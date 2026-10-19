"""The on-device detector artefact is served read-only and never fabricated."""

import json

from app.api.detection import EDGE_PROFILE_PATH
from app.models.edge import EdgeProfile


def test_edge_profile_artefact_is_valid_and_deployed():
    assert EDGE_PROFILE_PATH.exists(), "run scripts/edge_detector.py to generate it"
    profile = EdgeProfile.model_validate(json.loads(EDGE_PROFILE_PATH.read_text(encoding="utf-8")))
    # The model has to actually work before any deployment claim is meaningful.
    assert profile.validation.detects_every_fault
    assert profile.validation.agrees_with_isolation_forest
    assert profile.validation.healthy_false_positive_rate <= 0.01
    assert profile.model.parameters > 0
    # Figures must come from a recorded AI Hub job, not from anything computed locally.
    d = profile.deployment
    assert d is not None, "artefact was generated with --offline"
    assert d.compile_job_url.startswith("https://app.aihub.qualcomm.com/jobs/")
    assert d.profile_job_url.startswith("https://app.aihub.qualcomm.com/jobs/")
    assert d.inference_time_us and d.inference_time_us > 0
    assert sum(d.layers_by_compute_unit.values()) > 0


def test_edge_endpoint_serves_the_artefact(client, engine):
    body = client.get("/api/detection/edge").json()
    assert body["deployment"]["device"]
    assert body["deployment"]["layers_by_compute_unit"]
    assert body["validation"]["detects_every_fault"] is True


def test_edge_artefact_contains_no_credentials():
    raw = EDGE_PROFILE_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("token", "api_key", "apikey", "secret", "authorization"):
        assert forbidden not in raw, f"{forbidden!r} must never reach a committed artefact"
