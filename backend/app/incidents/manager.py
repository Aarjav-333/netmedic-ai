"""Incident state machine: DETECTED -> ANALYZING -> DIAGNOSED -> REMEDIATING -> VERIFYING -> RESOLVED.

The manager advances one stage per tick so the dashboard can show every
transition. It never reads the fault injector; it consumes detection results,
the live diagnosis and the healing engine only.
"""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone

from app.healing.engine import HealingEngine
from app.healing.verifier import SETTLE_TICKS, WINDOW_TICKS, summarise_window, verify
from app.logging_config import get_logger
from app.models.detection import ComponentKind, DetectionResult
from app.models.diagnosis import ActionType, Diagnosis
from app.models.incident import (
    STATUS_LABEL,
    HealingActionRecord,
    Incident,
    IncidentEvent,
    IncidentStatus,
    IncidentSummary,
    MetricWindow,
)
from app.models.telemetry import TelemetrySnapshot

log = get_logger("netmedic.incidents")

BASELINE_WINDOW = 5  # samples before the first abnormal one used as the pre-incident baseline
DIAGNOSIS_TIMEOUT_TICKS = 4
# Guard against transient blips: a mild anomaly must persist longer before it opens an incident.
MIN_OPEN_SEVERITY = 20.0
MILD_ANOMALY_TICKS = 4
MAX_HISTORY = 100

IncidentHook = Callable[[Incident], None]


