"""Synthetic healthy-telemetry generation and Isolation Forest training.

The training set is produced by running the *same* simulator with no faults
across several random seeds and mild demand variation (quiet nights, busy
afternoons), so "normal" covers the whole healthy operating envelope rather
than a single point.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from app.config import BACKEND_DIR
from app.detection.features import FEATURE_NAMES, node_feature_vector
from app.logging_config import get_logger
from app.simulation.network import NetworkSimulator
from app.telemetry.generator import TelemetryGenerator

log = get_logger("netmedic.detection")

MODEL_DIR = BACKEND_DIR / "data" / "models"
MODEL_PATH = MODEL_DIR / "isolation_forest.joblib"
META_PATH = MODEL_DIR / "isolation_forest.json"
DATASET_PATH = BACKEND_DIR / "data" / "training" / "normal_telemetry.csv"

DEFAULT_TICKS = 400
DEFAULT_SEEDS = (11, 23, 37, 41, 59, 67)
DEMAND_JITTER = 0.35  # +/- 35 % per-flow demand variation between runs
DIURNAL_AMPLITUDE = 0.15  # slow +/- 15 % swing within a run (busy / quiet periods)
CONTAMINATION = 0.005  # fraction of training data allowed beyond the threshold
# A deliberately extreme feature vector (10x latency, 50 % loss, saturated, pegged CPU/memory,
# 5x connections). Its decision score anchors severity 100 so the 0-100 scale spans what the
# model can actually express instead of an arbitrary constant.
WORST_CASE_VECTOR = (10.0, 50.0, 1.0, 150.0, 100.0, 100.0, 5.0)
N_ESTIMATORS = 200


@dataclass
class ModelMetadata:
    trained_at: str
    n_samples: int
    n_features: int
    feature_names: list[str]
    contamination: float
    n_estimators: int
    threshold: float  # decision_function value at the contamination quantile
    severity_span: float  # decision drop below the threshold that maps to severity 100
    seeds: list[int]
    ticks_per_seed: int


def generate_normal_dataset(
    ticks: int = DEFAULT_TICKS,
    seeds: tuple[int, ...] = DEFAULT_SEEDS,
    demand_jitter: float = DEMAND_JITTER,
) -> pd.DataFrame:
    """Run fault-free simulations and collect one row per node per tick."""
    rows: list[dict[str, float | str | int]] = []
    for seed in seeds:
        rng = np.random.default_rng(seed)
        network = NetworkSimulator()
        # Vary demand per flow and per run, plus a slow in-run swing, so the model
        # learns the whole healthy envelope rather than one operating point.
        base_demand = {f.id: f.demand_mbps for f in network.flows.values()}
        run_factor = {f: float(rng.uniform(1 - demand_jitter, 1 + demand_jitter)) for f in base_demand}
        phase = {f: float(rng.uniform(0, 2 * np.pi)) for f in base_demand}
        generator = TelemetryGenerator(network, seed=seed)
        for tick in range(ticks):
            for flow in network.flows.values():
                swing = 1 + DIURNAL_AMPLITUDE * np.sin(2 * np.pi * tick / ticks + phase[flow.id])
                flow.demand_mbps = base_demand[flow.id] * run_factor[flow.id] * swing
            snapshot = generator.generate(tick)
            for sample in snapshot.nodes:
                vector = node_feature_vector(sample, network.nodes[sample.node_id])
                row: dict[str, float | str | int] = {"seed": seed, "tick": tick, "node_id": sample.node_id}
                row.update(dict(zip(FEATURE_NAMES, vector.tolist())))
                rows.append(row)
    return pd.DataFrame(rows)


def train_model(dataset: pd.DataFrame, random_state: int = 7) -> tuple[IsolationForest, ModelMetadata]:
    features = dataset[list(FEATURE_NAMES)].to_numpy(dtype=float)
    model = IsolationForest(
        n_estimators=N_ESTIMATORS,
        contamination=CONTAMINATION,
        random_state=random_state,
        n_jobs=-1,
    )
    model.fit(features)
    decisions = model.decision_function(features)
    threshold = float(np.quantile(decisions, CONTAMINATION))
    worst = float(model.decision_function(np.array([WORST_CASE_VECTOR]))[0])
    severity_span = float(max(0.02, threshold - worst))
    metadata = ModelMetadata(
        trained_at=datetime.now(timezone.utc).isoformat(),
        n_samples=int(len(features)),
        n_features=len(FEATURE_NAMES),
        feature_names=list(FEATURE_NAMES),
        contamination=CONTAMINATION,
        n_estimators=N_ESTIMATORS,
        threshold=threshold,
        severity_span=severity_span,
        seeds=sorted(dataset["seed"].unique().tolist()),
        ticks_per_seed=int(dataset["tick"].max()) + 1,
    )
    return model, metadata


def save_model(model: IsolationForest, metadata: ModelMetadata, path: Path = MODEL_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    META_PATH.write_text(json.dumps(asdict(metadata), indent=2), encoding="utf-8")


def load_model(path: Path = MODEL_PATH) -> tuple[IsolationForest, ModelMetadata] | None:
    if not path.exists() or not META_PATH.exists():
        return None
    try:
        model = joblib.load(path)
        metadata = ModelMetadata(**json.loads(META_PATH.read_text(encoding="utf-8")))
    except Exception:  # noqa: BLE001 - corrupt / incompatible artefacts are simply retrained
        log.warning("[DETECTION] Could not load persisted model; retraining")
        return None
    if metadata.feature_names != list(FEATURE_NAMES):
        log.warning("[DETECTION] Persisted model features differ; retraining")
        return None
    return model, metadata


def train_and_save(save_dataset: bool = False) -> tuple[IsolationForest, ModelMetadata]:
    log.info("[DETECTION] Generating synthetic healthy telemetry for training...")
    dataset = generate_normal_dataset()
    if save_dataset:
        DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
        dataset.to_csv(DATASET_PATH, index=False)
    model, metadata = train_model(dataset)
    save_model(model, metadata)
    log.info(
        "[DETECTION] Isolation Forest trained on %d samples (threshold=%.4f)",
        metadata.n_samples,
        metadata.threshold,
    )
    return model, metadata
