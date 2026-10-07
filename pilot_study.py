"""Deterministic, synthetic-only pilot scheduling and scoring helpers."""

from __future__ import annotations

import csv
import json
import random
import re
from enum import StrEnum
from pathlib import Path
from typing import Any

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


TASKS_PATH = Path(__file__).with_name("PILOT_TASKS.json")
DRY_RUN_LABEL = "SYNTHETIC DRY RUN — NOT PARTICIPANT DATA"


class Answer(StrEnum):
    YES = "YES"
    NO = "NO"
    CANNOT_TELL = "CANNOT TELL"


class Condition(StrEnum):
    TARGET_LOCAL = "target_local"
    CONSEQUENCE = "consequence_oriented"


class QuestionType(StrEnum):
    DIRECT_RETRIEVAL = "DIRECT_RETRIEVAL"
    TRANSFER_INFERENCE = "TRANSFER_INFERENCE"


def _normalise_answer(value: str) -> str:
    return " ".join(str(value).strip().upper().replace("_", " ").replace("-", " ").split())


def _revoke_grant(engine: AuthorityEngine, grant_ref: Any) -> None:
    if isinstance(grant_ref, str):
        grant = next((item for item in engine.grants if item.id == grant_ref), None)
        if grant is None:
            raise ValueError(f"unknown revoked grant {grant_ref!r}")
        engine.revoke_grant(grant.principal_id, grant.scope)
        return
    engine.revoke_grant(grant_ref["principal_id"], grant_ref["scope"])


def _engine_for_task(task: dict[str, Any]) -> AuthorityEngine:
    """Replay a declarative task fixture through the frozen engine."""
    spec = task["state"]
    engine = AuthorityEngine()
    for item in spec["principals"]:
        engine.add_principal(
            Principal(
                item["id"],
                PrincipalType(item["type"]),
                item.get("parent_id"),
            )
        )

    for item in spec["grants"]:
        engine.add_grant(
            Grant(
                item["id"],
                item["principal_id"],
                item["scope"],
                item["source_principal_id"],
                True,
            )
        )

    # The delegation is issued while its source has authority. Final revocations
    # are applied after issuance so the fixture models a post-control state.
    for item in spec.get("external_states", []):
        engine.set_external_state(
            ExternalState(item["principal_id"], ExternalStatus.CONFIRMED_ACTIVE)
        )
    for item in spec["delegations"]:
        engine.add_delegation(
            Delegation(
                item["id"], item["from_id"], item["to_id"], item["scope"], True
            )
        )

    for grant_ref in spec.get("revoked_grants", []):
        _revoke_grant(engine, grant_ref)
    for delegation_ref in spec.get("revoked_delegations", []):
        delegation_id = (
            delegation_ref["id"] if isinstance(delegation_ref, dict) else delegation_ref
        )
        engine.revoke_delegation(delegation_id)

    # Apply the terminal external state only after delegation issuance and revocation.
    for item in spec.get("external_states", []):
        engine.set_external_state(
            ExternalState(item["principal_id"], ExternalStatus(item["status"]))
        )
    for item in spec.get("effects", []):
        engine.add_effect(
            Effect(
                item["id"],
                item["principal_id"],
                item["action"],
                EffectStatus(item["status"]),
                item["required_scope"],
                item.get("authority_source_id"),
            )
        )
    return engine


