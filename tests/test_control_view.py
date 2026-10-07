from authority_lens import (
    AuthorityEngine,
    Delegation,
    Effect,
    EffectStatus,
    ExternalState,
    ExternalStatus,
    Grant,
    Principal,
    PrincipalType,
)
from consequence_model import translate_effective_state
from control_view import (
    ControlContext,
    ControlOutcome,
    build_authority_lens_control_view,
    build_baseline_control_view,
    build_control_view,
)


def base_engine():
    engine = AuthorityEngine()
    engine.add_principal(Principal("human", PrincipalType.HUMAN))
    engine.add_principal(Principal("agent-a", PrincipalType.AGENT, "human"))
    return engine


def revoke_context():
    return ControlContext("Gmail", "revoke", "agent-a", action_confirmed=True)


def test_complete_revoke_yields_complete_and_baseline_off():
    engine = base_engine()
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.revoke_grant("agent-a", "gmail.read")
    view = build_control_view(revoke_context(), translate_effective_state(engine.calculate()))

    assert view.outcome == ControlOutcome.COMPLETE
    assert view.headline == "Gmail access has stopped."
    assert build_baseline_control_view(view).label == "Gmail Access: OFF"


def test_residual_descendant_yields_partial_in_both_views():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))
    engine.revoke_grant("agent-a", "gmail.read")
    view = build_control_view(revoke_context(), translate_effective_state(engine.calculate()))

    assert view.outcome == ControlOutcome.PARTIAL
    assert view.headline == "Gmail access is not fully stopped."
    assert view.residual_items[0].principal_id == "agent-b"
    assert build_baseline_control_view(view).label == "Gmail Access: OFF"
    detailed = build_authority_lens_control_view(view)
    assert detailed.residual_items == view.residual_items
    assert detailed.residual_items[0].authority.path_status.value == "residual"


def test_queued_effect_yields_pending_effects_not_current_send_authority():
    engine = base_engine()
    engine.add_grant(Grant("g-send", "agent-a", "gmail.send", "human"))
    engine.add_effect(
        Effect("send-1", "agent-a", "email.send", EffectStatus.QUEUED, "gmail.send")
    )
    engine.revoke_grant("agent-a", "gmail.send")
    view = build_control_view(revoke_context(), translate_effective_state(engine.calculate()))

    assert view.outcome == ControlOutcome.PENDING_EFFECTS
    assert view.headline == "New Gmail actions are blocked, but an earlier action may still complete."
    assert view.active_items == ()
    assert len(view.pending_items) == 1
    assert "queued email may still be sent" in view.pending_items[0].description
    assert build_baseline_control_view(view).label == "Gmail Access: OFF"


def test_unknown_external_delegate_yields_uncertain_and_baseline_unknown():
    engine = base_engine()
    engine.add_principal(Principal("agent-c", PrincipalType.EXTERNAL, "agent-a"))
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ac", "agent-a", "agent-c", "gmail.read"))
    engine.revoke_grant("agent-a", "gmail.read")
    engine.set_external_state(ExternalState("agent-c", ExternalStatus.UNKNOWN))
    view = build_control_view(revoke_context(), translate_effective_state(engine.calculate()))

    assert view.outcome == ControlOutcome.UNCERTAIN
    assert view.headline == "We cannot verify that all Gmail access has stopped."
    assert view.unknown_items
    assert build_baseline_control_view(view).label == "Gmail Access: OFF"
    detailed = build_authority_lens_control_view(view)
    assert detailed.unknown_items == view.unknown_items
    assert "cannot currently be verified" in detailed.unknown_items[0].description


def test_mixed_residual_authority_and_pending_effects_are_both_preserved():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.add_grant(Grant("g-send", "agent-a", "gmail.send", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))
    engine.add_effect(
        Effect("send-1", "agent-a", "email.send", EffectStatus.QUEUED, "gmail.send")
    )
    engine.revoke_grant("agent-a", "gmail.read")
    engine.revoke_grant("agent-a", "gmail.send")
    view = build_control_view(revoke_context(), translate_effective_state(engine.calculate()))
    detailed = build_authority_lens_control_view(view)

    assert view.outcome == ControlOutcome.PARTIAL
    assert len(detailed.residual_items) == 1
    assert len(detailed.pending_items) == 1
    assert detailed.residual_items[0] == view.residual_items[0]
    assert detailed.pending_items[0] == view.pending_items[0]


def test_empty_summary_without_revoke_context_does_not_claim_complete():
    context = ControlContext("Gmail", "inspect", "agent-a")
    empty_summary = translate_effective_state(base_engine().calculate())

    view = build_control_view(context, empty_summary)

    assert view.outcome == ControlOutcome.UNCERTAIN
    assert "has stopped" not in view.headline


def test_unknown_target_principal_makes_local_baseline_unknown():
    engine = base_engine()
    engine.add_principal(Principal("agent-c", PrincipalType.EXTERNAL, "agent-a"))
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ac", "agent-a", "agent-c", "gmail.read"))
    engine.set_external_state(ExternalState("agent-c", ExternalStatus.UNKNOWN))
    context = ControlContext("Gmail", "revoke", "agent-c", action_confirmed=True)
    view = build_control_view(context, translate_effective_state(engine.calculate()))

    assert view.outcome == ControlOutcome.UNCERTAIN
    assert build_baseline_control_view(view).label == "Gmail Access: UNKNOWN"


def test_direct_active_target_makes_local_baseline_on():
    engine = base_engine()
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    view = build_control_view(revoke_context(), translate_effective_state(engine.calculate()))

    assert view.outcome == ControlOutcome.PARTIAL
    assert build_baseline_control_view(view).label == "Gmail Access: ON"


def test_unconfirmed_revoke_with_empty_state_is_uncertain():
    context = ControlContext("Gmail", "revoke", "agent-a", action_confirmed=False)
    view = build_control_view(context, translate_effective_state(base_engine().calculate()))

    assert view.outcome == ControlOutcome.UNCERTAIN
    assert view.headline == "We cannot verify that all Gmail access has stopped."


def test_confirmed_revoke_with_empty_relevant_state_is_complete():
    context = ControlContext("Gmail", "revoke", "agent-a", action_confirmed=True)
    view = build_control_view(context, translate_effective_state(base_engine().calculate()))

    assert view.outcome == ControlOutcome.COMPLETE
    assert view.headline == "Gmail access has stopped."
