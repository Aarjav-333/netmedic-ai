from app.models.incident import IncidentStatus


def test_incident_lifecycle_via_api(client, engine):
    # Incident history survives resets by design; only the active incident is cleared.
    history_before = len(client.get("/api/incidents").json())
    assert client.get("/api/incidents/active").json() is None
    client.post("/api/faults/inject", json={"fault_type": "router_congestion", "target_id": "R4"})
    for _ in range(3):
        engine.tick()
    active = client.get("/api/incidents/active").json()
    assert active is not None and active["component_id"] == "R4"
    incident_id = active["id"]
    for _ in range(12):
        engine.tick()
    body = client.get(f"/api/incidents/{incident_id}").json()
    assert body["status"] == "resolved"
    assert body["recovery"]["status"] == "resolved"
    assert body["actions"][0]["route_changes"]
    summaries = client.get("/api/incidents").json()
    assert len(summaries) == history_before + 1
    assert summaries[0]["id"] == incident_id and summaries[0]["recovery_time_s"] is not None
    assert client.get("/api/incidents/nope").status_code == 404
    with client.websocket_connect("/ws/network") as ws:
        message = ws.receive_json()
    assert message["incidents"][0]["id"] == incident_id
    assert message["quarantined"] == ["R4"]


def test_manual_healing_via_api(client, engine):
    assert client.post("/api/healing/mode", json={"auto_heal": False}).json()["auto_heal"] is False
    assert client.get("/api/healing/mode").json()["auto_heal"] is False
    client.post("/api/faults/inject", json={"fault_type": "router_congestion", "target_id": "R4"})
    for _ in range(5):
        engine.tick()
    incident = client.get("/api/incidents/active").json()
    assert incident["status"] == IncidentStatus.DIAGNOSED.value
    assert client.post("/api/healing/nope/execute").status_code == 404
    res = client.post(f"/api/healing/{incident['id']}/execute")
    assert res.status_code == 200
    assert res.json()["status"] == IncidentStatus.REMEDIATING.value
    assert client.post(f"/api/healing/{incident['id']}/execute").status_code == 409
    client.post("/api/healing/mode", json={"auto_heal": True})
