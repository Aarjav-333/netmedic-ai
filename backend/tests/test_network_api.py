def test_topology_endpoint(client, engine):
    res = client.get("/api/network/topology")
    assert res.status_code == 200
    body = res.json()
    assert len(body["nodes"]) == 10
    assert len(body["links"]) == 15
    assert {r["flow_id"] for r in body["routes"]} == {f["id"] for f in body["flows"]}
    assert body["nodes"][0]["position"]["x"] >= 0


def test_status_endpoint(client, engine):
    res = client.get("/api/network/status")
    assert res.status_code == 200
    body = res.json()
    assert body["active_nodes"] == 10
    assert body["rerouted_flows"] == 0
    assert body["broken_flows"] == 0