def derive_ground_truth(task: dict[str, Any]) -> dict[str, Any]:
    """Derive answers from EffectiveState and structured query fields only."""
    engine = _engine_for_task(task)
    state = engine.calculate()
    question = task["question"]
    query_type = question["query_type"]
    scope = question.get("scope")
    principal_id = question.get("principal_id")

    if query_type == "pending_scope":
        pending_remains = any(
            effect.status == EffectStatus.QUEUED
            and effect.required_scope == scope
            for effect in state.pending_effects
        )
        answer = Answer.YES.value if pending_remains else Answer.NO.value
        remains = answer
        kind = "pending_effect" if pending_remains else "none"
    elif query_type in {
        "any_principal_scope",
        "specific_principal_scope",
        "future_message_reader",
    }:
        def matches(entry) -> bool:
            return entry.scope == scope and (
                query_type == "any_principal_scope"
                or entry.principal_id == principal_id
            )

        confirmed = any(matches(entry) for entry in state.active_authority)
        unresolved = any(matches(entry) for entry in state.unresolved_authority)
        if confirmed:
            answer, kind = Answer.YES.value, "confirmed_authority"
        elif unresolved:
            answer, kind = Answer.CANNOT_TELL.value, "unresolved_authority"
        else:
            answer, kind = Answer.NO.value, "none"
        remains = answer
    elif query_type == "guarantee_no_scope":
        principal_type = question.get("principal_type")

        def included(entry) -> bool:
            principal = engine.principals.get(entry.principal_id)
            return (
                entry.scope == scope
                and (
                    principal_type is None
                    or (principal is not None and principal.type.value == principal_type)
                )
            )

        confirmed = any(included(entry) for entry in state.active_authority)
        unresolved = any(included(entry) for entry in state.unresolved_authority)
        if confirmed:
            answer, remains, kind = Answer.NO.value, Answer.YES.value, "confirmed_authority"
        elif unresolved:
            # A guarantee is not established (NO) even though the underlying access remains unknown.
            answer, remains, kind = (
                Answer.NO.value,
                Answer.CANNOT_TELL.value,
                "unresolved_authority",
            )
        else:
            answer, remains, kind = Answer.YES.value, Answer.NO.value, "none"
    elif query_type == "send_closure_action_needed":
        confirmed = any(entry.scope == scope for entry in state.active_authority)
        unresolved = any(entry.scope == scope for entry in state.unresolved_authority)
        pending = any(
            effect.status == EffectStatus.QUEUED
            and effect.required_scope == scope
            for effect in state.pending_effects
        )
        if confirmed or pending:
            answer, remains, kind = Answer.YES.value, Answer.YES.value, (
                "pending_effect" if pending else "confirmed_authority"
            )
        elif unresolved:
            answer, remains, kind = (
                Answer.CANNOT_TELL.value,
                Answer.CANNOT_TELL.value,
                "unresolved_authority",
            )
        else:
            answer, remains, kind = Answer.NO.value, Answer.NO.value, "none"
    else:
        raise ValueError(f"unsupported query_type {query_type!r}")

    return {
        "answer": answer,
        "relevant_consequence_remains": remains,
        "consequence_kind": kind,
    }


def derive_view_supported_answer(task: dict[str, Any], condition: str) -> str:
    """Derive the answer warranted by the structured fields shown in one view."""
    engine = _engine_for_task(task)
    context = ControlContext(
        task["resource"],
        task["requested_action"],
        task["target_principal"],
        action_confirmed=task.get("action_confirmed", False),
    )
    control = build_control_view(context, translate_effective_state(engine.calculate()))
    question = task["question"]
    query_type = question["query_type"]
    scope = question.get("scope")

    if condition == Condition.TARGET_LOCAL.value:
        local_status = build_baseline_control_view(control).access_status
        if query_type in {
            "pending_scope",
            "send_closure_action_needed",
            "future_message_reader",
        }:
            return Answer.CANNOT_TELL.value
        if query_type == "guarantee_no_scope":
            principal_type = question.get("principal_type")
            target = engine.principals.get(context.target_principal)
            if principal_type and (
                target is None or target.type.value != principal_type
            ):
                return Answer.CANNOT_TELL.value
            # A local ON indicator disproves system-wide absence; OFF says nothing
            # about other holders, so the baseline cannot establish closure.
            return (
                Answer.NO.value
                if local_status in {"ON", "UNKNOWN"}
                else Answer.CANNOT_TELL.value
            )
        if query_type == "specific_principal_scope":
            if question.get("principal_id") != context.target_principal:
                return Answer.CANNOT_TELL.value
            return {
                "ON": Answer.YES.value,
                "OFF": Answer.NO.value,
                "UNKNOWN": Answer.CANNOT_TELL.value,
            }[local_status]
        if query_type == "any_principal_scope":
            return (
                Answer.YES.value
                if local_status == "ON"
                else Answer.CANNOT_TELL.value
            )
        raise ValueError(f"unsupported query type {query_type!r}")

    if condition != Condition.CONSEQUENCE.value:
        raise ValueError(f"unknown interface condition {condition!r}")
    view = build_authority_lens_control_view(control)

    if query_type == "pending_scope":
        has_pending = any(
            item.effect.required_scope == scope for item in view.pending_items
        )
        return Answer.YES.value if has_pending else Answer.NO.value

    if query_type == "send_closure_action_needed":
        has_authority = any(
            item.scope == scope
            for item in (*view.active_items, *view.residual_items)
        )
        has_pending = any(
            item.effect.required_scope == scope for item in view.pending_items
        )
        has_unknown = any(
            item.scope is None or item.scope == scope for item in view.unknown_items
        )
        if has_authority or has_pending:
            return Answer.YES.value
        return Answer.CANNOT_TELL.value if has_unknown else Answer.NO.value

    if query_type == "guarantee_no_scope":
        principal_type = question.get("principal_type")

        def included(item) -> bool:
            principal = engine.principals.get(item.principal_id)
            return (
                (item.scope is None or item.scope == scope)
                and (
                    principal_type is None
                    or (principal is not None and principal.type.value == principal_type)
                )
            )

        has_confirmed = any(
            included(item) for item in (*view.active_items, *view.residual_items)
        )
        if has_confirmed:
            return Answer.NO.value
        has_unresolved = any(included(item) for item in view.unknown_items)
        return Answer.NO.value if has_unresolved else Answer.YES.value

    if query_type not in {
        "any_principal_scope",
        "specific_principal_scope",
        "future_message_reader",
        "guarantee_no_scope",
    }:
        raise ValueError(f"unsupported query type {query_type!r}")

    principal_id = question.get("principal_id")
    matches_principal = lambda item: (
        query_type == "any_principal_scope" or item.principal_id == principal_id
    )
    has_confirmed = any(
        item.scope == scope and matches_principal(item)
        for item in (*view.active_items, *view.residual_items)
    )
    if has_confirmed:
        return Answer.YES.value
    has_unresolved = any(
        (item.scope is None or item.scope == scope) and matches_principal(item)
        for item in view.unknown_items
    )
    return Answer.CANNOT_TELL.value if has_unresolved else Answer.NO.value


