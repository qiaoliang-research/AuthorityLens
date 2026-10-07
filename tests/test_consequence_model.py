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
from consequence_model import render_control_summary, translate_effective_state


def base_engine():
    engine = AuthorityEngine()
    engine.add_principal(Principal("human", PrincipalType.HUMAN))
    engine.add_principal(Principal("agent-a", PrincipalType.AGENT, "human"))
    return engine


def test_complete_revocation_translates_to_empty_consequences():
    engine = base_engine()
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.revoke_grant("agent-a", "gmail.read")

    summary = translate_effective_state(engine.calculate())

    assert summary.active_capabilities == []
    assert summary.residual_capabilities == []
    assert summary.pending_consequences == []
    assert summary.unknown_risks == []


def test_residual_descendant_is_explicitly_classified():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))
    engine.revoke_grant("agent-a", "gmail.read")
    state = engine.calculate()

    summary = translate_effective_state(state)

    assert summary.active_capabilities == []
    assert len(summary.residual_capabilities) == 1
    capability = summary.residual_capabilities[0]
    assert capability.principal_id == "agent-b"
    assert capability.scope == "gmail.read"
    assert capability.authority is state.descendant_authority[0]
    assert "despite upstream access being revoked" in capability.description


def test_queued_email_is_pending_consequence_not_new_send_capability():
    engine = base_engine()
    engine.add_grant(Grant("g-send", "agent-a", "gmail.send", "human"))
    engine.add_effect(
        Effect("effect-1", "agent-a", "email.send", EffectStatus.QUEUED, "gmail.send")
    )
    engine.revoke_grant("agent-a", "gmail.send")
    state = engine.calculate()

    summary = translate_effective_state(state)

    assert summary.active_capabilities == []
    assert summary.residual_capabilities == []
    assert len(summary.pending_consequences) == 1
    consequence = summary.pending_consequences[0]
    assert consequence.effect is state.pending_effects[0]
    assert consequence.effect.required_scope == "gmail.send"
    assert consequence.effect.authority_source_id == "g-send"
    assert "queued email may still be sent" in consequence.description
    assert not any("send" in item.description for item in summary.active_capabilities)


def test_unknown_external_delegate_is_explicit_and_not_called_active_or_revoked():
    engine = base_engine()
    engine.add_principal(Principal("agent-c", PrincipalType.EXTERNAL, "agent-a"))
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ac", "agent-a", "agent-c", "gmail.read"))
    engine.revoke_grant("agent-a", "gmail.read")
    engine.set_external_state(ExternalState("agent-c", ExternalStatus.UNKNOWN))
    state = engine.calculate()

    summary = translate_effective_state(state)
    risk = next(item for item in summary.unknown_risks if item.principal_id == "agent-c")
    rendered = render_control_summary(summary).lower()

    assert risk.external_state == ExternalState("agent-c", ExternalStatus.UNKNOWN)
    assert risk.authority is state.unresolved_authority[0]
    assert "cannot currently be verified" in risk.description
    assert "cannot currently be verified" in rendered
    assert "revoked" not in rendered
    assert "confirmed active" not in rendered


def test_renderer_separates_capabilities_pending_effects_and_uncertainty():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_principal(Principal("agent-c", PrincipalType.EXTERNAL, "agent-a"))
    engine.add_grant(Grant("g-read", "agent-a", "gmail.read", "human"))
    engine.add_grant(Grant("g-send", "agent-a", "gmail.send", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))
    engine.add_delegation(Delegation("d-ac", "agent-a", "agent-c", "gmail.read"))
    engine.add_effect(
        Effect("effect-1", "agent-a", "email.send", EffectStatus.QUEUED, "gmail.send")
    )
    engine.revoke_grant("agent-a", "gmail.send")
    engine.set_external_state(ExternalState("agent-c", ExternalStatus.UNKNOWN))

    rendered = render_control_summary(translate_effective_state(engine.calculate()))

    assert "Remaining capabilities:" in rendered
    assert "Residual capabilities:" in rendered
    assert "Pending consequences:" in rendered
    assert "Cannot verify:" in rendered
    assert "Agent B can currently read Gmail." in rendered
    assert "One previously queued email may still be sent." in rendered
    assert "External Agent C's Gmail access cannot currently be verified." in rendered
