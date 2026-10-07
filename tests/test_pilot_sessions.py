import csv
import base64
import json
import logging
import re

import pytest

import app as webapp
from app import app
from pilot_sessions import Answer, PilotSessionError, PilotSessionManager


PRIVATE_PARTICIPANT_KEYS = {
    "expected_answer",
    "ground_truth",
    "task_id",
    "scenario_id",
    "false_safe_rule",
    "view_supported_answer",
    "view_supported_answer_by_condition",
    "condition",
    "seed",
    "question_type",
    "query_type",
    "session_run_id",
    "launch_token",
    "session_token",
}
PII_KEYS = {
    "name",
    "email",
    "ip",
    "ip_address",
    "geolocation",
    "location",
    "fingerprint",
    "participant_code",
    "participant_id",
}


def _all_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key.casefold()
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def _begin_measured(manager, token):
    assert manager.current(token)["phase"] == "information"
    manager.continue_from_information(token)
    manager.start_practice(token)
    practice = manager.current(token)
    manager.submit_practice(token, "NO")
    assert manager.current(token)["phase"] == "practice_feedback"
    manager.begin_measured(token)
    return manager.current(token)


def _researcher_headers(secret="test-researcher-secret-long-enough-for-local-tests"):
    credential = base64.b64encode(
        f"authoritylens-researcher:{secret}".encode("utf-8")
    ).decode("ascii")
    return {"Authorization": f"Basic {credential}"}


def _same_origin_headers():
    return {"Origin": "http://localhost"}


def test_participant_payload_never_contains_private_scoring_metadata():
    manager = PilotSessionManager(clock=lambda: 100.0)
    token = manager.create_session(0)

    public = manager.current(token)
    assert not PRIVATE_PARTICIPANT_KEYS.intersection(_all_keys(public))
    manager.continue_from_information(token)
    briefing = manager.current(token)
    assert not PRIVATE_PARTICIPANT_KEYS.intersection(_all_keys(briefing))
    manager.start_practice(token)
    practice = manager.current(token)
    assert not PRIVATE_PARTICIPANT_KEYS.intersection(_all_keys(practice))
    manager.submit_practice(token, "NO")
    manager.begin_measured(token)
    trial = manager.current(token)
    assert not PRIVATE_PARTICIPANT_KEYS.intersection(_all_keys(trial))
    assert not {"AuthorityLens", "Conventional Permission View"}.intersection(
        str(trial).split()
    )


def test_timer_requires_render_ack_then_measures_answer_submission():
    now = [12.0]
    manager = PilotSessionManager(clock=lambda: now[0])
    token = manager.create_session(0)
    _begin_measured(manager, token)

    with pytest.raises(PilotSessionError, match="render"):
        manager.submit_response(token, "YES")

    manager.mark_trial_rendered(token, 1)
    now[0] = 13.275
    manager.submit_response(token, "YES")
    exported = manager.export_data(token)

    assert exported["records"][0]["response_time_ms"] == 1275


def test_even_odd_seed_pairs_keep_order_and_flip_only_condition():
    manager = PilotSessionManager(clock=lambda: 100.0)
    exports = {}
    for seed in range(16):
        token = manager.create_session(seed)
        exports[seed] = manager.export_data(token)

    for even_seed in range(0, 16, 2):
        even, odd = exports[even_seed], exports[even_seed + 1]
        assert even["session"]["condition"] != odd["session"]["condition"]
        assert even["session"]["condition"] == "target_local"
        assert odd["session"]["condition"] == "consequence_oriented"
        assert [r["task_id"] for r in even["records"]] == [
            r["task_id"] for r in odd["records"]
        ]
        assert [r["scenario_id"] for r in even["records"]] == [
            r["scenario_id"] for r in odd["records"]
        ]
        assert [r["session_relative_order"] for r in even["records"]] == list(range(1, 10))
        assert even["session"]["session_run_id"] != odd["session"]["session_run_id"]
        assert re.fullmatch(r"[0-9a-f]{32}", even["session"]["session_run_id"])
    assert {item["seed"] for item in manager.researcher_sessions()} == set(range(16))
    session_conditions = [item["session"]["condition"] for item in exports.values()]
    assert session_conditions.count("target_local") == 8
    assert session_conditions.count("consequence_oriented") == 8


