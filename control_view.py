"""Presentation-oriented control outcomes derived from frozen consequence state."""

from dataclasses import dataclass
from enum import StrEnum

from consequence_model import Capability, ControlSummary, PendingConsequence, UnknownRisk


class ControlOutcome(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    PENDING_EFFECTS = "pending_effects"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class ControlContext:
    resource: str
    requested_action: str
    target_principal: str
    action_confirmed: bool = False


@dataclass(frozen=True)
class ControlView:
    context: ControlContext
    outcome: ControlOutcome
    headline: str
    active_items: tuple[Capability, ...]
    residual_items: tuple[Capability, ...]
    pending_items: tuple[PendingConsequence, ...]
    unknown_items: tuple[UnknownRisk, ...]


@dataclass(frozen=True)
class BaselineControlView:
    context: ControlContext
    access_status: str

    @property
    def label(self) -> str:
        return f"{self.context.resource} Access: {self.access_status}"


@dataclass(frozen=True)
class AuthorityLensControlView:
    context: ControlContext
    outcome: ControlOutcome
    headline: str
    active_items: tuple[Capability, ...]
    residual_items: tuple[Capability, ...]
    pending_items: tuple[PendingConsequence, ...]
    unknown_items: tuple[UnknownRisk, ...]


def _matches_resource(resource: str, scope: str | None) -> bool:
    if scope is None:
        # A scope-less external unknown could include the resource being controlled.
        return True
    resource_key = resource.casefold().replace(" ", "_")
    return scope.casefold().startswith(f"{resource_key}.")


def _item_order(item: Capability) -> tuple[str, str, str, tuple[str, ...]]:
    return (
        item.principal_id,
        item.scope,
        item.authority.root_source_grant_id,
        item.authority.delegation_path,
    )


def _headline(context: ControlContext, outcome: ControlOutcome, has_active: bool) -> str:
    resource = context.resource
    if context.requested_action.casefold() != "revoke":
        return f"A revoke result cannot be inferred from the requested {context.requested_action} action."
    if outcome == ControlOutcome.COMPLETE:
        return f"{resource} access has stopped."
    if outcome == ControlOutcome.PARTIAL:
        return f"{resource} access is not fully stopped."
    if outcome == ControlOutcome.PENDING_EFFECTS:
        if has_active:
            return f"Earlier {resource} actions may still complete, and some {resource} capabilities remain active."
        return f"New {resource} actions are blocked, but an earlier action may still complete."
    return f"We cannot verify that all {resource} access has stopped."


def build_control_view(context: ControlContext, summary: ControlSummary) -> ControlView:
    """Apply the control context and deterministic precedence to a consequence summary."""
    active_items = tuple(
        sorted(
            (item for item in summary.active_capabilities if _matches_resource(context.resource, item.scope)),
            key=_item_order,
        )
    )
    residual_items = tuple(
        sorted(
            (item for item in summary.residual_capabilities if _matches_resource(context.resource, item.scope)),
            key=_item_order,
        )
    )
    pending_items = tuple(
        sorted(
            (
                item
                for item in summary.pending_consequences
                if _matches_resource(context.resource, item.effect.required_scope)
            ),
            key=lambda item: item.effect_id,
        )
    )
    unknown_items = tuple(
        sorted(
            (item for item in summary.unknown_risks if _matches_resource(context.resource, item.scope)),
            key=lambda item: (item.principal_id, item.scope or ""),
        )
    )

    if unknown_items:
        outcome = ControlOutcome.UNCERTAIN
    elif residual_items:
        outcome = ControlOutcome.PARTIAL
    elif pending_items:
        outcome = ControlOutcome.PENDING_EFFECTS
    elif active_items:
        outcome = ControlOutcome.PARTIAL
    elif (
        context.requested_action.casefold() == "revoke"
        and context.action_confirmed
    ):
        outcome = ControlOutcome.COMPLETE
    else:
        # An empty state and a request alone do not prove the action completed.
        outcome = ControlOutcome.UNCERTAIN

    return ControlView(
        context=context,
        outcome=outcome,
        headline=_headline(context, outcome, has_active=bool(active_items)),
        active_items=active_items,
        residual_items=residual_items,
        pending_items=pending_items,
        unknown_items=unknown_items,
    )


def build_baseline_control_view(view: ControlView) -> BaselineControlView:
    """Show only the target's local permission state, not system-wide consequences."""
    target = view.context.target_principal
    target_unknown = any(item.principal_id == target for item in view.unknown_items)
    target_authority = any(
        item.principal_id == target
        for item in (*view.active_items, *view.residual_items)
    )

    # This baseline models a fair conventional target-local indicator. Descendant
    # authority, pending effects, and uncertainty about other principals remain out
    # of its ON/OFF value and are preserved in the AuthorityLens view.
    if target_unknown:
        status = "UNKNOWN"
    elif target_authority:
        status = "ON"
    else:
        status = "OFF"
    return BaselineControlView(context=view.context, access_status=status)


def build_authority_lens_control_view(view: ControlView) -> AuthorityLensControlView:
    """Preserve every consequence section from the same derived ControlView."""
    return AuthorityLensControlView(
        context=view.context,
        outcome=view.outcome,
        headline=view.headline,
        active_items=view.active_items,
        residual_items=view.residual_items,
        pending_items=view.pending_items,
        unknown_items=view.unknown_items,
    )
