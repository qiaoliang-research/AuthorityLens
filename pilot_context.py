"""Neutral participant context derived only from modeled structure."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def _principal_label(principal: dict[str, Any]) -> str:
    principal_id = principal["id"]
    suffix = principal_id.removeprefix("agent-").upper()
    if principal["type"] == "human":
        return "Human"
    if principal["type"] == "external":
        return f"External Agent {suffix}"
    return f"Agent {suffix}"


def _features(tasks: list[dict[str, Any]]) -> tuple[dict[str, str], set[str], set[str]]:
    principals: dict[str, str] = {}
    scopes: set[str] = set()
    resources: set[str] = set()
    for task in tasks:
        resources.add(task.get("resource", "Gmail"))
        state = task.get("state", {})
        for principal in state.get("principals", []):
            principals[principal["id"]] = principal["type"]
        for field in ("grants", "delegations", "effects"):
            scopes.update(
                item["scope"] if field != "effects" else item["required_scope"]
                for item in state.get(field, [])
            )
        question_scope = task.get("question", {}).get("scope")
        if question_scope:
            scopes.add(question_scope)
    return principals, scopes, resources


def _context_for(tasks: list[dict[str, Any]]) -> str:
    principals, scopes, resources = _features(tasks)
    labels = sorted(
        (_principal_label({"id": principal_id, "type": principal_type})
         for principal_id, principal_type in principals.items()),
        key=str.casefold,
    )
    labels = [
        label for label in labels
        if label != "Human"
    ]
    resource_text = " and ".join(sorted(resources, key=str.casefold))
    actions = []
    if "gmail.read" in scopes:
        actions.append(f"{resource_text}-read")
    if "gmail.send" in scopes:
        actions.append("email-send")
    action_text = " and ".join(actions) if actions else f"{resource_text} access"
    actor_text = ", ".join(labels) if labels else "the listed agents"
    return (
        f"This modeled workflow includes {actor_text}. "
        f"The question concerns a {action_text} workflow after an access-control action."
    )


def build_neutral_scenario_contexts(
    tasks: list[dict[str, Any]],
) -> dict[str, str]:
    """Give matched variants the same context without exposing their differing state."""
    by_pair: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        pair_id = task.get("matched_pair")
        if pair_id:
            by_pair[pair_id].append(task)

    result: dict[str, str] = {}
    for task in tasks:
        pair_id = task.get("matched_pair")
        context_tasks = by_pair[pair_id] if pair_id else [task]
        labels, scopes, resources = _features(context_tasks)
        actor_labels = sorted(
            (
                _principal_label({"id": principal_id, "type": principal_type})
                for principal_id, principal_type in labels.items()
                if principal_type != "human"
            ),
            key=str.casefold,
        )
        actor_text = ", ".join(actor_labels) if actor_labels else "the listed agents"
        resource_text = " and ".join(sorted(resources, key=str.casefold))
        if pair_id == "multihop_message_readability":
            context = (
                f"This modeled workflow contains {actor_text}. "
                f"Agent A participated in a delegated {resource_text}-read workflow "
                "before the current control state shown below."
            )
        elif pair_id == "queued_send_sufficiency":
            context = (
                "Agent A previously initiated an email-send workflow, "
                "and a control action was later applied."
            )
        elif pair_id == "external_message_readability":
            context = (
                f"This modeled workflow contains {actor_text}. "
                f"A {resource_text} access-control action has been applied."
            )
        else:
            context = _context_for(context_tasks)
        result[task["task_id"]] = context
    return result