class IncidentManager:
    def __init__(self, healing: HealingEngine, history: deque[TelemetrySnapshot], auto_heal: bool = True) -> None:
        self.healing = healing
        self.history = history
        self.auto_heal = auto_heal
        self.active: Incident | None = None
        self.closed: list[Incident] = []
        self._first_abnormal: dict[str, tuple[int, datetime]] = {}
        self._stage_tick: int = 0
        self._before: MetricWindow | None = None
        self._baseline: MetricWindow | None = None
        self._remediated_tick: int | None = None
        self._manual_go = False
        self.on_change: IncidentHook | None = None
        self.on_diagnosed: IncidentHook | None = None

    # ------------------------------------------------------------ queries
    def all_incidents(self) -> list[Incident]:
        items = [self.active] if self.active else []
        return items + self.closed

    def get(self, incident_id: str) -> Incident | None:
        return next((i for i in self.all_incidents() if i.id == incident_id), None)

    def summaries(self) -> list[IncidentSummary]:
        return [
            IncidentSummary(
                id=i.id,
                status=i.status,
                status_label=i.status_label,
                component_id=i.component_id,
                root_cause_label=i.root_cause_label,
                confidence=i.confidence,
                detected_at=i.detected_at,
                resolved_at=i.resolved_at,
                action=i.plan.action if i.plan else None,
                recovery_time_s=i.metrics.recovery_time_s,
                total_duration_s=i.metrics.total_duration_s,
            )
            for i in self.all_incidents()
        ]

    # ----------------------------------------------------------- control
    def request_healing(self, incident_id: str) -> Incident:
        incident = self.get(incident_id)
        if incident is None:
            raise KeyError(incident_id)
        if incident.status != IncidentStatus.DIAGNOSED:
            raise ValueError(f"Incident {incident_id} is {incident.status.value}, not awaiting remediation")
        self._manual_go = True
        return incident

    def cancel_active(self, tick: int, reason: str) -> Incident | None:
        incident = self.active
        if incident is None:
            return None
        self._transition(incident, IncidentStatus.CANCELLED, tick, reason)
        incident.resolved_at = datetime.now(timezone.utc)
        self._close(incident)
        return incident

    def reset(self) -> None:
        self._first_abnormal.clear()
        self._before = None
        self._baseline = None
        self._remediated_tick = None
        self._manual_go = False

    # --------------------------------------------------------------- tick
    def process(self, tick: int, snapshot: TelemetrySnapshot, detection: DetectionResult, diagnosis: Diagnosis | None) -> None:
        self._track_first_abnormal(tick, detection)
        self._drain_restored_events(tick)
        if self.active is not None:
            self._advance(tick, snapshot, detection, diagnosis)
        else:
            self._maybe_open(tick, detection, diagnosis)

    # ------------------------------------------------------------ opening
    def _track_first_abnormal(self, tick: int, detection: DetectionResult) -> None:
        flagged = {a.component_id for a in detection.anomalies}
        for component_id in flagged:
            self._first_abnormal.setdefault(component_id, (tick, detection.timestamp))
        for component_id in list(self._first_abnormal):
            if component_id not in flagged:
                del self._first_abnormal[component_id]

    def _maybe_open(self, tick: int, detection: DetectionResult, diagnosis: Diagnosis | None) -> None:
        candidates = [
            a
            for a in detection.anomalies
            if a.confirmed
            and a.component_kind in (ComponentKind.NODE, ComponentKind.LINK)
            and not self.healing.is_quarantined(a.component_id)
            and (a.severity >= MIN_OPEN_SEVERITY or a.consecutive_ticks >= MILD_ANOMALY_TICKS)
        ]
        if not candidates:
            return
        if diagnosis is not None and any(a.component_id == diagnosis.target_id for a in candidates):
            target = next(a for a in candidates if a.component_id == diagnosis.target_id)
        else:
            target = max(candidates, key=lambda a: a.severity)
        first_tick, first_at = self._first_abnormal.get(target.component_id, (tick, detection.timestamp))
        now = datetime.now(timezone.utc)
        incident = Incident(
            id=f"inc-{uuid.uuid4().hex[:8]}",
            status=IncidentStatus.DETECTED,
            status_label=STATUS_LABEL[IncidentStatus.DETECTED],
            component_id=target.component_id,
            component_kind=target.component_kind,
            anomaly_severity=target.severity,
            first_abnormal_at=first_at,
            detected_at=now,
            auto_heal=self.auto_heal,
        )
        if first_tick < tick:
            incident.timeline.append(
                IncidentEvent(
                    timestamp=first_at,
                    tick=first_tick,
                    stage=IncidentStatus.DETECTED,
                    message=f"Abnormal telemetry observed on {target.component_id}",
                )
            )
        self.active = incident
        self._stage_tick = tick
        self._baseline = self._baseline_window(first_tick, target.component_id)
        self._transition(
            incident,
            IncidentStatus.DETECTED,
            tick,
            f"Anomaly confirmed on {target.component_id} (severity {target.severity:.0f}/100, {target.method.replace('_', ' ')})",
        )
        incident.metrics.time_to_detect_s = round((now - first_at).total_seconds(), 2)
        log.info("[INCIDENT] %s opened for %s", incident.id, target.component_id)

    def _baseline_window(self, first_tick: int, component_id: str) -> MetricWindow | None:
        samples = [s for s in self.history if first_tick - BASELINE_WINDOW <= s.tick < first_tick]
        if not samples:
            return None
        flows = [r.flow_id for r in self.healing.network.routes.values() if component_id in r.path or component_id in r.links]
        return summarise_window(samples, flows, component_id)

    # ----------------------------------------------------------- advance
    def _advance(self, tick: int, snapshot: TelemetrySnapshot, detection: DetectionResult, diagnosis: Diagnosis | None) -> None:
        incident = self.active
        assert incident is not None
        status = incident.status

        if status == IncidentStatus.DETECTED:
            flagged = len(detection.anomalies)
            self._transition(incident, IncidentStatus.ANALYZING, tick, f"Analysing telemetry and topology ({flagged} component(s) flagged)")

        elif status == IncidentStatus.ANALYZING:
            if diagnosis is not None:
                self._apply_diagnosis(incident, diagnosis, tick)
            elif tick - self._stage_tick >= DIAGNOSIS_TIMEOUT_TICKS:
                still_flagged = any(a.component_id == incident.component_id for a in detection.anomalies)
                if still_flagged:
                    self._transition(incident, IncidentStatus.FAILED, tick, "Anomaly persists but matches no known root-cause signature; escalated to operator")
                else:
                    self._transition(incident, IncidentStatus.CANCELLED, tick, "Transient anomaly cleared on its own before a root cause could be established")
                self._finish(incident)

        elif status == IncidentStatus.DIAGNOSED:
            if incident.auto_heal or self._manual_go:
                self._manual_go = False
                self._remediate(incident, snapshot, tick)

        elif status == IncidentStatus.REMEDIATING:
            self._transition(incident, IncidentStatus.VERIFYING, tick, f"Verifying recovery: waiting {SETTLE_TICKS} samples to settle, then measuring {WINDOW_TICKS}")

        elif status == IncidentStatus.VERIFYING:
            assert self._remediated_tick is not None
            elapsed = tick - self._remediated_tick
            if elapsed >= SETTLE_TICKS + WINDOW_TICKS:
                self._verify(incident, tick)

    def _apply_diagnosis(self, incident: Incident, diagnosis: Diagnosis, tick: int) -> None:
        incident.diagnosis = diagnosis
        incident.plan = diagnosis.plan
        incident.root_cause = diagnosis.root_cause
        incident.root_cause_label = diagnosis.root_cause_label
        incident.confidence = diagnosis.confidence
        if diagnosis.target_id != incident.component_id:
            incident.component_id = diagnosis.target_id
            incident.component_kind = diagnosis.target_kind
        incident.diagnosed_at = datetime.now(timezone.utc)
        incident.metrics.time_to_diagnose_s = round((incident.diagnosed_at - incident.detected_at).total_seconds(), 2)
        self._transition(
            incident,
            IncidentStatus.DIAGNOSED,
            tick,
            f"Root cause: {diagnosis.root_cause_label} on {diagnosis.target_id} (confidence {diagnosis.confidence:.0%})",
        )
        incident.timeline.append(
            IncidentEvent(
                timestamp=datetime.now(timezone.utc),
                tick=tick,
                stage=IncidentStatus.DIAGNOSED,
                message=f"Remediation selected: {diagnosis.plan.summary}" + ("" if incident.auto_heal else " - awaiting operator approval"),
            )
        )
        if self.on_diagnosed:
            self.on_diagnosed(incident)

    def _remediate(self, incident: Incident, snapshot: TelemetrySnapshot, tick: int) -> None:
        assert incident.plan is not None
        affected = incident.diagnosis.affected_flows if incident.diagnosis else []
        recent = [s for s in self.history if s.tick <= tick][-WINDOW_TICKS:]
        self._before = summarise_window(recent, affected, incident.component_id)
        self._transition(incident, IncidentStatus.REMEDIATING, tick, f"Executing: {incident.plan.summary}")
        record = self.healing.execute(incident.plan, incident.id, tick, snapshot.links)
        incident.actions.append(record)
        incident.remediated_at = datetime.now(timezone.utc)
        incident.metrics.time_to_remediate_s = round(
            (incident.remediated_at - (incident.diagnosed_at or incident.detected_at)).total_seconds(), 2
        )
        self._remediated_tick = tick
        if record.result != "applied":
            message = (
                "No automatic remediation available - escalated to operator"
                if incident.plan.action in (ActionType.ESCALATE, ActionType.MONITOR)
                else f"Remediation failed: {record.details}"
            )
            self._transition(incident, IncidentStatus.FAILED, tick, message)
            self._finish(incident)
            return
        for change in record.route_changes:
            incident.timeline.append(
                IncidentEvent(
                    timestamp=datetime.now(timezone.utc),
                    tick=tick,
                    stage=IncidentStatus.REMEDIATING,
                    message=f"Traffic rerouted: {change.flow_id} now {' > '.join(change.after) if change.after else 'no path'} (was {' > '.join(change.before) or 'no path'})",
                )
            )
        if not record.route_changes:
            incident.timeline.append(
                IncidentEvent(timestamp=datetime.now(timezone.utc), tick=tick, stage=IncidentStatus.REMEDIATING, message=record.details)
            )

    def _verify(self, incident: Incident, tick: int) -> None:
        assert self._remediated_tick is not None and self._before is not None
        window_start = self._remediated_tick + SETTLE_TICKS + 1
        samples = [s for s in self.history if window_start <= s.tick <= tick][-WINDOW_TICKS:]
        affected = incident.diagnosis.affected_flows if incident.diagnosis else []
        after = summarise_window(samples, affected, incident.component_id)
        report = verify(self._baseline, self._before, after)
        incident.recovery = report
        incident.verified_at = report.verified_at
        incident.metrics.recovery_time_s = round((report.verified_at - (incident.remediated_at or report.verified_at)).total_seconds(), 2)
        self._transition(incident, report.status, tick, report.summary)
        self._finish(incident)

    # ------------------------------------------------------------ helpers
    def _transition(self, incident: Incident, status: IncidentStatus, tick: int, message: str) -> None:
        incident.status = status
        incident.status_label = STATUS_LABEL[status]
        incident.timeline.append(IncidentEvent(timestamp=datetime.now(timezone.utc), tick=tick, stage=status, message=message))
        self._stage_tick = tick
        log.info("[INCIDENT] %s -> %s: %s", incident.id, STATUS_LABEL[status], message)
        if self.on_change:
            self.on_change(incident)

    def _finish(self, incident: Incident) -> None:
        incident.resolved_at = datetime.now(timezone.utc)
        incident.metrics.total_duration_s = round((incident.resolved_at - incident.first_abnormal_at).total_seconds(), 2)
        self._close(incident)

    def _close(self, incident: Incident) -> None:
        self.closed.insert(0, incident)
        del self.closed[MAX_HISTORY:]
        self.active = None
        self._before = None
        self._baseline = None
        self._remediated_tick = None
        self._manual_go = False
        if self.on_change:
            self.on_change(incident)

    def _drain_restored_events(self, tick: int) -> None:
        while self.healing.restored_events:
            incident_id, _component, message = self.healing.restored_events.pop(0)
            incident = self.get(incident_id)
            if incident is None:
                continue
            incident.timeline.append(
                IncidentEvent(timestamp=datetime.now(timezone.utc), tick=tick, stage=incident.status, message=message)
            )
            if self.on_change:
                self.on_change(incident)

    def record_action(self, record: HealingActionRecord) -> None:
        incident = self.get(record.incident_id)
        if incident is not None:
            incident.actions.append(record)
            if self.on_change:
                self.on_change(incident)
