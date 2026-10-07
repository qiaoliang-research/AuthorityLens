"""Structured benchmark facts derived from the engine's EffectiveState."""

from dataclasses import dataclass
from enum import StrEnum

from authority_lens import EffectiveState, ExternalStatus, PathStatus
from control_view import ControlContext


class FactType(StrEnum):
    ACTIVE_CAPABILITY = "active_capability"
    RESIDUAL_CAPABILITY = "residual_capability"
    PENDING_EFFECT = "pending_effect"
    UNKNOWN_AUTHORITY = "unknown_authority"
    COMPLETE_REVOCATION = "complete_revocation"
    TARGET_PERMISSION = "target_permission"


@dataclass(frozen=True)
class Fact:
    fact_type: FactType
    principal_id: str | None = None
    resource: str | None = None
    action: str | None = None
    scope: str | None = None
    status: str | None = None
    effect_id: str | None = None
    authority_source_id: str | None = None
    principal_path: tuple[str, ...] = ()
    delegation_path: tuple[str, ...] = ()
    path_status: str | None = None


def _scope_details(scope: str | None) -> tuple[str | None, str | None]:
    if not scope or "." not in scope:
        return None, None
    resource, action = scope.split(".", 1)
    return resource, action


def _relevant(scope: str | None, context: ControlContext) -> bool:
    if scope is None:
        return True
    resource, _ = _scope_details(scope)
    return resource is not None and resource.casefold() == context.resource.casefold()


def _authority_fact(fact_type: FactType, entry) -> Fact:
    resource, action = _scope_details(entry.scope)
    return Fact(
        fact_type=fact_type,
        principal_id=entry.principal_id,
        resource=resource,
        action=action,
        scope=entry.scope,
        authority_source_id=entry.root_source_grant_id,
        principal_path=entry.principal_path,
        delegation_path=entry.delegation_path,
        path_status=entry.path_status.value,
    )


def derive_ground_truth_facts(
    state: EffectiveState,
    context: ControlContext,
) -> tuple[Fact, ...]:
    """Create ground-truth facts from engine output and confirmed action context."""
    facts: set[Fact] = set()
    represented_unknowns: set[str] = set()
    relevant_active = []
    relevant_residual = []
    relevant_unresolved = []

    for entry in state.active_authority:
        if not _relevant(entry.scope, context):
            continue
        if entry.path_status == PathStatus.CLEAN:
            facts.add(_authority_fact(FactType.ACTIVE_CAPABILITY, entry))
            relevant_active.append(entry)
        elif entry.path_status == PathStatus.RESIDUAL:
            facts.add(_authority_fact(FactType.RESIDUAL_CAPABILITY, entry))
            relevant_residual.append(entry)
        elif entry.path_status == PathStatus.UNCERTAIN:
            facts.add(_authority_fact(FactType.UNKNOWN_AUTHORITY, entry))
            represented_unknowns.add(entry.principal_id)
            relevant_unresolved.append(entry)

    for entry in state.unresolved_authority:
        if _relevant(entry.scope, context):
            facts.add(_authority_fact(FactType.UNKNOWN_AUTHORITY, entry))
            represented_unknowns.add(entry.principal_id)
            relevant_unresolved.append(entry)

    for external_state in state.unknown_states:
        if (
            external_state.status != ExternalStatus.UNKNOWN
            or external_state.principal_id in represented_unknowns
        ):
            continue
        facts.add(
            Fact(
                fact_type=FactType.UNKNOWN_AUTHORITY,
                principal_id=external_state.principal_id,
                resource=context.resource.casefold(),
                status=external_state.status.value,
                principal_path=(external_state.principal_id,),
                path_status=PathStatus.UNCERTAIN.value,
            )
        )

    for effect in state.pending_effects:
        if not _relevant(effect.required_scope, context):
            continue
        resource, _ = _scope_details(effect.required_scope)
        facts.add(
            Fact(
                fact_type=FactType.PENDING_EFFECT,
                principal_id=effect.principal_id,
                resource=resource,
                action=effect.action,
                scope=effect.required_scope,
                status=effect.status.value,
                effect_id=effect.id,
                authority_source_id=effect.authority_source_id,
            )
        )

    relevant_unknown_states = [
        item for item in state.unknown_states
        if item.status == ExternalStatus.UNKNOWN
    ]
    target_entries = [
        entry
        for entry in (*state.active_authority, *state.unresolved_authority)
        if entry.principal_id == context.target_principal and _relevant(entry.scope, context)
    ]
    target_unknown = any(
        entry.path_status == PathStatus.UNCERTAIN for entry in target_entries
    ) or any(
        item.principal_id == context.target_principal
        for item in relevant_unknown_states
    )
    if target_unknown:
        target_status = "unknown"
    elif any(
        entry.path_status in (PathStatus.CLEAN, PathStatus.RESIDUAL)
        for entry in target_entries
    ):
        target_status = "on"
    else:
        target_status = "off"
    facts.add(
        Fact(
            fact_type=FactType.TARGET_PERMISSION,
            principal_id=context.target_principal,
            resource=context.resource.casefold(),
            status=target_status,
        )
    )

    relevant_pending = [
        effect for effect in state.pending_effects
        if _relevant(effect.required_scope, context)
    ]
    confirmed_revoke = (
        context.requested_action.casefold() == "revoke"
        and context.action_confirmed
    )
    if (
        confirmed_revoke
        and not relevant_active
        and not relevant_residual
        and not relevant_unresolved
        and not relevant_pending
        # ExternalState has no scope field, so unknown states are conservatively
        # relevant to the resource named by this control context.
        and not relevant_unknown_states
    ):
        facts.add(
            Fact(
                fact_type=FactType.COMPLETE_REVOCATION,
                resource=context.resource.casefold(),
            )
        )

    return tuple(sorted(facts, key=fact_sort_key))


def fact_sort_key(fact: Fact) -> tuple:
    return (
        fact.fact_type.value,
        fact.principal_id or "",
        fact.scope or "",
        fact.effect_id or "",
        fact.status or "",
        fact.principal_path,
        fact.delegation_path,
    )
