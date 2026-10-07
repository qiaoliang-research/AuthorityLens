"""Deterministic translation from machine authority state to consequences."""

from dataclasses import dataclass

from authority_lens import (
    AuthorityEntry,
    Effect,
    EffectiveState,
    ExternalState,
    ExternalStatus,
    PathStatus,
)


@dataclass(frozen=True)
class Capability:
    principal_id: str
    scope: str
    description: str
    authority: AuthorityEntry


@dataclass(frozen=True)
class PendingConsequence:
    effect_id: str
    description: str
    effect: Effect


@dataclass(frozen=True)
class UnknownRisk:
    principal_id: str
    scope: str | None
    description: str
    authority: AuthorityEntry | None = None
    external_states: tuple[ExternalState, ...] = ()

    @property
    def external_state(self) -> ExternalState | None:
        return self.external_states[0] if self.external_states else None


@dataclass
class ControlSummary:
    active_capabilities: list[Capability]
    residual_capabilities: list[Capability]
    pending_consequences: list[PendingConsequence]
    unknown_risks: list[UnknownRisk]


_SCOPE_WORDING = {
    "gmail.read": "read Gmail",
    "gmail.send": "send email through Gmail",
}
_SCOPE_LABEL = {
    "gmail.read": "Gmail",
    "gmail.send": "Gmail sending",
}


def _principal_name(principal_id: str, external: bool = False) -> str:
    if principal_id.startswith("agent-"):
        name = f"Agent {principal_id.removeprefix('agent-').upper()}"
    elif principal_id.startswith("external-"):
        name = f"External Agent {principal_id.removeprefix('external-').upper()}"
    else:
        name = principal_id.replace("-", " ").title()
    if external and not name.startswith("External "):
        return f"External {name}"
    return name


def _scope_wording(scope: str) -> str:
    return _SCOPE_WORDING.get(scope, f"use {scope}")


def _active_description(entry: AuthorityEntry) -> str:
    return f"{_principal_name(entry.principal_id)} can currently {_scope_wording(entry.scope)}."


def _residual_description(entry: AuthorityEntry) -> str:
    return (
        f"{_principal_name(entry.principal_id)} can still {_scope_wording(entry.scope)} "
        "despite upstream access being revoked."
    )


def _unknown_description(
    principal_id: str,
    scope: str | None,
    external_states: tuple[ExternalState, ...],
    authority: AuthorityEntry | None,
) -> str:
    external = any(state.principal_id == principal_id for state in external_states)
    principal = _principal_name(principal_id, external=external)
    capability = f"{_SCOPE_LABEL.get(scope, scope)} access" if scope else "authority"
    if authority and len(authority.principal_path) > 1 and not external:
        path = " → ".join(
            _principal_name(
                item,
                external=any(state.principal_id == item for state in external_states),
            )
            for item in authority.principal_path
        )
        return f"{principal}'s {capability} cannot currently be verified (path: {path})."
    return f"{principal}'s {capability} cannot currently be verified."


def _unknown_risks(state: EffectiveState) -> list[UnknownRisk]:
    unknown_by_id = {
        item.principal_id: item
        for item in state.unknown_states
        if item.status == ExternalStatus.UNKNOWN
    }
    risks: list[UnknownRisk] = []
    represented_unknown_ids: set[str] = set()
    unresolved_entries = list(state.unresolved_authority)
    unresolved_entries.extend(
        entry
        for entry in state.active_authority
        if entry.path_status == PathStatus.UNCERTAIN
    )

    for entry in unresolved_entries:
        path_states = tuple(
            unknown_by_id[principal_id]
            for principal_id in entry.principal_path
            if principal_id in unknown_by_id
        )
        if entry.principal_id in unknown_by_id:
            path_states = (unknown_by_id[entry.principal_id],)
            represented_unknown_ids.add(entry.principal_id)
        risks.append(
            UnknownRisk(
                principal_id=entry.principal_id,
                scope=entry.scope,
                description=_unknown_description(
                    entry.principal_id, entry.scope, path_states, entry
                ),
                authority=entry,
                external_states=path_states,
            )
        )

    for external_state in state.unknown_states:
        if (
            external_state.status == ExternalStatus.UNKNOWN
            and external_state.principal_id not in represented_unknown_ids
        ):
            source_states = (external_state,)
            risks.append(
                UnknownRisk(
                    principal_id=external_state.principal_id,
                    scope=None,
                    description=_unknown_description(
                        external_state.principal_id, None, source_states, None
                    ),
                    external_states=source_states,
                )
            )
    return sorted(risks, key=lambda item: (item.principal_id, item.scope or ""))


def _authority_order(entry: AuthorityEntry) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        entry.principal_id,
        entry.scope,
        entry.root_source_grant_id,
        entry.delegation_path,
    )


def translate_effective_state(state: EffectiveState) -> ControlSummary:
    """Translate state entries without merging authority and pending operations."""
    active_entries = [
        entry
        for entry in state.active_authority
        if entry.path_status == PathStatus.CLEAN
    ]
    residual_entries = [
        entry
        for entry in state.active_authority
        if entry.path_status == PathStatus.RESIDUAL
    ]
    active_entries.sort(key=_authority_order)
    residual_entries.sort(key=_authority_order)

    active_capabilities = [
        Capability(
            principal_id=entry.principal_id,
            scope=entry.scope,
            description=_active_description(entry),
            authority=entry,
        )
        for entry in active_entries
    ]
    residual_capabilities = [
        Capability(
            principal_id=entry.principal_id,
            scope=entry.scope,
            description=_residual_description(entry),
            authority=entry,
        )
        for entry in residual_entries
    ]
    pending_consequences = [
        PendingConsequence(
            effect_id=effect.id,
            description=(
                "One previously queued email may still be sent."
                if effect.action == "email.send"
                else f"A previously queued {effect.action} operation may still complete."
            ),
            effect=effect,
        )
        for effect in sorted(state.pending_effects, key=lambda item: item.id)
    ]
    return ControlSummary(
        active_capabilities=active_capabilities,
        residual_capabilities=residual_capabilities,
        pending_consequences=pending_consequences,
        unknown_risks=_unknown_risks(state),
    )


def render_control_summary(summary: ControlSummary) -> str:
    """Render concise deterministic text for debugging, not a user interface."""
    sections = [
        (
            "Remaining capabilities:",
            [item.description for item in summary.active_capabilities],
        ),
        (
            "Residual capabilities:",
            [item.description for item in summary.residual_capabilities],
        ),
        (
            "Pending consequences:",
            [item.description for item in summary.pending_consequences],
        ),
        (
            "Cannot verify:",
            [item.description for item in summary.unknown_risks],
        ),
    ]
    lines: list[str] = []
    for heading, items in sections:
        lines.append(heading)
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("- None.")
    return "\n".join(lines)
