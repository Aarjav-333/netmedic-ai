def test_current_telemetry(client, engine):
    res = client.get("/api/telemetry/current")
    assert res.status_code == 200
    body = res.json()
    assert len(body["nodes"]) == 10
    assert body["summary"]["health_score"] > 90


def test_history_grows_with_ticks(client, engine):
    for _ in range(5):
        engine.tick()
    res = client.get("/api/telemetry/history?limit=3")
    assert res.status_code == 200
    points = res.json()["points"]
    assert len(points) == 3
    assert "R4" in points[0]["node_latency_ms"]


def test_websocket_sends_state(client, engine):
    with client.websocket_connect("/ws/network") as ws:
        message = ws.receive_json()
    assert message["type"] == "state"
    assert message["telemetry"]["summary"]["health_score"] > 0
    assert len(message["topology"]["routes"]) == 6