def _validate_task(task: dict[str, Any]) -> None:
    try:
        QuestionType(task["question_type"])
    except (KeyError, ValueError) as error:
        raise ValueError(f"task {task.get('task_id', '<unknown>')} has an invalid question_type") from error
    question = task.get("question", {})
    query_type = question.get("query_type")
    allowed_queries = {
        "any_principal_scope",
        "specific_principal_scope",
        "pending_scope",
        "future_message_reader",
        "guarantee_no_scope",
        "send_closure_action_needed",
    }
    if query_type not in allowed_queries:
        raise ValueError(f"task {task.get('task_id', '<unknown>')} has an unsupported query_type")
    if query_type in {"specific_principal_scope", "future_message_reader"} and not question.get("principal_id"):
        raise ValueError(f"task {task['task_id']} query requires principal_id")
    if query_type in {
        "any_principal_scope",
        "specific_principal_scope",
        "pending_scope",
        "future_message_reader",
        "guarantee_no_scope",
        "send_closure_action_needed",
    } and not question.get("scope"):
        raise ValueError(f"task {task['task_id']} query requires scope")
    question_type = QuestionType(task["question_type"])
    if question_type == QuestionType.TRANSFER_INFERENCE and query_type not in {
        "future_message_reader",
        "guarantee_no_scope",
        "send_closure_action_needed",
    }:
        raise ValueError(f"task {task['task_id']} transfer query is not an inference query")
    if question_type == QuestionType.DIRECT_RETRIEVAL and query_type in {
        "future_message_reader",
        "guarantee_no_scope",
        "send_closure_action_needed",
    }:
        raise ValueError(f"task {task['task_id']} direct query uses a transfer query type")
    principal_type = question.get("principal_type")
    if principal_type is not None:
        try:
            PrincipalType(principal_type)
        except ValueError as error:
            raise ValueError(
                f"task {task['task_id']} has an invalid principal_type filter"
            ) from error
        if query_type != "guarantee_no_scope":
            raise ValueError(
                f"task {task['task_id']} uses principal_type on an incompatible query"
            )
    expected = _normalise_answer(task["expected_answer"])
    if expected not in {answer.value for answer in Answer}:
        raise ValueError(f"invalid expected answer for {task['task_id']}")
    derived = derive_ground_truth(task)
    if expected != derived["answer"]:
        raise ValueError(
            f"task {task['task_id']} expected {expected}, but AuthorityEngine derives {derived['answer']}"
        )
    if _normalise_answer(task["relevant_consequence_remains"]) != derived["relevant_consequence_remains"]:
        raise ValueError(
            f"task {task['task_id']} consequence annotation disagrees with AuthorityEngine"
        )
    false_safe_rule = task.get("false_safe_rule", {})
    for rule_name in ("false_safe_if", "false_alarm_if"):
        answers = false_safe_rule.get(rule_name)
        if not isinstance(answers, list) or any(
            _normalise_answer(answer) not in {item.value for item in Answer}
            for answer in answers
        ):
            raise ValueError(f"task {task['task_id']} has an invalid {rule_name} rule")
    if Answer.CANNOT_TELL.value in map(_normalise_answer, false_safe_rule["false_safe_if"]):
        raise ValueError(f"task {task['task_id']} cannot classify CANNOT TELL as false-safe")
    if derived["relevant_consequence_remains"] == Answer.NO.value and false_safe_rule["false_safe_if"]:
        raise ValueError(f"task {task['task_id']} has false-safe responses despite no remaining consequence")
    if derived["relevant_consequence_remains"] != Answer.NO.value and false_safe_rule["false_alarm_if"]:
        raise ValueError(f"task {task['task_id']} has false-alarm responses without a known absence")
    view_answers = task["view_supported_answer_by_condition"]
    if set(view_answers) != {condition.value for condition in Condition}:
        raise ValueError(f"task {task['task_id']} must annotate both view conditions")
    for condition, answer in view_answers.items():
        if _normalise_answer(answer) not in {item.value for item in Answer}:
            raise ValueError(f"task {task['task_id']} has an invalid view-supported answer")
        derived_view_answer = derive_view_supported_answer(task, condition)
        if _normalise_answer(answer) != derived_view_answer:
            raise ValueError(
                f"task {task['task_id']} {condition} view supports {derived_view_answer}, not {answer}"
            )


