"""Small authority model that keeps grants, delegations, and effects distinct."""

from dataclasses import dataclass, field, replace
from enum import StrEnum


class PrincipalType(StrEnum):
    HUMAN = "human"
    AGENT = "agent"
    EXTERNAL = "external"


class EffectStatus(StrEnum):
    QUEUED = "queued"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ExternalStatus(StrEnum):
    CONFIRMED_ACTIVE = "confirmed_active"
    CONFIRMED_REVOKED = "confirmed_revoked"
    UNKNOWN = "unknown"


class PathStatus(StrEnum):
    CLEAN = "clean"
    RESIDUAL = "residual"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class Principal:
    id: str
    type: PrincipalType
    parent_id: str | None = None


@dataclass
class Grant:
    id: str
    principal_id: str
    scope: str
    source_principal_id: str
    active: bool = True


@dataclass
class Delegation:
    id: str
    from_id: str
    to_id: str
    scope: str
    active: bool = True


@dataclass(frozen=True)
class Effect:
    id: str
    principal_id: str
    action: str
    status: EffectStatus
    required_scope: str
    authority_source_id: str | None = None


@dataclass(frozen=True)
class ExternalState:
    principal_id: str
    status: ExternalStatus


@dataclass(frozen=True)
class AuthorityEntry:
    principal_id: str
    scope: str
    source: str
    immediate_delegator: str | None
    root_source_principal_id: str
    root_source_grant_id: str
    principal_path: tuple[str, ...]
    delegation_path: tuple[str, ...]
    path_status: PathStatus = PathStatus.CLEAN


@dataclass
class EffectiveState:
    active_authority: list[AuthorityEntry] = field(default_factory=list)
    descendant_authority: list[AuthorityEntry] = field(default_factory=list)
    unresolved_authority: list[AuthorityEntry] = field(default_factory=list)
    pending_effects: list[Effect] = field(default_factory=list)
    unknown_states: list[ExternalState] = field(default_factory=list)


