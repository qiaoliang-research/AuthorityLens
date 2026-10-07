"""Deterministic benchmark scenario definitions and family generation."""

from dataclasses import dataclass

from authority_lens import (
    Delegation,
    Effect,
    EffectStatus,
    ExternalState,
    ExternalStatus,
    Grant,
    Principal,
    PrincipalType,
)


@dataclass(frozen=True)
class BenchmarkScenario:
    scenario_id: str
    description: str
    principals: tuple[Principal, ...]
    grants: tuple[Grant, ...]
    delegations: tuple[Delegation, ...]
    external_states: tuple[ExternalState, ...]
    pending_effects: tuple[Effect, ...]
    revoke_grant_ids: tuple[str, ...]
    revoke_delegation_ids: tuple[str, ...]
    requested_action: str
    target_principal: str
    resource: str


CANONICAL_SCENARIO_IDS = (
    "S001_complete_revocation",
    "S002_single_residual_delegate",
    "S003_queued_action",
    "S004_unknown_external_agent",
)


def _scope_action(scope: str) -> str:
    return scope.split(".", 1)[1]


def _principal_chain(depth: int, external_depth: int | None = None) -> tuple[Principal, ...]:
    people = [
        Principal("human", PrincipalType.HUMAN),
        Principal("agent-a", PrincipalType.AGENT, "human"),
    ]
    previous = "agent-a"
    for level in range(1, depth + 1):
        if level == external_depth:
            current = "external-c"
            principal_type = PrincipalType.EXTERNAL
        else:
            letter_offset = level + 1 if external_depth is not None and level > external_depth else level
            current = f"agent-{chr(ord('a') + letter_offset)}"
            principal_type = PrincipalType.AGENT
        people.append(Principal(current, principal_type, previous))
        previous = current
    return tuple(people)


def _make_scenario(
    scenario_id: str,
    description: str,
    scope: str,
    depth: int = 0,
    *,
    external_depth: int | None = None,
    external_status: str | None = None,
    revoke_root: bool = False,
    revoke_link_positions: tuple[int, ...] = (),
    queue_effect: bool = False,
) -> BenchmarkScenario:
    principals = _principal_chain(depth, external_depth)
    grant_id = f"g-human-agent-a-{scope}"
    grants = (Grant(grant_id, "agent-a", scope, "human"),)
    chain_ids = [principal.id for principal in principals if principal.id != "human"]
    delegations = tuple(
        Delegation(
            f"d-{from_id}-{to_id}-{scope}",
            from_id,
            to_id,
            scope,
        )
        for from_id, to_id in zip(chain_ids, chain_ids[1:])
    )
    external_states = (
        (ExternalState("external-c", ExternalStatus(external_status)),)
        if external_status is not None
        else ()
    )
    effects = (
        (
            Effect(
                f"e-{scenario_id.lower()}-email",
                "agent-a",
                "email.send",
                EffectStatus.QUEUED,
                "gmail.send",
            ),
        )
        if queue_effect
        else ()
    )
    revoked_links = tuple(
        delegations[position - 1].id for position in revoke_link_positions
    )
    # The local permission estimand is the recipient whose delegation edge was
    # revoked; remaining descendants are still evaluated as system consequences.
    target = (
        delegations[revoke_link_positions[0] - 1].to_id
        if revoke_link_positions
        else "agent-a"
    )
    return BenchmarkScenario(
        scenario_id=scenario_id,
        description=description,
        principals=principals,
        grants=grants,
        delegations=delegations,
        external_states=external_states,
        pending_effects=effects,
        revoke_grant_ids=(grant_id,) if revoke_root else (),
        revoke_delegation_ids=revoked_links,
        requested_action="revoke",
        target_principal=target,
        resource="Gmail",
    )