def load_task_bank(path: str | Path | None = None) -> list[dict[str, Any]]:
    source = Path(path) if path is not None else TASKS_PATH
    catalog = json.loads(source.read_text(encoding="utf-8"))
    # The research catalog is intentionally a plain JSON array; accept a named
    # wrapper too so small downstream fixtures can remain self-describing.
    task_bank = catalog if isinstance(catalog, list) else catalog["tasks"]
    if not 12 <= len(task_bank) <= 16:
        raise ValueError("pilot task bank must contain 12 to 16 logical tasks")
    ids = [task["task_id"] for task in task_bank]
    if len(ids) != len(set(ids)):
        raise ValueError("pilot task IDs must be unique")
    scenario_ids = [task["scenario_id"] for task in task_bank]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise ValueError("pilot scenario IDs must be unique")
    for task in task_bank:
        _validate_task(task)
    transfer_pairs: dict[str, list[dict[str, Any]]] = {}
    for task in task_bank:
        if task["question_type"] == QuestionType.TRANSFER_INFERENCE.value:
            pair_id = task.get("matched_pair")
            if not pair_id:
                raise ValueError(f"transfer task {task['task_id']} needs a matched_pair")
            transfer_pairs.setdefault(pair_id, []).append(task)
    if not transfer_pairs or any(len(pair) != 2 for pair in transfer_pairs.values()):
        raise ValueError("each transfer matched_pair must contain exactly two tasks")
    if any(pair[0]["question"]["text"] != pair[1]["question"]["text"] for pair in transfer_pairs.values()):
        raise ValueError("matched transfer tasks must use identical question wording")
    direct_tasks = [
        task for task in task_bank
        if task["question_type"] == QuestionType.DIRECT_RETRIEVAL.value
    ]
    for transfer in (
        task for task in task_bank
        if task["question_type"] == QuestionType.TRANSFER_INFERENCE.value
    ):
        exact_state_matches = {
            task["task_id"] for task in direct_tasks
            if task["state"] == transfer["state"]
        }
        declared_avoidance = set(transfer.get("avoid_cooccurrence_with", []))
        if declared_avoidance != exact_state_matches:
            raise ValueError(
                f"transfer task {transfer['task_id']} must exclude its exact-state direct items"
            )
    return task_bank


def _principal_name(principal_id: str, engine: AuthorityEngine | None = None) -> str:
    if principal_id.startswith("external-"):
        return f"External Agent {principal_id.removeprefix('external-').upper()}"
    if principal_id.startswith("agent-"):
        label = f"Agent {principal_id.removeprefix('agent-').upper()}"
        principal = engine.principals.get(principal_id) if engine else None
        if principal and principal.type == PrincipalType.EXTERNAL:
            return f"External {label}"
        return label
    return principal_id.replace("-", " ").title()