def test_abort_keeps_partial_session_explicitly_incomplete_and_marks_missing():
    now = [100.0]
    manager = PilotSessionManager(clock=lambda: now[0])
    token = manager.create_session(0)
    _begin_measured(manager, token)
    manager.mark_trial_rendered(token, 1)
    now[0] += 0.5
    manager.submit_response(token, "CANNOT TELL", confidence=3)
    manager.abort(token)

    export = manager.export_data(token)
    assert export["session"]["completed"] is False
    assert export["session"]["status"] == "incomplete"
    assert export["session"]["trial_count"] == 9
    assert export["session"]["response_count"] == 1
    assert export["session"]["missing_response_indicator"] is True
    assert export["records"][0]["missing_response"] is False
    assert all(record["missing_response"] for record in export["records"][1:])


def test_withdrawal_discards_submitted_answers_and_leaves_incomplete_metadata():
    manager = PilotSessionManager(clock=lambda: 100.0)
    token = manager.create_session(0)
    _begin_measured(manager, token)
    manager.mark_trial_rendered(token, 1)
    manager.submit_response(token, "YES")

    manager.withdraw(token)
    export = manager.export_data(token)

    assert export["session"]["completed"] is False
    assert export["session"]["status"] == "incomplete"
    assert export["session"]["withdrawn"] is True
    assert export["session"]["response_count"] == 0
    assert all(row["missing_response"] for row in export["records"])
    assert all(row["response"] is None for row in export["records"])


def test_response_and_confidence_validation_does_not_advance_trial():
    manager = PilotSessionManager(clock=lambda: 100.0)
    token = manager.create_session(0)
    _begin_measured(manager, token)
    manager.mark_trial_rendered(token, 1)

    with pytest.raises(ValueError, match="YES, NO, or CANNOT TELL"):
        manager.submit_response(token, "MAYBE")
    with pytest.raises(ValueError, match="confidence"):
        manager.submit_response(token, "YES", confidence=6)
    assert manager.current(token)["trial"]["order"] == 1


def test_researcher_json_and_csv_exports_are_local_and_contain_no_pii_fields():
    manager = PilotSessionManager(clock=lambda: 100.0)
    token = manager.create_session(0)
    _begin_measured(manager, token)
    for order in range(1, 10):
        manager.mark_trial_rendered(token, order)
        manager.submit_response(token, "CANNOT TELL")
    data = manager.export_data(token)
    csv_text = manager.export_csv(token)

    assert data["session"]["completed"] is True
    assert data["session"]["trial_count"] == 9
    assert not PII_KEYS.intersection(_all_keys(data))
    assert not PII_KEYS.intersection(key.casefold() for key in data["session"])
    assert "participant_code" not in csv_text.casefold()
    assert "@" not in csv_text
    csv_rows = list(csv.DictReader(csv_text.splitlines()))
    assert csv_rows and csv_rows[0]["completed"] == "True"
    assert csv_rows[0]["trial_count"] == "9"
    assert csv_rows[0]["missing_response_indicator"] == "False"


def test_practice_item_is_not_in_task_bank_or_measured_analysis():
    from pilot_study import load_task_bank

    manager = PilotSessionManager(clock=lambda: 100.0)
    token = manager.create_session(0)
    manager.continue_from_information(token)
    manager.start_practice(token)
    practice = manager.current(token)["trial"]
    assert "Calendar" in json.dumps(practice)
    assert all("Calendar" not in task["description"] for task in load_task_bank())
    manager.submit_practice(token, "NO")
    manager.begin_measured(token)
    assert manager.current(token)["trial"]["total"] == 9
    assert all("Calendar" not in record["question"] for record in manager.export_data(token)["records"])


