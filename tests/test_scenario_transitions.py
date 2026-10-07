import app


SCENARIO_2_DELEGATE = "delegate-read-agent-b"
SCENARIO_2_REVOKE = "revoke-agent-a"
SCENARIO_3_QUEUE = "queue-email"
SCENARIO_3_REVOKE = "revoke-gmail-send"
SCENARIO_3_CANCEL = "cancel-email"
SCENARIO_4_DELEGATE = "delegate-read-external-c"
SCENARIO_4_REQUEST = "send-revocation-request"
SCENARIO_4_REVOKE_C = "confirm-c-revoked"
SCENARIO_4_ACTIVE_C = "confirm-c-active"


def test_scenario_1_revoke_completes_after_initial_active_state():
    initial = app.build_scenario_payload("complete-revocation")
    assert initial["baseline"]["access_status"] == "ON"
    assert initial["available_actions"] == [
        {"id": "revoke-gmail-access", "label": "Revoke Gmail Access"}
    ]

    revoked = app.transition_scenario(
        "complete-revocation", initial["event_log"], "revoke-gmail-access"
    )
    assert revoked["baseline"]["access_status"] == "OFF"
    assert revoked["authority_lens"]["outcome"] == "complete"
    assert revoked["system_state"]["active_authority"] == []
    assert revoked["system_state"]["pending_effects"] == []
    assert revoked["system_state"]["unknown_states"] == []


def test_scenario_2_agent_b_has_no_authority_before_delegation():
    payload = app.build_scenario_payload("residual-delegation")

    assert not any(
        item["principal_id"] == "agent-b"
        for item in payload["system_state"]["active_authority"]
    )
    assert not any(
        item["principal_id"] == "agent-b"
        for item in payload["system_state"]["residual_authority"]
    )


def test_scenario_2_delegation_then_revoke_transitions_clean_to_residual():
    delegated = app.transition_scenario(
        "residual-delegation", [], SCENARIO_2_DELEGATE
    )
    b_active = next(
        item for item in delegated["system_state"]["active_authority"]
        if item["principal_id"] == "agent-b"
    )
    assert b_active["path_status"] == "clean"

    revoked = app.transition_scenario(
        "residual-delegation",
        delegated["event_log"],
        SCENARIO_2_REVOKE,
    )
    b_residual = next(
        item for item in revoked["system_state"]["residual_authority"]
        if item["principal_id"] == "agent-b"
    )
    assert b_residual["path_status"] == "residual"
    assert revoked["authority_lens"]["outcome"] == "partial"
    assert revoked["baseline"]["access_status"] == "OFF"


def test_scenario_3_queue_then_revoke_removes_new_authority_but_keeps_effect():
    queued = app.transition_scenario("queued-action", [], SCENARIO_3_QUEUE)
    assert len(queued["system_state"]["pending_effects"]) == 1

    revoked = app.transition_scenario(
        "queued-action", queued["event_log"], SCENARIO_3_REVOKE
    )
    assert not any(
        item["scope"] == "gmail.send"
        for item in revoked["system_state"]["active_authority"]
    )
    assert len(revoked["system_state"]["pending_effects"]) == 1
    assert revoked["authority_lens"]["outcome"] == "pending_effects"

    cancelled = app.transition_scenario(
        "queued-action", revoked["event_log"], SCENARIO_3_CANCEL
    )
    assert cancelled["system_state"]["pending_effects"] == []
    assert cancelled["authority_lens"]["outcome"] == "complete"
    assert cancelled["baseline"]["access_status"] == "OFF"
    assert cancelled["baseline"]["resource_label"] == "Gmail Sending"
    assert cancelled["baseline"]["label"] == "Gmail Sending: OFF"


def scenario_4_pending_external_confirmation():
    events = [SCENARIO_4_DELEGATE, SCENARIO_2_REVOKE, SCENARIO_4_REQUEST]
    return app.build_scenario_payload("unknown-external-agent", events)


def test_scenario_4_unknown_external_keeps_uncertain_outcome():
    payload = scenario_4_pending_external_confirmation()

    assert payload["authority_lens"]["outcome"] == "uncertain"
    assert payload["system_state"]["unknown_states"] == [
        {"principal_id": "agent-c", "status": "unknown"}
    ]


def test_scenario_4_confirm_external_revoked_removes_unknown_and_completes():
    pending = scenario_4_pending_external_confirmation()
    revoked = app.transition_scenario(
        "unknown-external-agent", pending["event_log"], SCENARIO_4_REVOKE_C
    )

    assert revoked["system_state"]["unknown_states"] == []
    assert revoked["system_state"]["residual_authority"] == []
    assert revoked["authority_lens"]["outcome"] == "complete"


def test_scenario_4_confirm_external_active_preserves_residual_authority():
    pending = scenario_4_pending_external_confirmation()
    active = app.transition_scenario(
        "unknown-external-agent", pending["event_log"], SCENARIO_4_ACTIVE_C
    )

    assert active["system_state"]["unknown_states"] == []
    c_residual = next(
        item for item in active["system_state"]["residual_authority"]
        if item["principal_id"] == "agent-c"
    )
    assert c_residual["path_status"] == "residual"
    assert active["authority_lens"]["outcome"] == "partial"
    assert active["baseline"]["access_status"] == "OFF"


def test_reset_returns_scenario_to_canonical_initial_state():
    client = app.app.test_client()
    response = client.post(
        "/api/scenarios/residual-delegation/transition",
        json={"events": [], "action": SCENARIO_2_DELEGATE},
    )
    assert response.status_code == 200
    assert response.get_json()["event_log"] == [SCENARIO_2_DELEGATE]

    reset = client.post("/api/scenarios/residual-delegation/reset")
    payload = reset.get_json()
    assert reset.status_code == 200
    assert payload["event_log"] == []
    assert not any(
        item["principal_id"] == "agent-b"
        for item in payload["system_state"]["active_authority"]
    )
