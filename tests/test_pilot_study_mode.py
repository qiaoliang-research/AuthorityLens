import base64

import pytest

import app as webapp
from app import app
from pilot_sessions import PilotSessionManager


RESEARCHER_SECRET = "test-researcher-secret-long-enough-for-local-tests"


def _researcher_headers():
    token = base64.b64encode(
        f"authoritylens-researcher:{RESEARCHER_SECRET}".encode("utf-8")
    ).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _assert_no_scenario_payload(response):
    text = response.get_data(as_text=True).casefold()
    assert "baseline" not in text
    assert "authority_lens" not in text
    assert "complete-revocation" not in text


def test_normal_development_mode_still_serves_ordinary_demo(monkeypatch):
    monkeypatch.delenv("PILOT_STUDY_MODE", raising=False)

    response = app.test_client().get("/")

    assert response.status_code == 200
    assert "AuthorityLens" in response.get_data(as_text=True)


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "Yes", "on", "ON"])
def test_study_mode_flag_accepts_truthy_values(monkeypatch, value):
    monkeypatch.setenv("PILOT_STUDY_MODE", value)

    assert webapp.pilot_study_mode_enabled() is True


def test_study_mode_flag_treats_other_values_as_disabled(monkeypatch):
    for value in ("", "0", "false", "no", "off", "enabled"):
        monkeypatch.setenv("PILOT_STUDY_MODE", value)
        assert webapp.pilot_study_mode_enabled() is False


def test_study_mode_blocks_root_without_demo_content(monkeypatch):
    monkeypatch.setenv("PILOT_STUDY_MODE", "1")

    response = app.test_client().get("/")

    assert response.status_code == 404
    _assert_no_scenario_payload(response)


def test_study_mode_blocks_scenario_list_and_detail_without_payload(monkeypatch):
    monkeypatch.setenv("PILOT_STUDY_MODE", "yes")
    client = app.test_client()

    for path in ("/api/scenarios", "/api/scenarios/complete-revocation"):
        response = client.get(path)
        assert response.status_code == 404
        _assert_no_scenario_payload(response)


def test_study_mode_blocks_scenario_transition_and_reset(monkeypatch):
    monkeypatch.setenv("PILOT_STUDY_MODE", "on")
    client = app.test_client()

    transition = client.post(
        "/api/scenarios/residual-delegation/transition",
        json={"events": [], "action": "delegate-read-agent-b"},
    )
    reset = client.post("/api/scenarios/residual-delegation/reset")

    assert transition.status_code == 404
    assert reset.status_code == 404
    _assert_no_scenario_payload(transition)
    _assert_no_scenario_payload(reset)


def test_study_mode_keeps_participant_page_and_api_available(monkeypatch):
    monkeypatch.setenv("PILOT_STUDY_MODE", "1")
    monkeypatch.setattr(webapp, "pilot_sessions", PilotSessionManager())
    client = app.test_client()
    token = webapp.pilot_sessions.create_session(0)
    client.set_cookie(app.config["PILOT_SESSION_COOKIE"], token)

    page = client.get("/pilot")
    state = client.get("/api/pilot/state")
    continued = client.post("/api/pilot/information/continue")

    assert page.status_code == 200
    assert state.status_code == 200
    assert state.get_json()["phase"] == "information"
    assert continued.status_code == 200
    assert continued.get_json()["phase"] == "briefing"
    assert "study_mode" not in str(state.get_json()).casefold()


def test_study_mode_keeps_researcher_routes_behind_existing_auth(monkeypatch):
    monkeypatch.setenv("PILOT_STUDY_MODE", "1")
    monkeypatch.setenv("PILOT_RESEARCHER_SECRET", RESEARCHER_SECRET)
    client = app.test_client()

    unauthenticated = client.get("/pilot/researcher")
    authenticated = client.get("/pilot/researcher", headers=_researcher_headers())

    assert unauthenticated.status_code == 401
    assert authenticated.status_code == 200
    assert "Participant session assignment" in authenticated.get_data(as_text=True)
