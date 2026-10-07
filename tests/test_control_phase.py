import app


def advance(scenario_id, actions):
    events = []
    for action in actions:
        payload = app.transition_scenario(scenario_id, events, action)
        events = payload["event_log"]
    return payload


def test_scenario_1_initial_state_is_before_action():
    payload = app.build_scenario_payload("complete-revocation")

    assert payload["control_phase"] == app.ControlPhase.BEFORE_ACTION
    assert payload["authority_lens"]["outcome"] is None
    assert any("Agent A can currently read Gmail" in item for item in payload["current_state"]["items"])


def test_scenario_2_delegation_does_not_start_after_action_phase():
    payload = advance("residual-delegation", ["delegate-read-agent-b"])

    assert payload["control_phase"] == app.ControlPhase.BEFORE_ACTION
    assert payload["authority_lens"]["outcome"] is None
    assert any("Agent B can currently read Gmail" in item for item in payload["current_state"]["items"])


def test_scenario_2_revoke_starts_after_action_and_keeps_partial_outcome():
    payload = advance(
        "residual-delegation",
        ["delegate-read-agent-b", "revoke-agent-a"],
    )

    assert payload["control_phase"] == app.ControlPhase.AFTER_ACTION
    assert payload["authority_lens"]["outcome"] == "partial"


def test_scenario_3_queue_is_before_action_and_pending_is_current_state():
    payload = advance("queued-action", ["queue-email"])

    assert payload["control_phase"] == app.ControlPhase.BEFORE_ACTION
    assert payload["authority_lens"]["outcome"] is None
    assert any("queued email" in item.lower() for item in payload["current_state"]["items"])


def test_scenario_3_revoke_is_after_action_with_pending_effect_outcome():
    payload = advance("queued-action", ["queue-email", "revoke-gmail-send"])

    assert payload["control_phase"] == app.ControlPhase.AFTER_ACTION
    assert payload["authority_lens"]["outcome"] == "pending_effects"


def test_scenario_4_external_delegation_is_before_action():
    payload = advance("unknown-external-agent", ["delegate-read-external-c"])

    assert payload["control_phase"] == app.ControlPhase.BEFORE_ACTION
    assert payload["authority_lens"]["outcome"] is None
    assert any("External Agent C" in item for item in payload["current_state"]["items"])


def test_scenario_4_agent_revoke_is_after_action_with_uncertain_outcome():
    payload = advance(
        "unknown-external-agent",
        ["delegate-read-external-c", "revoke-agent-a"],
    )

    assert payload["control_phase"] == app.ControlPhase.AFTER_ACTION
    assert payload["authority_lens"]["outcome"] == "uncertain"

