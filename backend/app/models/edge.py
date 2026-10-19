"""Schema for the on-device (Qualcomm AI Hub) detector profile.

The artefact is produced offline by `scripts/edge_detector.py` and served read-only:
the backend never trains, exports or calls AI Hub at runtime, and never imports torch.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EdgeModelInfo(BaseModel):
    architecture: str
    features: list[str]
    parameters: int
    training_samples: int
    threshold: float = Field(description="Reconstruction-error threshold calibrated on healthy telemetry")
    threshold_quantile: float


class EdgeFaultCheck(BaseModel):
    reconstruction_error: float
    threshold: float
    detected: bool
    isolation_forest_detected: bool | None
    agrees_with_isolation_forest: bool


class EdgeValidation(BaseModel):
    healthy_false_positive_rate: float
    healthy_samples: int
    faults: dict[str, EdgeFaultCheck]
    detects_every_fault: bool
    agrees_with_isolation_forest: bool


class EdgeDeployment(BaseModel):
    device: str
    runtime: str
    compile_job_url: str
    profile_job_url: str
    inference_time_us: float | None
    peak_memory_bytes: int | None
    first_load_time_us: float | None
    layers_by_compute_unit: dict[str, int]


class EdgeProfile(BaseModel):
    generated_at: datetime
    model: EdgeModelInfo
    validation: EdgeValidation
    deployment: EdgeDeployment | None = Field(
        default=None, description="Null when the artefact was generated with --offline"
    )