def build_stimulus_pair(task: dict[str, Any]) -> dict[str, Any]:
    """Build both conditions from one EffectiveState calculation."""
    engine = _engine_for_task(task)
    state = engine.calculate()
    context = ControlContext(
        task["resource"],
        task["requested_action"],
        task["target_principal"],
        action_confirmed=task.get("action_confirmed", False),
    )
    control_view = build_control_view(context, translate_effective_state(state))
    return {
        "effective_state": state,
        Condition.TARGET_LOCAL.value: _render_stimulus(
            task, Condition.TARGET_LOCAL.value, engine, control_view
        ),
        Condition.CONSEQUENCE.value: _render_stimulus(
            task, Condition.CONSEQUENCE.value, engine, control_view
        ),
    }


def build_stimulus(task: dict[str, Any], condition: str) -> dict[str, Any]:
    """Build one panel from the same-state comparison model."""
    if condition not in {item.value for item in Condition}:
        raise ValueError(f"unknown interface condition {condition!r}")
    return build_stimulus_pair(task)[condition]


def _render_stimulus(
    task: dict[str, Any],
    condition: str,
    engine: AuthorityEngine,
    control_view,
) -> dict[str, Any]:
    context = control_view.context
    baseline = build_baseline_control_view(control_view)
    scope = task["question"].get("scope", "")
    resource_label = (
        f"{context.resource} Sending" if scope == "gmail.send" else f"{context.resource} Access"
    )
    target_local_state = {
        "target": _principal_name(context.target_principal, engine),
        "resource_label": resource_label,
        "status": baseline.access_status,
    }
    if condition == Condition.TARGET_LOCAL.value:
        return {
            "title": "Conventional Permission View",
            **target_local_state,
        }

    if condition == Condition.CONSEQUENCE.value:
        view = build_authority_lens_control_view(control_view)
        authority_local_state = _authoritylens_local_state(
            baseline.access_status,
            context,
            target_local_state["target"],
            resource_label,
        )
        sections = []
        external_ids = {
            principal_id
            for principal_id, principal in engine.principals.items()
            if principal.type == PrincipalType.EXTERNAL
        }
        for title, items in (
            ("Current capabilities", view.active_items),
            ("Remaining delegated access", view.residual_items),
            ("Pending consequences", view.pending_items),
            ("Cannot verify", view.unknown_items),
        ):
            if items:
                sections.append({
                    "title": title,
                    "items": [
                        _externalize_description(item.description, item.principal_id)
                        if getattr(item, "principal_id", None) in external_ids
                        else item.description
                        for item in items
                    ],
                })
        stimulus = {
            "title": "AuthorityLens",
            "target_local_state": {
                "target": target_local_state["target"],
                "resource_label": resource_label,
                **authority_local_state,
            },
            "headline": view.headline,
            "sections": sections,
            "empty": not sections,
        }
        if view.outcome == ControlOutcome.COMPLETE:
            stimulus["empty_state_message"] = (
                f"No remaining {context.resource} capabilities, pending actions, "
                "or unresolved access."
            )
        return stimulus
    raise ValueError(f"unknown interface condition {condition!r}")


def _authoritylens_local_state(
    access_status: str,
    context: ControlContext,
    target_label: str,
    resource_label: str,
) -> dict[str, str]:
    """Render the baseline's target-local fact at the task's displayed scope."""
    is_send_scope = resource_label == f"{context.resource} Sending"
    local_fact = (
        f"send email through {context.resource}"
        if is_send_scope
        else f"have {context.resource} access"
    )
    if access_status == "UNKNOWN":
        return {
            "status": "UNKNOWN",
            "text": (
                f"{target_label}'s ability to {local_fact} cannot be verified."
                if is_send_scope
                else f"{target_label}'s {context.resource} access cannot be verified."
            ),
        }
    if access_status == "ON":
        return {
            "status": "REMAINING",
            "text": (
                f"{target_label} can still {local_fact}."
                if is_send_scope
                else f"{target_label} still has {context.resource} access."
            ),
        }
    if context.requested_action.casefold() == "revoke" and context.action_confirmed:
        return {
            "status": "STOPPED",
            "text": (
                f"{target_label} can no longer {local_fact}."
                if is_send_scope
                else f"{target_label} no longer has {context.resource} access."
            ),
        }
    return {
        "status": "OFF",
        "text": f"No current {context.resource} permission is shown for the target.",
    }