def test_unknown_response_is_stratified_from_confirmed_remaining_false_safe():
    manager = PilotSessionManager(clock=lambda: 100.0)
    token = manager.create_session(0)
    _begin_measured(manager, token)
    for order in range(1, 10):
        manager.mark_trial_rendered(token, order)
        manager.submit_response(token, "NO")

    export = manager.export_data(token)
    by_state = export["metrics"]["false_safe_by_consequence_state"]
    assert set(by_state) == {"confirmed_remaining", "unresolved"}
    assert all("count" in item and "denominator" in item and "rate" in item for item in by_state.values())
    answered = [row for row in export["records"] if not row["missing_response"]]
    for name, truth in (("confirmed_remaining", "YES"), ("unresolved", "CANNOT TELL")):
        stratum = [
            row for row in answered
            if row["ground_truth"]["relevant_consequence_remains"] == truth
        ]
        assert by_state[name]["denominator"] == len(stratum)
        assert by_state[name]["count"] == sum(row["false_safe"] for row in stratum)


def test_only_seed_slots_zero_through_fifteen_are_accepted():
    manager = PilotSessionManager(clock=lambda: 100.0)
    for invalid in (-1, 16, True, "0", 1.5):
        with pytest.raises(ValueError, match="0 to 15"):
            manager.create_session(invalid)


def test_flask_participant_flow_has_no_seed_condition_keys_or_feedback(monkeypatch):
    monkeypatch.setenv(
        "PILOT_RESEARCHER_SECRET", "test-researcher-secret-long-enough-for-local-tests"
    )
    webapp.pilot_sessions = PilotSessionManager()
    researcher = app.test_client()
    assigned = researcher.post(
        "/pilot/researcher/start",
        data={"seed": "0"},
        headers={**_researcher_headers(), **_same_origin_headers()},
    )
    assert assigned.status_code == 200
    launch_match = re.search(r'href="(/pilot/launch/[A-Za-z0-9_-]+)"', assigned.get_data(as_text=True))
    assert launch_match
    launch_path = launch_match.group(1)
    assert "seed" not in launch_path.casefold()
    assert "condition" not in launch_path.casefold()

    client = app.test_client()
    launch = client.get(launch_path)
    assert launch.status_code == 302
    assert client.get(launch_path).status_code == 410
    page = client.get("/pilot")
    assert page.status_code == 200
    page_text = page.get_data(as_text=True)
    assert "AuthorityLens" not in page_text
    assert "Conventional Permission View" not in page_text
    assert "target_local" not in page_text
    assert "consequence_oriented" not in page_text
    assert "seed" not in page_text.casefold()

    client.post("/api/pilot/information/continue")
    client.post("/api/pilot/practice/start")
    client.post("/api/pilot/practice/submit", json={"response": "NO"})
    client.post("/api/pilot/practice/continue")
    trial = client.get("/api/pilot/state").get_json()
    assert trial["phase"] == "trial"
    assert not PRIVATE_PARTICIPANT_KEYS.intersection(_all_keys(trial))
    assert "scenario_context" in trial["trial"]
    client.post("/api/pilot/trial/rendered", json={"order": 1})
    submitted = client.post("/api/pilot/response", json={"response": "YES"})
    assert submitted.status_code == 200
    assert "correct" not in json.dumps(submitted.get_json()).casefold()
    assert client.get("/api/pilot/task-catalog").status_code == 404


def test_participant_session_never_receives_both_conditions_or_condition_labels():
    for seed in (0, 1):
        manager = PilotSessionManager(clock=lambda: 100.0)
        token = manager.create_session(seed)
        _begin_measured(manager, token)
        for order in range(1, 10):
            payload = manager.current(token)
            serialized = json.dumps(payload)
            assert "target_local" not in serialized
            assert "consequence_oriented" not in serialized
            assert "Conventional Permission View" not in serialized
            assert '"AuthorityLens"' not in serialized
            assert "condition" not in {key.casefold() for key in _all_keys(payload)}
            manager.mark_trial_rendered(token, order)
            manager.submit_response(token, "CANNOT TELL")
        exported = manager.export_data(token)
        assert {record["condition"] for record in exported["records"]} == {
            exported["session"]["condition"]
        }


