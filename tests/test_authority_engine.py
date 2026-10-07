import pytest

from authority_lens import (
    AuthorityEngine,
    Delegation,
    Effect,
    EffectStatus,
    ExternalStatus,
    ExternalState,
    Grant,
    Principal,
    PrincipalType,
    PathStatus,
)


def base_engine():
    engine = AuthorityEngine()
    engine.add_principal(Principal("human", PrincipalType.HUMAN))
    engine.add_principal(Principal("agent-a", PrincipalType.AGENT, "human"))
    return engine


def test_complete_revocation_has_no_authority_effects_or_unknown_state():
    engine = base_engine()
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))
    engine.revoke_grant("agent-a", "gmail.read")

    state = engine.calculate()

    assert state.active_authority == []
    assert state.descendant_authority == []
    assert state.pending_effects == []
    assert state.unknown_states == []


def test_revoked_source_grant_leaves_explicit_residual_descendant_authority():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))
    engine.revoke_grant("agent-a", "gmail.read")

    state = engine.calculate()
    agent_b = next(item for item in state.active_authority if item.principal_id == "agent-b")

    assert not any(item.principal_id == "agent-a" for item in state.active_authority)
    assert agent_b.path_status == PathStatus.RESIDUAL
    assert agent_b.root_source_principal_id == "human"
    assert any(item.principal_id == "agent-b" for item in state.descendant_authority)


def test_queued_effect_survives_authority_revocation_with_provenance():
    engine = base_engine()
    engine.add_grant(Grant("g-human-a-send", "agent-a", "gmail.send", "human"))
    engine.add_effect(
        Effect("send-1", "agent-a", "email.send", EffectStatus.QUEUED, "gmail.send")
    )
    engine.revoke_grant("agent-a", "gmail.send")

    state = engine.calculate()

    assert not engine.can_initiate("agent-a", "gmail.send")
    assert state.pending_effects[0].required_scope == "gmail.send"
    assert state.pending_effects[0].authority_source_id == "g-human-a-send"
    assert not any(item.scope == "gmail.send" for item in state.active_authority)


def external_delegate_state(status):
    engine = base_engine()
    engine.add_principal(Principal("agent-c", PrincipalType.EXTERNAL, "agent-a"))
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ac", "agent-a", "agent-c", "gmail.read"))
    engine.revoke_grant("agent-a", "gmail.read")
    engine.set_external_state(ExternalState("agent-c", status))
    return engine


def test_confirmed_external_active_is_active_not_unresolved():
    state = external_delegate_state(ExternalStatus.CONFIRMED_ACTIVE).calculate()

    assert any(item.principal_id == "agent-c" for item in state.active_authority)
    assert not any(item.principal_id == "agent-c" for item in state.unresolved_authority)
    assert state.unknown_states == []


def test_confirmed_external_revoked_is_neither_active_nor_unresolved():
    state = external_delegate_state(ExternalStatus.CONFIRMED_REVOKED).calculate()

    assert not any(item.principal_id == "agent-c" for item in state.active_authority)
    assert not any(item.principal_id == "agent-c" for item in state.unresolved_authority)
    assert state.unknown_states == []


def test_external_unknown_is_unresolved_and_neither_active_nor_revoked():
    engine = external_delegate_state(ExternalStatus.UNKNOWN)
    state = engine.calculate()

    assert not any(item.principal_id == "agent-a" for item in state.active_authority)
    assert not any(item.principal_id == "agent-c" for item in state.active_authority)
    assert any(item.principal_id == "agent-c" for item in state.unresolved_authority)
    assert state.unknown_states == [ExternalState("agent-c", ExternalStatus.UNKNOWN)]
    assert not engine.can_initiate("agent-c", "gmail.read")


def test_multi_hop_delegation_preserves_root_and_full_lineage():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_principal(Principal("agent-c", PrincipalType.AGENT, "agent-b"))
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))
    engine.add_delegation(Delegation("d-bc", "agent-b", "agent-c", "gmail.read"))

    agent_c = next(
        item for item in engine.calculate().active_authority if item.principal_id == "agent-c"
    )

    assert agent_c.path_status == PathStatus.CLEAN
    assert agent_c.immediate_delegator == "agent-b"
    assert agent_c.root_source_principal_id == "human"
    assert agent_c.principal_path == ("human", "agent-a", "agent-b", "agent-c")
    assert agent_c.delegation_path == ("d-ab", "d-bc")