def _externalize_description(
    description: str, principal_id: str
) -> str:
    """Label external holders without duplicating an existing `External` prefix."""
    suffix = (
        principal_id.removeprefix("external-").upper()
        if principal_id.startswith("external-")
        else principal_id.removeprefix("agent-").upper()
    )
    label = f"Agent {suffix}"
    return re.sub(rf"(?<!External )\b{re.escape(label)}\b", f"External {label}", description)


def _build_session_plan(seed: int) -> list[dict[str, Any]]:
    """Build private scoring-side schedule records for one between-subjects session.

    A participant sees one state from each matched transfer pair. Any direct
    item with an identical underlying state is omitted from that session, so a
    transfer answer cannot be recalled from an earlier duplicate. Adjacent
    even/odd seeds share order and selected variants, with opposite conditions.
    """
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be an integer")
    all_tasks = load_task_bank()
    pair_index = seed // 2
    block_index = pair_index % 8
    direct_tasks = [
        task for task in all_tasks
        if task["question_type"] == QuestionType.DIRECT_RETRIEVAL.value
    ]
    pairs: dict[str, list[dict[str, Any]]] = {}
    for task in all_tasks:
        if task["question_type"] == QuestionType.TRANSFER_INFERENCE.value:
            pairs.setdefault(task["matched_pair"], []).append(task)
    pair_ids = sorted(pairs)
    selected_transfer = [
        pairs[pair_id][(block_index >> pair_number) & 1]
        for pair_number, pair_id in enumerate(sorted(pairs))
    ]

    # The exact-state annotations keep matched transfer facts from being
    # repeated verbatim as direct retrieval earlier in the same session.
    excluded_direct_ids = {
        task_id
        for task in selected_transfer
        for task_id in task.get("avoid_cooccurrence_with", [])
    }
    limited_direct_ids = {
        task_id
        for task in all_tasks
        if task["question_type"] == QuestionType.TRANSFER_INFERENCE.value
        for task_id in task.get("avoid_cooccurrence_with", [])
    }
    selected_limited_direct = [
        task for task in direct_tasks
        if task["task_id"] in limited_direct_ids
        and task["task_id"] not in excluded_direct_ids
    ]
    rotating_direct = [
        task for task in direct_tasks
        if task["task_id"] not in limited_direct_ids
    ]
    rotating_count = 6 - len(selected_limited_direct)

    # Across the eight transfer-variant blocks, rotate the always-eligible
    # direct items evenly; paired condition seeds retain the same selection.
    rotation_offset = 0
    for prior_block in range(block_index):
        prior_transfer = [
            pairs[pair_id][(prior_block >> pair_number) & 1]
            for pair_number, pair_id in enumerate(pair_ids)
        ]
        prior_excluded_ids = {
            task_id
            for task in prior_transfer
            for task_id in task.get("avoid_cooccurrence_with", [])
        }
        prior_limited_count = sum(
            task["task_id"] in limited_direct_ids
            and task["task_id"] not in prior_excluded_ids
            for task in direct_tasks
        )
        rotation_offset += 6 - prior_limited_count
    if rotating_count < 0 or rotating_count > len(rotating_direct):
        raise ValueError("task bank cannot form a nine-trial session without same-state overlap")
    if not rotating_direct and rotating_count:
        raise ValueError("task bank needs at least one rotating direct item")
    rotation_offset %= max(len(rotating_direct), 1)
    selected_rotating_direct = [
        rotating_direct[(rotation_offset + index) % len(rotating_direct)]
        for index in range(rotating_count)
    ]
    selected_direct = selected_limited_direct + selected_rotating_direct
    if len(selected_direct) != 6:
        raise ValueError("each session must contain six direct-retrieval items")

    task_order = selected_direct + selected_transfer
    rng = random.Random(pair_index)
    rng.shuffle(task_order)
    condition = (
        Condition.TARGET_LOCAL.value
        if seed % 2 == 0
        else Condition.CONSEQUENCE.value
    )
    schedule = []
    for index, task in enumerate(task_order):
        views = build_stimulus_pair(task)
        schedule.append({
            "trial_index": index + 1,
            "task_id": task["task_id"],
            "scenario_id": task["scenario_id"],
            "question_type": task["question_type"],
            "matched_pair": task.get("matched_pair"),
            "condition": condition,
            "question": task["question"]["text"],
            "stimulus": views[condition],
        })
    return schedule