def test_researcher_export_routes_download_private_scoring_data(monkeypatch):
    monkeypatch.setenv(
        "PILOT_RESEARCHER_SECRET", "test-researcher-secret-long-enough-for-local-tests"
    )
    webapp.pilot_sessions = PilotSessionManager()
    client = app.test_client()
    assigned = client.post(
        "/pilot/researcher/start",
        data={"seed": "0"},
        headers={**_researcher_headers(), **_same_origin_headers()},
    )
    launch_match = re.search(r'href="(/pilot/launch/[A-Za-z0-9_-]+)"', assigned.get_data(as_text=True))
    assert launch_match
    participant = app.test_client()
    participant.get(launch_match.group(1))
    for endpoint, body in (
        ("/api/pilot/information/continue", None),
        ("/api/pilot/practice/start", None),
        ("/api/pilot/practice/submit", {"response": "NO"}),
        ("/api/pilot/practice/continue", None),
    ):
        participant.post(endpoint, json=body)
    for order in range(1, 10):
        participant.get("/api/pilot/state")
        participant.post("/api/pilot/trial/rendered", json={"order": order})
        participant.post("/api/pilot/response", json={"response": "CANNOT TELL"})
    researcher = client.get("/pilot/researcher", headers=_researcher_headers())
    token_match = re.search(r'data-session-token="([^"]+)"', researcher.get_data(as_text=True))
    assert token_match
    token = token_match.group(1)

    json_response = client.get(
        f"/pilot/researcher/export/{token}.json", headers=_researcher_headers()
    )
    csv_response = client.get(
        f"/pilot/researcher/export/{token}.csv", headers=_researcher_headers()
    )
    assert json_response.status_code == 200
    assert json_response.headers["Content-Disposition"].endswith(".json\"")
    assert json_response.get_json()["session"]["completed"] is True
    assert csv_response.status_code == 200
    assert "attachment" in csv_response.headers["Content-Disposition"]


def test_researcher_routes_reject_unauthenticated_and_participant_only_clients(monkeypatch):
    monkeypatch.setenv(
        "PILOT_RESEARCHER_SECRET", "test-researcher-secret-long-enough-for-local-tests"
    )
    webapp.pilot_sessions = PilotSessionManager()
    token = webapp.pilot_sessions.create_session(0)
    participant = app.test_client()
    participant.set_cookie(app.config["PILOT_SESSION_COOKIE"], token)

    assert participant.get("/pilot/researcher").status_code == 401
    assert participant.post(
        "/pilot/researcher/start",
        data={"seed": "0"},
        headers=_same_origin_headers(),
    ).status_code == 401
    assert participant.get(f"/pilot/researcher/export/{token}.json").status_code == 401
    assert participant.get(f"/pilot/researcher/export/{token}.csv").status_code == 401


def test_researcher_secret_missing_fails_closed(monkeypatch):
    monkeypatch.delenv("PILOT_RESEARCHER_SECRET", raising=False)
    assert app.test_client().get("/pilot/researcher").status_code == 503


def test_malformed_basic_credentials_are_rejected_without_exposing_routes(monkeypatch):
    monkeypatch.setenv(
        "PILOT_RESEARCHER_SECRET", "test-researcher-secret-long-enough-for-local-tests"
    )
    malformed = base64.b64encode(b"authoritylens-researcher").decode("ascii")
    response = app.test_client().get(
        "/pilot/researcher", headers={"Authorization": f"Basic {malformed}"}
    )

    assert response.status_code == 401


def test_launch_token_is_one_time_and_participant_payload_has_no_private_metadata():
    manager = PilotSessionManager(clock=lambda: 10.0)
    session_token = manager.create_session(0)
    launch_token = manager.create_launch_token(session_token)

    assert manager.consume_launch_token(launch_token) == session_token
    assert manager.consume_launch_token(launch_token) is None
    assert not PRIVATE_PARTICIPANT_KEYS.intersection(
        _all_keys(manager.current(session_token))
    )


def test_launch_token_expires_and_is_consumed():
    now = [10.0]
    manager = PilotSessionManager(clock=lambda: now[0])
    session_token = manager.create_session(0)
    launch_token = manager.create_launch_token(session_token)
    now[0] += manager.LAUNCH_TOKEN_TTL_SECONDS + 1

    assert manager.consume_launch_token(launch_token) is None
    assert manager.consume_launch_token(launch_token) is None


