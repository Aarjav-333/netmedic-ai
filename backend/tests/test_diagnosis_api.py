def test_diagnosis_endpoint(client, engine):
    assert client.get("/api/diagnosis/current").json() is None
    client.post("/api/faults/inject", json={"fault_type": "router_congestion", "target_id": "R4"})
    engine.tick()
    body = client.get("/api/diagnosis/current").json()
    assert body["root_cause"] == "router_congestion"
    assert body["target_id"] == "R4"
    assert body["plan"]["action"] == "reroute_around_node"
    assert body["evidence"]
    with client.websocket_connect("/ws/network") as ws:
        message = ws.receive_json()
    assert message["diagnosis"]["target_id"] == "R4"