def build_session_schedule(seed: int) -> list[dict[str, Any]]:
    """Return only participant-display fields; keep semantic IDs scoring-side."""
    return [
        {
            "trial_index": trial["trial_index"],
            "question": trial["question"],
            "stimulus": trial["stimulus"],
        }
        for trial in _build_session_plan(seed)
    ]


def score_trial(
    trial: dict[str, Any],
    response: str,
    response_time_ms: int,
    confidence: int | None = None,
) -> dict[str, Any]:
    normalized = _normalise_answer(response)
    valid_answers = {answer.value for answer in Answer}
    if normalized not in valid_answers:
        raise ValueError("response must be YES, NO, or CANNOT TELL")
    if isinstance(response_time_ms, bool) or not isinstance(response_time_ms, int) or response_time_ms < 0:
        raise ValueError("response_time_ms must be a nonnegative integer")
    if confidence is not None and (
        isinstance(confidence, bool)
        or not isinstance(confidence, int)
        or not 1 <= confidence <= 5
    ):
        raise ValueError("confidence must be an integer from 1 to 5")

    ground_truth = trial["ground_truth"]
    correct_answer = _normalise_answer(ground_truth["answer"])
    correct = normalized == correct_answer
    view_supported_answer = _normalise_answer(trial["view_supported_answer"])
    remains = _normalise_answer(ground_truth["relevant_consequence_remains"])
    question_type = QuestionType(trial["question_type"]).value
    false_safe_responses = {
        _normalise_answer(item) for item in trial["false_safe_rule"]["false_safe_if"]
    }
    false_alarm_responses = {
        _normalise_answer(item) for item in trial["false_safe_rule"]["false_alarm_if"]
    }
    if Answer.CANNOT_TELL.value in false_safe_responses:
        raise ValueError("CANNOT TELL cannot be classified as false-safe")
    false_safe_eligible = remains != Answer.NO.value
    false_alarm_eligible = remains == Answer.NO.value
    return {
        "trial_index": trial["trial_index"],
        "task_id": trial["task_id"],
        "trial_id": f"{trial['task_id']}-{trial['trial_index']:02d}",
        "scenario_id": trial["scenario_id"],
        "condition": trial["condition"],
        "question_type": question_type,
        "ground_truth": ground_truth,
        "question": trial["question"],
        "response": normalized,
        "correct": correct,
        "evidence_aligned": normalized == view_supported_answer,
        "false_safe_eligible": false_safe_eligible,
        "false_safe": false_safe_eligible and normalized in false_safe_responses,
        "false_alarm_eligible": false_alarm_eligible,
        "false_alarm": false_alarm_eligible and normalized in false_alarm_responses,
        "response_time_ms": response_time_ms,
        "confidence": confidence,
    }


def simulate_dry_run(seed: int) -> dict[str, Any]:
    """Exercise serialization/scoring with marked synthetic responses, never participant data."""
    schedule = _build_session_plan(seed)
    task_by_id = {task["task_id"]: task for task in load_task_bank()}
    records = []
    for index, trial in enumerate(schedule):
        # Keep engine and view-supported answer keys outside the display payload.
        # The scoring side reconstructs them from the private catalog only here.
        truth = derive_ground_truth(task_by_id[trial["task_id"]])
        task = task_by_id[trial["task_id"]]
        supported_answer = task["view_supported_answer_by_condition"][trial["condition"]]
        scored_trial = {
            **trial,
            "ground_truth": truth,
            "view_supported_answer": supported_answer,
            "question_type": task["question_type"],
            "false_safe_rule": task["false_safe_rule"],
        }
        if index % 4 == 0:
            response = truth["answer"]
        elif index % 4 == 1:
            response = (
                Answer.NO.value
                if truth["relevant_consequence_remains"] != Answer.NO.value
                else Answer.YES.value
            )
        elif index % 4 == 2:
            response = Answer.CANNOT_TELL.value
        else:
            response = Answer.YES.value if truth["answer"] == Answer.NO.value else truth["answer"]
        records.append(
            score_trial(
                scored_trial,
                response,
                response_time_ms=850 + index * 75,
                confidence=3 + index % 3,
            )
        )
    return {
        "dataset_label": DRY_RUN_LABEL,
        "seed": seed,
        "record_note": "Scoring and export test vectors only; not participant responses or findings.",
        "records": records,
    }