def build_scenarios() -> tuple[BenchmarkScenario, ...]:
    """Return four canonical cases and 36 systematically varied cases."""
    scenarios = [
        _make_scenario(
            CANONICAL_SCENARIO_IDS[0],
            "Complete Revocation: the root Gmail read grant is revoked.",
            "gmail.read",
            revoke_root=True,
        ),
        _make_scenario(
            CANONICAL_SCENARIO_IDS[1],
            "Residual Delegation: Agent B keeps an issued read delegation after Agent A is revoked.",
            "gmail.read",
            depth=1,
            revoke_root=True,
        ),
        _make_scenario(
            CANONICAL_SCENARIO_IDS[2],
            "Queued Action: one email is queued before Gmail send authority is revoked.",
            "gmail.send",
            revoke_root=True,
            queue_effect=True,
        ),
        _make_scenario(
            CANONICAL_SCENARIO_IDS[3],
            "Unknown External Agent: Agent C has unknown status after root revocation.",
            "gmail.read",
            depth=1,
            external_depth=1,
            external_status="unknown",
            revoke_root=True,
        ),
    ]

    def append(description: str, **options) -> None:
        scenario_id = f"S{len(scenarios) + 1:03d}_{options.pop('slug')}"
        scenarios.append(
            _make_scenario(scenario_id, description, **options)
        )

    # Current, clean target authority establishes active-capability coverage.
    for scope in ("gmail.read", "gmail.send"):
        append(
            f"Agent A currently has a clean direct {scope} grant.",
            slug=f"direct_active_{_scope_action(scope)}",
            scope=scope,
        )

    # Clean delegation paths vary depth and scope independently.
    for depth in (1, 2, 3):
        for scope in ("gmail.read", "gmail.send"):
            append(
                f"A clean delegation chain of depth {depth} carries {scope}.",
                slug=f"clean_chain_depth{depth}_{_scope_action(scope)}",
                scope=scope,
                depth=depth,
            )

    # Revoking the root grant leaves previously issued descendant links residual.
    for depth in (1, 2, 3):
        for scope in ("gmail.read", "gmail.send"):
            if depth == 1 and scope == "gmail.read":
                continue  # Covered by canonical scenario S002.
            append(
                f"The root grant is revoked on a depth {depth} {scope} chain.",
                slug=f"root_revoked_depth{depth}_{_scope_action(scope)}",
                scope=scope,
                depth=depth,
                revoke_root=True,
            )

    # Revoking a non-root link leaves links below it independently active.
    for depth in (2, 3):
        for position in range(1, depth):
            for scope in ("gmail.read", "gmail.send"):
                append(
                    f"Delegation link {position} is revoked for its recipient in a depth {depth} {scope} chain.",
                    slug=f"link{position}_revoked_depth{depth}_{_scope_action(scope)}",
                    scope=scope,
                    depth=depth,
                    revoke_link_positions=(position,),
                )

    # The queued email is created from the root grant and survives root revocation.
    for depth in (1, 2, 3):
        append(
            f"One email is queued before root revocation on a depth {depth} send chain.",
            slug=f"queued_send_residual_depth{depth}",
            scope="gmail.send",
            depth=depth,
            revoke_root=True,
            queue_effect=True,
        )

    # External recipient status varies across confirmed active, revoked, and unknown.
    for depth in (1, 2):
        for status in ("confirmed_active", "confirmed_revoked", "unknown"):
            for scope in ("gmail.read", "gmail.send"):
                if depth == 1 and status == "unknown" and scope == "gmail.read":
                    continue  # Covered by canonical scenario S004.
                append(
                    f"An external leaf at delegation depth {depth} is {status} after root revocation.",
                    slug=f"external_leaf_depth{depth}_{status}_{_scope_action(scope)}",
                    scope=scope,
                    depth=depth,
                    external_depth=depth,
                    external_status=status,
                    revoke_root=True,
                )

    # Unknown/confirmed external state in the middle of a path to an internal descendant.
    for status in ("confirmed_active", "confirmed_revoked", "unknown"):
        append(
            f"External Agent C is {status} in the middle of a read path to Agent D.",
            slug=f"external_middle_{status}_read",
            scope="gmail.read",
            depth=2,
            external_depth=1,
            external_status=status,
            revoke_root=True,
        )

    return tuple(scenarios)