def test_common_briefing_does_not_claim_permission_panel_lists_every_principal():
    manager = PilotSessionManager(clock=lambda: 10.0)
    token = manager.create_session(0)
    briefing = manager.continue_from_information(token)["message"]

    assert "The scenario context names the modeled actors relevant to the question" in briefing
    assert "The interface panel may summarize only part of the current system state" in briefing
    assert "complete modeled set" not in briefing


def test_neutral_scenario_context_is_identical_between_conditions():
    manager = PilotSessionManager(clock=lambda: 10.0)
    paired_payloads = []
    for seed in (0, 1):
        token = manager.create_session(seed)
        _begin_measured(manager, token)
        contexts = []
        for order in range(1, 10):
            current = manager.current(token)
            contexts.append(current["trial"]["scenario_context"])
            manager.mark_trial_rendered(token, order)
            manager.submit_response(token, "CANNOT TELL")
        paired_payloads.append(contexts)

    assert paired_payloads[0] == paired_payloads[1]


def test_matched_transfer_pair_contexts_are_identical_and_neutral():
    from pilot_context import build_neutral_scenario_contexts
    from pilot_study import load_task_bank

    tasks = load_task_bank()
    contexts = build_neutral_scenario_contexts(tasks)
    pairs = {}
    for task in tasks:
        if task.get("matched_pair"):
            pairs.setdefault(task["matched_pair"], []).append(task)

    forbidden = {"active", "residual", "uncertain", "unknown", "pending", "cancelled", "canceled"}
    for pair in pairs.values():
        assert len(pair) == 2
        first = contexts[pair[0]["task_id"]]
        second = contexts[pair[1]["task_id"]]
        assert first == second
        words = set(re.findall(r"[a-z]+", first.casefold()))
        assert not forbidden.intersection(words)

    assert "Agent B" in contexts["T01"] and "Agent C" in contexts["T01"]
    assert "External Agent C" in contexts["T05"]
    assert "queued" not in contexts["T03"].casefold()
    assert "cancel" not in contexts["T04"].casefold()


def test_launch_urls_are_one_time_and_do_not_encode_seed_or_condition(monkeypatch):
    monkeypatch.setenv(
        "PILOT_RESEARCHER_SECRET", "test-researcher-secret-long-enough-for-local-tests"
    )
    webapp.pilot_sessions = PilotSessionManager()
    client = app.test_client()
    response = client.post(
        "/pilot/researcher/start",
        data={"seed": "3"},
        headers={**_researcher_headers(), **_same_origin_headers()},
    )
    link = re.search(r'href="(/pilot/launch/[A-Za-z0-9_-]+)"', response.get_data(as_text=True)).group(1)
    assert re.search(r"/pilot/launch/[A-Za-z0-9_-]+$", link)
    assert "target_local" not in link
    assert "consequence_oriented" not in link

    participant = app.test_client()
    assert participant.get(link).status_code == 302
    assert participant.get(link).status_code == 410


def test_reused_seed_exports_have_distinct_run_id_filenames(monkeypatch):
    monkeypatch.setenv(
        "PILOT_RESEARCHER_SECRET", "test-researcher-secret-long-enough-for-local-tests"
    )
    webapp.pilot_sessions = PilotSessionManager()
    manager = webapp.pilot_sessions
    tokens = [manager.create_session(2) for _ in range(2)]
    client = app.test_client()
    filenames = []
    for token in tokens:
        response = client.get(
            f"/pilot/researcher/export/{token}.json",
            headers=_researcher_headers(),
        )
        assert response.status_code == 200
        filenames.append(response.headers["Content-Disposition"])

    assert filenames[0] != filenames[1]
    assert all("-slot-03.json" in name for name in filenames)
    assert all(re.search(r"authoritylens-pilot-[0-9a-f]{32}-slot-03\.json", name) for name in filenames)


def test_werkzeug_access_logger_is_disabled_for_no_ip_logging():
    assert logging.getLogger("werkzeug").disabled is True
