def test_detection_endpoints(client, engine):
    res = client.get("/api/detection/model")
    assert res.status_code == 200
    body = res.json()
    assert body["algorithm"].startswith("IsolationForest")
    assert body["n_samples"] > 1000
    assert len(body["feature_names"]) == 7

    res = client.get("/api/detection/current")
    assert res.status_code == 200
    assert res.json()["confirmed_ids"] == []

    client.post("/api/faults/inject", json={"fault_type": "router_congestion", "target_id": "R4"})
    engine.tick()
    current = client.get("/api/detection/current").json()
    assert "R4" in current["confirmed_ids"]
    assert current["node_scores"]["R4"] > 50

    ws_state = client.get("/api/telemetry/current")
    assert ws_state.status_code == 200
