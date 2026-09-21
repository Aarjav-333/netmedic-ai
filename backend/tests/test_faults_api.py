def test_fault_catalog(client, engine):
    res = client.get("/api/faults")
    assert res.status_code == 200
    body = res.json()
    assert body["active"] == []
    assert {d["type"] for d in body["catalog"]} >= {"router_congestion", "link_failure", "traffic_spike"}


def test_inject_and_reset_via_api(client, engine):
    res = client.post("/api/faults/inject", json={"fault_type": "router_congestion", "target_id": "R4", "severity": "high"})
    assert res.status_code == 201, res.text
    fault = res.json()
    assert fault["target_id"] == "R4" and fault["severity"] == "high"
    assert client.get("/api/faults").json()["active"][0]["id"] == fault["id"]
    # Telemetry reflects the fault immediately.
    r4 = next(n for n in client.get("/api/telemetry/current").json()["nodes"] if n["node_id"] == "R4")
    assert r4["bandwidth_utilization_percent"] > 95

    res = client.delete(f"/api/faults/{fault['id']}")
    assert res.status_code == 200 and res.json()["cleared_by"] == "operator"
    assert client.delete(f"/api/faults/{fault['id']}").status_code == 404

    client.post("/api/faults/inject", json={"fault_type": "link_failure", "target_id": "L-R1-R3"})
    res = client.post("/api/faults/reset")
    assert res.status_code == 200 and res.json()["cleared_faults"] == 1
    assert client.get("/api/faults").json()["active"] == []


def test_invalid_injection_returns_400(client, engine):
    res = client.post("/api/faults/inject", json={"fault_type": "link_failure", "target_id": "R4"})
    assert res.status_code == 400
    assert "link" in res.json()["detail"].lower()