class AuthorityEngine:
    def __init__(self) -> None:
        self.principals: dict[str, Principal] = {}
        self.grants: list[Grant] = []
        self.delegations: list[Delegation] = []
        self.effects: list[Effect] = []
        self.external_states: dict[str, ExternalState] = {}

    def add_principal(self, principal: Principal) -> None:
        self.principals[principal.id] = principal

    def add_grant(self, grant: Grant) -> None:
        if any(existing.id == grant.id for existing in self.grants):
            raise ValueError(f"grant id {grant.id!r} already exists")
        self.grants.append(grant)

    def _external_status(self, principal_id: str) -> ExternalStatus | None:
        principal = self.principals.get(principal_id)
        if not principal or principal.type != PrincipalType.EXTERNAL:
            return None
        state = self.external_states.get(principal_id)
        return state.status if state else ExternalStatus.UNKNOWN

    def _effective_scopes(self, principal_id: str) -> set[str]:
        return {
            entry.scope
            for entry in self.calculate().active_authority
            if entry.principal_id == principal_id
        }

    def add_delegation(self, delegation: Delegation) -> None:
        # Validate the scope when issued; later revocation does not cascade to descendants.
        if delegation.scope not in self._effective_scopes(delegation.from_id):
            raise ValueError(
                f"delegation scope {delegation.scope!r} exceeds delegator's effective authority"
            )
        if any(existing.id == delegation.id for existing in self.delegations):
            raise ValueError(f"delegation id {delegation.id!r} already exists")
        self.delegations.append(delegation)

    def revoke_grant(self, principal_id: str, scope: str) -> None:
        for grant in self.grants:
            if grant.principal_id == principal_id and grant.scope == scope:
                grant.active = False

    def revoke_delegation(self, delegation_id: str) -> None:
        for delegation in self.delegations:
            if delegation.id == delegation_id:
                delegation.active = False
                return
        raise KeyError(f"unknown delegation id {delegation_id!r}")

    def add_effect(self, effect: Effect) -> None:
        if effect.authority_source_id is None and self.can_initiate(
            effect.principal_id, effect.required_scope
        ):
            source_id = next(
                (
                    grant.id
                    for grant in reversed(self.grants)
                    if grant.active
                    and grant.principal_id == effect.principal_id
                    and grant.scope == effect.required_scope
                ),
                None,
            )
            if source_id is None:
                source_id = next(
                    (
                        delegation.id
                        for delegation in reversed(self.delegations)
                        if delegation.active
                        and delegation.to_id == effect.principal_id
                        and delegation.scope == effect.required_scope
                        and self._external_status(delegation.to_id)
                        not in (ExternalStatus.UNKNOWN, ExternalStatus.CONFIRMED_REVOKED)
                    ),
                    None,
                )
            if source_id is not None:
                effect = replace(effect, authority_source_id=source_id)
        self.effects.append(effect)

    def cancel_effect(self, effect_id: str) -> None:
        for index, effect in enumerate(self.effects):
            if effect.id == effect_id:
                if effect.status == EffectStatus.QUEUED:
                    self.effects[index] = replace(effect, status=EffectStatus.CANCELLED)
                return
        raise KeyError(f"unknown effect id {effect_id!r}")

    def set_external_state(self, state: ExternalState) -> None:
        self.external_states[state.principal_id] = state

    def can_initiate(self, principal_id: str, scope: str) -> bool:
        return scope in self._effective_scopes(principal_id)

    def _path_status(
        self,
        principal_path: tuple[str, ...],
        current: PathStatus,
        revoked_link: bool = False,
    ) -> PathStatus:
        statuses = [self._external_status(principal_id) for principal_id in principal_path]
        if ExternalStatus.UNKNOWN in statuses:
            return PathStatus.UNCERTAIN
        if current == PathStatus.UNCERTAIN:
            return PathStatus.UNCERTAIN
        if revoked_link or current == PathStatus.RESIDUAL:
            return PathStatus.RESIDUAL
        if ExternalStatus.CONFIRMED_REVOKED in statuses:
            return PathStatus.RESIDUAL
        return PathStatus.CLEAN

    def calculate(self) -> EffectiveState:
        result = EffectiveState()

        for grant in self.grants:
            if grant.active:
                path = (grant.source_principal_id, grant.principal_id)
                status = self._path_status(path, PathStatus.CLEAN)
                entry = AuthorityEntry(
                    principal_id=grant.principal_id,
                    scope=grant.scope,
                    source="grant",
                    immediate_delegator=None,
                    root_source_principal_id=grant.source_principal_id,
                    root_source_grant_id=grant.id,
                    principal_path=path,
                    delegation_path=(),
                    path_status=status,
                )
                endpoint_status = self._external_status(grant.principal_id)
                if status == PathStatus.UNCERTAIN:
                    result.unresolved_authority.append(entry)
                elif endpoint_status != ExternalStatus.CONFIRMED_REVOKED:
                    result.active_authority.append(entry)

        # Historical links remain in paths so surviving downstream links expose residual health.
        for grant in self.grants:
            path = (grant.source_principal_id, grant.principal_id)
            status = self._path_status(
                path,
                PathStatus.RESIDUAL if not grant.active else PathStatus.CLEAN,
            )
            self._collect_descendants(
                holder_id=grant.principal_id,
                scope=grant.scope,
                root_source=grant.source_principal_id,
                root_grant_id=grant.id,
                principal_path=path,
                delegation_path=(),
                path_status=status,
                result=result,
                visited=frozenset({grant.principal_id}),
            )

        result.pending_effects = [
            effect for effect in self.effects if effect.status == EffectStatus.QUEUED
        ]
        for state in self.external_states.values():
            if state.status == ExternalStatus.UNKNOWN:
                result.unknown_states.append(state)
        for delegation in self.delegations:
            if (
                delegation.active
                and self._external_status(delegation.to_id) == ExternalStatus.UNKNOWN
                and delegation.to_id not in self.external_states
            ):
                result.unknown_states.append(
                    ExternalState(delegation.to_id, ExternalStatus.UNKNOWN)
                )
        return result

    def _collect_descendants(
        self,
        holder_id: str,
        scope: str,
        root_source: str,
        root_grant_id: str,
        principal_path: tuple[str, ...],
        delegation_path: tuple[str, ...],
        path_status: PathStatus,
        result: EffectiveState,
        visited: frozenset[str],
    ) -> None:
        for delegation in self.delegations:
            if delegation.from_id != holder_id or delegation.scope != scope:
                continue
            if delegation.to_id in visited:
                continue

            next_principal_path = principal_path + (delegation.to_id,)
            next_delegation_path = delegation_path + (delegation.id,)
            next_status = self._path_status(
                next_principal_path,
                path_status,
                revoked_link=not delegation.active,
            )
            entry = AuthorityEntry(
                principal_id=delegation.to_id,
                scope=scope,
                source="delegation",
                immediate_delegator=delegation.from_id,
                root_source_principal_id=root_source,
                root_source_grant_id=root_grant_id,
                principal_path=next_principal_path,
                delegation_path=next_delegation_path,
                path_status=next_status,
            )
            endpoint_status = self._external_status(delegation.to_id)
            if delegation.active:
                if next_status == PathStatus.UNCERTAIN:
                    result.unresolved_authority.append(entry)
                elif endpoint_status != ExternalStatus.CONFIRMED_REVOKED:
                    result.active_authority.append(entry)
                    result.descendant_authority.append(entry)
            # Continue through revoked links to retain lineage for independently active descendants.
            self._collect_descendants(
                holder_id=delegation.to_id,
                scope=scope,
                root_source=root_source,
                root_grant_id=root_grant_id,
                principal_path=next_principal_path,
                delegation_path=next_delegation_path,
                path_status=next_status,
                result=result,
                visited=visited | {delegation.to_id},
            )
