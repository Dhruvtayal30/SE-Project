import json

from cfg_analyzer.validation import MAX_SOURCE_CHARS


def post(client, body, **kw):
    return client.post("/api/analyze", data=json.dumps(body), content_type="application/json", **kw)


def test_health(client):
    assert client.get("/api/health").get_json()["ok"] is True


def test_successful_analysis_shape(client):
    r = post(client, {"source": "int main(void){ if (1) return 1; return 0; }"})
    assert r.status_code == 200
    d = r.get_json()
    for key in ("function", "functions", "graph", "statistics", "complexity", "reachability", "paths", "warnings", "source_map", "convention"):
        assert key in d
    assert d["convention"] == "course" and d["complexity"]["convention"] == "course"
    assert d["graph"]["nodes"][0]["id"] == d["graph"]["entry"]
    assert {"id", "source", "target", "label", "kind", "back_edge"} <= set(d["graph"]["edges"][0])


def test_empty_source_is_400(client):
    for body in ({"source": ""}, {"source": "   \n"}):
        r = post(client, body)
        assert r.status_code == 400 and r.get_json()["error"]["code"] == "EMPTY_SOURCE"


def test_malformed_json_is_400(client):
    r = client.post("/api/analyze", data="{not json", content_type="application/json")
    assert r.status_code == 400 and r.get_json()["error"]["code"] == "MALFORMED_JSON"


def test_wrong_content_type_is_400(client):
    r = client.post("/api/analyze", data="int main(){}", content_type="text/plain")
    assert r.status_code == 400


def test_wrong_types_are_400(client):
    for body in ([], {"source": 5}, {"source": "int f(){}", "function": 3}, {"source": "int f(){}", "options": []},
                 {"source": "int f(){}", "options": {"merge_blocks": "yes"}},
                 {"source": "int f(){}", "convention": "default"}, {"source": "int f(){}", "convention": []}, {}):
        r = post(client, body)
        assert r.status_code == 400, body
        assert r.get_json()["ok"] is False


def test_nul_byte_is_rejected(client):
    assert post(client, {"source": "int f(){}\x00"}).status_code == 400


def test_invalid_c_is_422_with_locations(client):
    r = post(client, {"source": "int f(void){\n int x = 1\n return x;\n}"})
    d = r.get_json()
    assert r.status_code == 422 and d["error"]["code"] == "SYNTAX_ERROR"
    assert d["error"]["locations"][0]["line"] == 2 and "graph" not in d


def test_unsupported_is_422(client):
    r = post(client, {"source": "int f(void){\n#if X\n return 1;\n#endif\n}"})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "UNSUPPORTED_CONSTRUCT"


def test_unknown_function_is_422(client):
    r = post(client, {"source": "int f(void){return 0;}", "function": "g"})
    assert r.status_code == 422 and r.get_json()["error"]["details"]["available"] == ["f"]


def test_large_but_permitted_input(client):
    body = "int f(int x){ int y=0; " + "".join(f"if (x=={i}) y+={i}; " for i in range(130)) + "return y; }"
    assert len(body) < MAX_SOURCE_CHARS
    r = post(client, {"source": body})
    assert r.status_code == 200 and r.get_json()["complexity"]["value"] == 131
    assert r.get_json()["paths"]["status"] == "skipped"


def test_source_over_limit_is_413(client):
    r = post(client, {"source": "int f(){}" + " " * (MAX_SOURCE_CHARS + 1)})
    assert r.status_code == 413 and r.get_json()["error"]["code"] == "SOURCE_TOO_LARGE"


def test_graph_too_large_is_422(client):
    body = "int f(int x){ " + "x++; if (x) x--; " * 400 + "return x; }"
    assert len(body) < MAX_SOURCE_CHARS
    r = post(client, {"source": body})
    assert r.status_code == 422 and r.get_json()["error"]["code"] == "GRAPH_TOO_LARGE"


def test_deep_nesting_is_handled(client):
    body = "int f(int x){ " + "if (x) { " * 150 + "x++;" + "}" * 150 + " return x; }"
    r = post(client, {"source": body})
    assert r.status_code in (200, 422) and r.get_json()["ok"] in (True, False)
    assert r.status_code != 500


def test_internal_failures_return_generic_500_without_traceback(client, monkeypatch):
    import cfg_analyzer.api as api
    monkeypatch.setattr(api, "analyze_source", lambda req: 1 / 0)
    r = post(client, {"source": "int f(){}"})
    assert r.status_code == 500 and r.get_json()["error"]["code"] == "INTERNAL_ERROR"
    assert "ZeroDivision" not in r.get_data(as_text=True)


def test_unknown_route_and_method_are_json(client):
    assert client.get("/api/nope").get_json()["error"]["code"] == "NOT_FOUND"
    r = client.get("/api/analyze")
    assert r.status_code == 405 and r.get_json()["ok"] is False


def test_examples_endpoint_serves_sources_and_expectations(client):
    d = client.get("/api/examples").get_json()
    assert len(d["examples"]) >= 10
    assert all("source" in e and "expected" in e for e in d["examples"])


def test_static_frontend_is_served_when_a_build_exists(tmp_path):
    from cfg_analyzer.api import create_app
    (tmp_path / "index.html").write_text("<!doctype html><title>x</title>")
    c = create_app(static_dir=tmp_path).test_client()
    assert c.get("/").status_code == 200 and b"<title>x</title>" in c.get("/").data
    assert c.get("/missing.js").status_code == 404
    assert c.get("/api/nope").get_json()["error"]["code"] == "NOT_FOUND"
    assert c.get("/api/analyze").status_code == 405
    assert c.post("/api/analyze", json={"source": "int f(void){return 0;}"}).status_code == 200