def test_explicit_delegation_revocation_removes_descendant_authority():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))

    engine.revoke_delegation("d-ab")

    state = engine.calculate()
    assert not any(item.principal_id == "agent-b" for item in state.active_authority)
    assert state.descendant_authority == []


def test_cancel_effect_removes_queued_effect_from_pending_state():
    engine = base_engine()
    engine.add_effect(
        Effect("send-1", "agent-a", "email.send", EffectStatus.QUEUED, "gmail.send", "d-ab")
    )

    engine.cancel_effect("send-1")

    assert engine.effects[0].status == EffectStatus.CANCELLED
    assert engine.calculate().pending_effects == []


def test_completed_and_cancelled_effects_are_not_pending():
    engine = base_engine()
    engine.add_effect(
        Effect("send-1", "agent-a", "email.send", EffectStatus.COMPLETED, "gmail.send")
    )
    engine.add_effect(
        Effect("send-2", "agent-a", "email.send", EffectStatus.CANCELLED, "gmail.send")
    )

    assert engine.calculate().pending_effects == []


def test_delegation_cannot_exceed_effective_authority():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))

    with pytest.raises(ValueError, match="effective authority"):
        engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.send"))





def test_revoked_upstream_delegation_marks_surviving_descendant_residual():
    engine = base_engine()
    engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
    engine.add_principal(Principal("agent-c", PrincipalType.AGENT, "agent-b"))
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ab", "agent-a", "agent-b", "gmail.read"))
    engine.add_delegation(Delegation("d-bc", "agent-b", "agent-c", "gmail.read"))
    engine.revoke_delegation("d-ab")

    agent_c = next(item for item in engine.calculate().active_authority if item.principal_id == "agent-c")

    assert agent_c.path_status == PathStatus.RESIDUAL
    assert agent_c.delegation_path == ("d-ab", "d-bc")


def external_middle_state(status):
    engine = base_engine()
    engine.add_principal(Principal("external-c", PrincipalType.EXTERNAL, "agent-a"))
    engine.add_principal(Principal("agent-d", PrincipalType.AGENT, "external-c"))
    engine.add_grant(Grant("g-human-a-read", "agent-a", "gmail.read", "human"))
    engine.add_delegation(Delegation("d-ac", "agent-a", "external-c", "gmail.read"))
    engine.set_external_state(ExternalState("external-c", ExternalStatus.CONFIRMED_ACTIVE))
    engine.add_delegation(Delegation("d-cd", "external-c", "agent-d", "gmail.read"))
    engine.set_external_state(ExternalState("external-c", status))
    return engine


def test_unknown_external_in_middle_makes_downstream_path_uncertain():
    engine = external_middle_state(ExternalStatus.UNKNOWN)
    state = engine.calculate()

    external_c = next(item for item in state.unresolved_authority if item.principal_id == "external-c")
    agent_d = next(item for item in state.unresolved_authority if item.principal_id == "agent-d")

    assert external_c.path_status == PathStatus.UNCERTAIN
    assert agent_d.path_status == PathStatus.UNCERTAIN
    assert not any(item.principal_id == "agent-d" for item in state.active_authority)
    assert not engine.can_initiate("agent-d", "gmail.read")


def test_revoked_external_in_middle_makes_surviving_downstream_residual():
    state = external_middle_state(ExternalStatus.CONFIRMED_REVOKED).calculate()

    assert not any(item.principal_id == "external-c" for item in state.active_authority)
    agent_d = next(item for item in state.active_authority if item.principal_id == "agent-d")
    assert agent_d.path_status == PathStatus.RESIDUAL


def test_effect_records_root_grant_id_as_authority_source():
    engine = base_engine()
    engine.add_grant(Grant("g-human-a-send", "agent-a", "gmail.send", "human"))
    engine.add_effect(
        Effect("send-1", "agent-a", "email.send", EffectStatus.QUEUED, "gmail.send")
    )

    effect = engine.calculate().pending_effects[0]
    assert effect.authority_source_id == "g-human-a-send"