def calculate_metrics(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Summarize outcomes by condition and question type without a composite score."""
    result = {}
    for condition in (Condition.TARGET_LOCAL.value, Condition.CONSEQUENCE.value):
        group = [record for record in records if record["condition"] == condition]
        by_type = {}
        for question_type in QuestionType:
            typed = [record for record in group if record["question_type"] == question_type.value]
            fs_denominator = sum(record["false_safe_eligible"] for record in typed)
            fa_denominator = sum(record["false_alarm_eligible"] for record in typed)
            durations = sorted(record["response_time_ms"] for record in typed)
            if durations:
                middle = len(durations) // 2
                median_duration = (
                    durations[middle]
                    if len(durations) % 2
                    else (durations[middle - 1] + durations[middle]) / 2
                )
            else:
                median_duration = None
            confidence_values = [
                record["confidence"] for record in typed
                if record["confidence"] is not None
            ]
            by_type[question_type.value] = {
                "trials": len(typed),
                "accuracy_count": sum(record["correct"] for record in typed),
                "accuracy_rate": (
                    sum(record["correct"] for record in typed) / len(typed)
                    if typed else None
                ),
                "evidence_aligned_count": sum(record["evidence_aligned"] for record in typed),
                "evidence_aligned_rate": (
                    sum(record["evidence_aligned"] for record in typed) / len(typed)
                    if typed else None
                ),
                "false_safe_count": sum(record["false_safe"] for record in typed),
                "false_safe_denominator": fs_denominator,
                "false_safe_rate": (
                    sum(record["false_safe"] for record in typed) / fs_denominator
                    if fs_denominator else None
                ),
                "false_alarm_count": sum(record["false_alarm"] for record in typed),
                "false_alarm_denominator": fa_denominator,
                "false_alarm_rate": (
                    sum(record["false_alarm"] for record in typed) / fa_denominator
                    if fa_denominator else None
                ),
                "median_response_time_ms": median_duration,
                "mean_confidence": (
                    sum(confidence_values) / len(confidence_values)
                    if confidence_values else None
                ),
            }

        false_safe_count = sum(record["false_safe"] for record in group)
        false_safe_denominator = sum(record["false_safe_eligible"] for record in group)
        stratified_false_safe = {}
        for label, consequence_state in (
            ("confirmed_remaining", Answer.YES.value),
            ("unresolved", Answer.CANNOT_TELL.value),
        ):
            matching = [
                record for record in group
                if record["ground_truth"]["relevant_consequence_remains"]
                == consequence_state
            ]
            count = sum(record["false_safe"] for record in matching)
            denominator = len(matching)
            stratified_false_safe[label] = {
                "count": count,
                "denominator": denominator,
                "rate": count / denominator if denominator else None,
            }
        false_alarm_count = sum(record["false_alarm"] for record in group)
        false_alarm_denominator = sum(record["false_alarm_eligible"] for record in group)
        result[condition] = {
            "trials": len(group),
            "by_question_type": by_type,
            "false_safe_count": false_safe_count,
            "false_safe_denominator": false_safe_denominator,
            "false_safe_rate": (
                false_safe_count / false_safe_denominator
                if false_safe_denominator else None
            ),
            "false_safe_by_consequence_state": stratified_false_safe,
            "false_alarm_count": false_alarm_count,
            "false_alarm_denominator": false_alarm_denominator,
            "false_alarm_rate": (
                false_alarm_count / false_alarm_denominator
                if false_alarm_denominator else None
            ),
        }
    return result


def write_dry_run_outputs(output_dir: str | Path, seed: int) -> tuple[Path, Path]:
    """Write local synthetic serialization fixtures, visibly separate from study data."""
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    data = simulate_dry_run(seed)
    json_path = destination / f"SYNTHETIC_DRY_RUN_seed-{seed}.json"
    csv_path = destination / f"SYNTHETIC_DRY_RUN_seed-{seed}.csv"
    json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if data["records"]:
        columns = ["dataset_label", *data["records"][0].keys()]
        with csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            for record in data["records"]:
                writer.writerow({"dataset_label": DRY_RUN_LABEL, **record,
                    "ground_truth": json.dumps(record["ground_truth"], ensure_ascii=False)})
    else:
        csv_path.write_text("dataset_label\n" + DRY_RUN_LABEL + "\n", encoding="utf-8")
    return json_path, csv_path
