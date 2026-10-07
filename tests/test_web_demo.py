from pathlib import Path

import app


EXPECTED_SCENARIOS = {
    "complete-revocation",
    "residual-delegation",
    "queued-action",
    "unknown-external-agent",
}


def test_home_page_and_all_scenario_endpoints_load():
    client = app.app.test_client()

    page = client.get("/")
    scenarios = client.get("/api/scenarios")

    assert page.status_code == 200
    assert b"AuthorityLens" in page.data
    assert b"This prototype compares a target-local permission indicator with a system-consequence-aware representation." in page.data
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/styles.css").status_code == 200
    assert scenarios.status_code == 200
    assert {item["id"] for item in scenarios.get_json()} == EXPECTED_SCENARIOS
    expected_results = {
        "complete-revocation": ("on", "Gmail Access"),
        "residual-delegation": ("on", "Gmail Access"),
        "queued-action": ("on", "Gmail Sending"),
        "unknown-external-agent": ("on", "Gmail Access"),
    }
    for scenario_id in EXPECTED_SCENARIOS:
        response = client.get(f"/api/scenarios/{scenario_id}")
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["scenario"]["id"] == scenario_id
        expected_baseline, expected_label = expected_results[scenario_id]
        assert payload["baseline"]["access_status"].lower() == expected_baseline
        assert payload["baseline"]["target_principal_display"] == "Agent A"
        assert payload["baseline"]["resource_label"] == expected_label
        assert payload["control_phase"] == "before_action"
        assert payload["authority_lens"]["outcome"] is None


def test_baseline_and_authority_lens_use_the_same_control_view(monkeypatch):
    seen = []
    build_baseline = app.build_baseline_control_view
    build_authority_lens = app.build_authority_lens_control_view

    def baseline_spy(view):
        seen.append(("baseline", id(view)))
        return build_baseline(view)

    def authority_lens_spy(view):
        seen.append(("authority_lens", id(view)))
        return build_authority_lens(view)

    monkeypatch.setattr(app, "build_baseline_control_view", baseline_spy)
    monkeypatch.setattr(app, "build_authority_lens_control_view", authority_lens_spy)

    payload = app.build_scenario_payload(
        "residual-delegation",
        ["delegate-read-agent-b", "revoke-agent-a"],
    )

    assert [name for name, _ in seen] == ["baseline", "authority_lens"]
    assert seen[0][1] == seen[1][1]
    assert payload["baseline"]["access_status"] == "OFF"
    assert payload["authority_lens"]["outcome"] == "partial"
    assert payload["authority_lens"]["residual_items"][0]["principal_id"] == "agent-b"


def test_frontend_fetches_backend_models_without_hardcoded_scenario_results():
    script = Path(app.app.static_folder, "app.js").read_text(encoding="utf-8")

    assert "/api/scenarios/" in script
    assert "Gmail access has stopped" not in script
    assert "Agent B can still read Gmail" not in script
    assert "One previously queued email may still be sent" not in script
    assert "We cannot verify that all Gmail access has stopped" not in script
    assert "/transition" in script


def test_pilot_route_is_the_local_session_shell_and_requires_a_researcher_slot():
    client = app.app.test_client()

    page = client.get("/pilot")
    script = client.get("/static/pilot.js")
    no_session_submit = client.post("/api/pilot/response", json={"response": "YES"})

    assert page.status_code == 200
    assert b"not approved study consent" in page.data
    assert b"AuthorityLens" not in page.data
    assert b"Conventional Permission View" not in page.data
    assert b"target_local" not in page.data
    assert b"consequence_oriented" not in page.data
    assert b"seed" not in page.data.lower()
    assert script.status_code == 200
    assert b"requestAnimationFrame" in script.data
    assert b"/api/pilot/trial/rendered" in script.data
    assert no_session_submit.status_code == 401
