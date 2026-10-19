"""Train, validate and deploy NetMedic's on-device anomaly detector to Qualcomm AI Hub.

Why this exists
---------------
The live pipeline scores telemetry with a scikit-learn Isolation Forest running in the
backend. A real deployment would score it *on the network device itself*, so the loop
closes without a round trip to a server. Tree ensembles do not map onto an NPU, so the
on-device variant is a compact autoencoder trained on the same seven normalised features
and the same synthetic healthy telemetry: it flags a sample when reconstruction error
exceeds a threshold calibrated on healthy data.

This script:
  1. generates the healthy training set (the same generator the Isolation Forest uses),
  2. trains the autoencoder and calibrates its threshold,
  3. validates it against every injectable fault and measures agreement with the
     Isolation Forest - if it does not actually detect faults, it is not worth deploying,
  4. exports it, compiles it for a Qualcomm device and profiles it on real hardware via
     Qualcomm AI Hub,
  5. writes backend/data/edge_profile.json, which the backend serves read-only.

Usage (from the repo root):
    pip install -r backend/requirements-edge.txt
    set QUALCOMM_AI_HUB_TOKEN=...        # or put it in .env (git-ignored)
    python scripts/edge_detector.py --device "Samsung Galaxy S25 (Family)"
    python scripts/edge_detector.py --offline        # train + validate, skip AI Hub
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "backend"))

from app.detection.features import FEATURE_NAMES, node_feature_vector  # noqa: E402
from app.detection.trainer import generate_normal_dataset, load_model  # noqa: E402
from app.engine import SimulationEngine  # noqa: E402
from app.models.faults import FaultType, Severity  # noqa: E402

ARTEFACT = REPO / "backend" / "data" / "edge_profile.json"
DEFAULT_DEVICE = "Samsung Galaxy S25 (Family)"
AI_HUB_URL = "https://app.aihub.qualcomm.com"
N_FEATURES = len(FEATURE_NAMES)
EPOCHS = 60
BATCH = 256
LATENT = 3
# Flag a sample when reconstruction error exceeds this quantile of the healthy set.
THRESHOLD_QUANTILE = 0.995


class TelemetryAutoencoder(nn.Module):
    """7 -> 16 -> 3 -> 16 -> 7. Small enough to sit on an NPU, expressive enough to
    reconstruct healthy telemetry and fail loudly on anything else."""

    def __init__(self, n_features: int = N_FEATURES, latent: int = LATENT) -> None:
        super().__init__()
        self.encoder = nn.Sequential(nn.Linear(n_features, 16), nn.ReLU(), nn.Linear(16, latent))
        self.decoder = nn.Sequential(nn.Linear(latent, 16), nn.ReLU(), nn.Linear(16, n_features))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))


@dataclass
class Standardiser:
    """Feature scaling folded into the artefact so the device needs no sklearn."""

    mean: list[float]
    scale: list[float]

    def apply(self, x: np.ndarray) -> np.ndarray:
        return (x - np.array(self.mean)) / np.array(self.scale)


def train(seed: int = 7) -> tuple[TelemetryAutoencoder, Standardiser, float, int]:
    torch.manual_seed(seed)
    frame = generate_normal_dataset()
    raw = frame[list(FEATURE_NAMES)].to_numpy(dtype=np.float32)
    std = Standardiser(mean=raw.mean(0).tolist(), scale=(raw.std(0) + 1e-6).tolist())
    data = torch.tensor(std.apply(raw), dtype=torch.float32)

    model = TelemetryAutoencoder()
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    loss_fn = nn.MSELoss()
    for epoch in range(EPOCHS):
        perm = torch.randperm(len(data))
        total = 0.0
        for i in range(0, len(data), BATCH):
            batch = data[perm[i : i + BATCH]]
            opt.zero_grad()
            loss = loss_fn(model(batch), batch)
            loss.backward()
            opt.step()
            total += loss.item() * len(batch)
        if epoch % 20 == 0 or epoch == EPOCHS - 1:
            print(f"  epoch {epoch:3d}  loss {total / len(data):.5f}")

    model.eval()
    with torch.no_grad():
        errors = ((model(data) - data) ** 2).mean(1).numpy()
    threshold = float(np.quantile(errors, THRESHOLD_QUANTILE))
    print(f"  threshold (q{THRESHOLD_QUANTILE}): {threshold:.5f}  on {len(data)} healthy samples")
    return model, std, threshold, len(data)


def reconstruction_error(model: TelemetryAutoencoder, std: Standardiser, vectors: np.ndarray) -> np.ndarray:
    with torch.no_grad():
        x = torch.tensor(std.apply(vectors), dtype=torch.float32)
        return ((model(x) - x) ** 2).mean(1).numpy()


def validate(model: TelemetryAutoencoder, std: Standardiser, threshold: float) -> dict:
    """Does it actually detect the faults, and does it agree with the Isolation Forest?"""
    cases = [
        (FaultType.ROUTER_CONGESTION, "R4", Severity.MEDIUM),
        (FaultType.NODE_OVERLOAD, "R2", Severity.HIGH),
        (FaultType.TRAFFIC_SPIKE, "SW3", Severity.MEDIUM),
        (FaultType.ROUTER_CONGESTION, "R1", Severity.HIGH),
    ]
    engine = SimulationEngine()
    forest = load_model()
    results: dict[str, dict] = {}

    engine.reset()
    healthy_flags = 0
    healthy_total = 0
    for _ in range(40):
        snap = engine.tick()
        for sample in snap.nodes:
            vec = node_feature_vector(sample, engine.network.nodes[sample.node_id])
            healthy_total += 1
            healthy_flags += int(reconstruction_error(model, std, vec[None, :])[0] > threshold)
    false_positive_rate = healthy_flags / max(1, healthy_total)
    print(f"  healthy false-positive rate: {false_positive_rate:.3%} ({healthy_flags}/{healthy_total})")

    for fault, target, severity in cases:
        engine.reset()
        for _ in range(8):
            engine.tick()
        engine.faults.inject(fault, target, severity)
        for _ in range(4):
            snap = engine.tick()
        sample = snap.node(target) if target in engine.network.nodes else None
        if sample is None:
            continue
        vec = node_feature_vector(sample, engine.network.nodes[target])
        err = float(reconstruction_error(model, std, vec[None, :])[0])
        detected = err > threshold
        forest_detected = None
        if forest is not None:
            forest_model, meta = forest
            forest_detected = bool(forest_model.decision_function(vec[None, :])[0] < meta.threshold)
        results[f"{fault.value}@{target}"] = {
            "reconstruction_error": round(err, 5),
            "threshold": round(threshold, 5),
            "detected": detected,
            "isolation_forest_detected": forest_detected,
            "agrees_with_isolation_forest": forest_detected is None or forest_detected == detected,
        }
        print(f"  {fault.value:22} on {target:4} err={err:8.4f} detected={detected} forest={forest_detected}")

    detected_all = all(r["detected"] for r in results.values())
    agree_all = all(r["agrees_with_isolation_forest"] for r in results.values())
    return {
        "healthy_false_positive_rate": round(false_positive_rate, 5),
        "healthy_samples": healthy_total,
        "faults": results,
        "detects_every_fault": detected_all,
        "agrees_with_isolation_forest": agree_all,
    }


def deploy(model: TelemetryAutoencoder, device_name: str, token: str) -> dict:
    """Compile for the target device and profile it on real Qualcomm hardware."""
    from qai_hub.client import Client, ClientConfig

    shape = (1, N_FEATURES)
    with torch.no_grad():
        exported = torch.export.export(model, (torch.rand(shape),))

    client = Client(ClientConfig(api_url=AI_HUB_URL, web_url=AI_HUB_URL, api_token=token, verbose=False))
    device = next((d for d in client.get_devices() if d.name == device_name), None)
    if device is None:
        raise SystemExit(f"Unknown AI Hub device {device_name!r}")

    print(f"  compiling for {device.name} (tflite)...")
    compile_job = client.submit_compile_job(
        model=exported, device=device, input_specs=dict(telemetry=shape),
        options="--target_runtime tflite", name="netmedic-edge-detector",
    )
    target = compile_job.get_target_model()
    if target is None:
        raise SystemExit(f"Compile failed: {compile_job.url}")
    print(f"  compile job: {compile_job.url}")

    print("  profiling on device...")
    profile_job = client.submit_inference_job(
        model=target, device=device, inputs=dict(telemetry=[np.zeros(shape, dtype=np.float32)]),
        profile=True, name="netmedic-edge-detector-profile",
    )
    profile = profile_job.download_profile()
    summary = profile["execution_summary"]
    units: dict[str, int] = {}
    for layer in profile.get("execution_detail", []):
        unit = layer.get("compute_unit", "unknown")
        units[unit] = units.get(unit, 0) + 1
    print(f"  profile job: {profile_job.url}")
    print(f"  inference {summary.get('estimated_inference_time')} us | layers {units}")

    return {
        "device": device.name,
        "runtime": "tflite",
        "compile_job_url": compile_job.url,
        "profile_job_url": profile_job.url,
        "inference_time_us": summary.get("estimated_inference_time"),
        "peak_memory_bytes": summary.get("estimated_inference_peak_memory"),
        "first_load_time_us": summary.get("first_load_time"),
        "layers_by_compute_unit": units,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="AI Hub device name")
    parser.add_argument("--offline", action="store_true", help="train and validate only; skip AI Hub")
    args = parser.parse_args()

    print("[1/3] Training the on-device autoencoder on synthetic healthy telemetry...")
    model, std, threshold, n_samples = train()

    print("[2/3] Validating against the injectable faults...")
    validation = validate(model, std, threshold)
    if not validation["detects_every_fault"]:
        raise SystemExit("Refusing to deploy: the autoencoder missed at least one fault.")

    artefact = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": {
            "architecture": f"{N_FEATURES}-16-{LATENT}-16-{N_FEATURES} autoencoder",
            "features": list(FEATURE_NAMES),
            "parameters": sum(p.numel() for p in model.parameters()),
            "training_samples": n_samples,
            "threshold": round(threshold, 5),
            "threshold_quantile": THRESHOLD_QUANTILE,
            "standardiser": asdict(std),
        },
        "validation": validation,
        "deployment": None,
    }

    if args.offline:
        print("[3/3] --offline: skipping Qualcomm AI Hub.")
    else:
        token = os.environ.get("QUALCOMM_AI_HUB_TOKEN", "").strip()
        if not token:
            raise SystemExit("Set QUALCOMM_AI_HUB_TOKEN (see .env.example). Never commit it.")
        print("[3/3] Deploying to Qualcomm AI Hub...")
        artefact["deployment"] = deploy(model, args.device, token)

    ARTEFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTEFACT.write_text(json.dumps(artefact, indent=2), encoding="utf-8")
    print(f"\nWrote {ARTEFACT.relative_to(REPO)}")


if __name__ == "__main__":
    main()
