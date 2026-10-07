"""Local deterministic browser demo for the frozen AuthorityLens pipeline."""

import logging
import hmac
import os
from dataclasses import fields, is_dataclass
from enum import Enum, StrEnum
from functools import wraps
from urllib.parse import urlsplit

from flask import Flask, abort, jsonify, make_response, redirect, render_template, request, url_for

from authority_lens import (
    AuthorityEngine,
    Delegation,
    Effect,
    EffectStatus,
    ExternalState,
    ExternalStatus,
    Grant,
    PathStatus,
    Principal,
    PrincipalType,
)
from consequence_model import translate_effective_state
from control_view import (
    ControlContext,
    build_authority_lens_control_view,
    build_baseline_control_view,
    build_control_view,
)
from pilot_sessions import PilotSessionError, PilotSessionManager


app = Flask(__name__)
app.config["PILOT_SESSION_COOKIE"] = "authoritylens_pilot_session"
pilot_sessions = PilotSessionManager()


def pilot_study_mode_enabled() -> bool:
    """Return whether the process is serving the supervised pilot surface only."""
    return os.environ.get("PILOT_STUDY_MODE", "").strip().casefold() in {
        "1", "true", "yes", "on",
    }


ORDINARY_DEMO_ENDPOINTS = {
    "index",
    "list_scenarios",
    "get_scenario",
    "post_transition",
    "reset_scenario",
}

# The local pilot never needs request access logs, which would include client addresses.
logging.getLogger("werkzeug").disabled = True


@app.before_request
def isolate_pilot_study_mode():
    """Hide ordinary demo pages and APIs during a participant study session."""
    if pilot_study_mode_enabled() and request.endpoint in ORDINARY_DEMO_ENDPOINTS:
        abort(404)


def _researcher_required(view):
    """Protect researcher controls with a separately supplied local secret."""
    @wraps(view)
    def protected(*args, **kwargs):
        secret = os.environ.get("PILOT_RESEARCHER_SECRET", "")
        # Fail closed when the local researcher secret has not been configured.
        if len(secret) < 32:
            return make_response("Researcher access is not configured.", 503)
        credentials = request.authorization
        supplied = credentials.password if credentials else ""
        valid = bool(
            credentials
            and credentials.type.casefold() == "basic"
            and credentials.username == "authoritylens-researcher"
            and hmac.compare_digest(supplied.encode("utf-8"), secret.encode("utf-8"))
        )
        if not valid:
            response = make_response("Researcher authentication required.", 401)
            response.headers["WWW-Authenticate"] = (
                'Basic realm="AuthorityLens researcher", charset="UTF-8"'
            )
            return response
        return view(*args, **kwargs)

    return protected


def _same_origin_researcher_post() -> bool:
    origin = request.headers.get("Origin")
    if not origin:
        return False
    parsed = urlsplit(origin)
    return (
        parsed.scheme.casefold() == request.scheme.casefold()
        and parsed.netloc.casefold() == request.host.casefold()
    )


@app.after_request
def prevent_pilot_response_caching(response):
    if request.path.startswith(("/pilot", "/api/pilot")):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
    return response


class ControlPhase(StrEnum):
    BEFORE_ACTION = "before_action"
    AFTER_ACTION = "after_action"

SCENARIOS = (
    {
        "id": "complete-revocation",
        "title": "Complete Revocation",
        "description": "Revoke Agent A's Gmail read permission and inspect what remains.",
        "initial_state": "Agent A has gmail.read authority.",
    },
    {
        "id": "residual-delegation",
        "title": "Residual Delegation",
        "description": (
            "Delegate Gmail read access to Agent B, then revoke Agent A. "
            "Issued delegations remain independent until explicitly revoked in this prototype."
        ),
        "initial_state": "Agent A has gmail.read authority; Agent B has no authority.",
        "assumption_note": (
            "Prototype assumption: an issued delegation remains independently active "
            "until that delegation is explicitly revoked."
        ),
    },
    {
        "id": "queued-action",
        "title": "Queued Action",
        "description": "Queue an email, then revoke Agent A's Gmail send permission.",
        "initial_state": "Agent A has gmail.send authority; no email is queued.",
    },
    {
        "id": "unknown-external-agent",
        "title": "Unknown External Agent",
        "description": (
            "Delegate to External Agent C, revoke Agent A, and simulate an "
            "unconfirmed revocation request."
        ),
        "initial_state": "Agent A has gmail.read authority; External Agent C is not yet delegated.",
    },
)

# Each key is the exact event prefix under which the listed next actions are valid.
ACTION_FLOW = {
    "complete-revocation": {
        (): ("revoke-gmail-access",),
        ("revoke-gmail-access",): (),
    },
    "residual-delegation": {
        (): ("delegate-read-agent-b",),
        ("delegate-read-agent-b",): ("revoke-agent-a",),
        ("delegate-read-agent-b", "revoke-agent-a"): (),
    },
    "queued-action": {
        (): ("queue-email",),
        ("queue-email",): ("revoke-gmail-send",),
        ("queue-email", "revoke-gmail-send"): ("cancel-email",),
        ("queue-email", "revoke-gmail-send", "cancel-email"): (),
    },
    "unknown-external-agent": {
        (): ("delegate-read-external-c",),
        ("delegate-read-external-c",): ("revoke-agent-a",),
        ("delegate-read-external-c", "revoke-agent-a"): ("send-revocation-request",),
        (
            "delegate-read-external-c",
            "revoke-agent-a",
            "send-revocation-request",
        ): ("confirm-c-revoked", "confirm-c-active"),
        (
            "delegate-read-external-c",
            "revoke-agent-a",
            "send-revocation-request",
            "confirm-c-revoked",
        ): (),
        (
            "delegate-read-external-c",
            "revoke-agent-a",
            "send-revocation-request",
            "confirm-c-active",
        ): (),
    },
}

ACTION_LABELS = {
    "revoke-gmail-access": ("Revoke Gmail Access", "Revoked Agent A's Gmail read grant."),
    "delegate-read-agent-b": ("Delegate Read Access to Agent B", "Delegated gmail.read from Agent A to Agent B."),
    "revoke-agent-a": ("Revoke Agent A", "Revoked Agent A's Gmail grant."),
    "queue-email": ("Queue Email", "Queued one email-send operation."),
    "revoke-gmail-send": ("Revoke Gmail Send", "Revoked Agent A's gmail.send grant."),
    "cancel-email": ("Cancel Queued Email", "Cancelled the queued email-send operation."),
    "delegate-read-external-c": ("Delegate Read Access to External Agent C", "Delegated gmail.read to External Agent C; C's status is unknown."),
    "send-revocation-request": ("Send Revocation Request to Agent C", "Sent a simulated request; no confirmation was received."),
    "confirm-c-revoked": ("Confirm C Revoked", "Simulation set External Agent C to confirmed revoked."),
    "confirm-c-active": ("Confirm C Still Active", "Simulation set External Agent C to confirmed active."),
}

REVOKE_ACTIONS = {
    "complete-revocation": "revoke-gmail-access",
    "residual-delegation": "revoke-agent-a",
    "queued-action": "revoke-gmail-send",
    "unknown-external-agent": "revoke-agent-a",
}


def _new_engine() -> AuthorityEngine:
    engine = AuthorityEngine()
    engine.add_principal(Principal("human", PrincipalType.HUMAN))
    engine.add_principal(Principal("agent-a", PrincipalType.AGENT, "human"))
    return engine


def _initial_state(scenario_id: str) -> tuple[AuthorityEngine, str]:
    engine = _new_engine()
    scope = "gmail.send" if scenario_id == "queued-action" else "gmail.read"
    grant_id = "g-human-a-send" if scope == "gmail.send" else "g-human-a-read"
    engine.add_grant(Grant(grant_id, "agent-a", scope, "human"))
    return engine, scope


def _apply_event(engine: AuthorityEngine, scenario_id: str, event: str) -> bool:
    """Apply one validated event; return whether the revoke action is confirmed."""
    if event == "revoke-gmail-access":
        engine.revoke_grant("agent-a", "gmail.read")
        return True
    if event == "delegate-read-agent-b":
        engine.add_principal(Principal("agent-b", PrincipalType.AGENT, "agent-a"))
        engine.add_delegation(Delegation("d-a-b-read", "agent-a", "agent-b", "gmail.read"))
    elif event == "revoke-agent-a":
        engine.revoke_grant("agent-a", "gmail.read" if scenario_id != "queued-action" else "gmail.send")
        return True
    elif event == "queue-email":
        engine.add_effect(
            Effect(
                "effect-queued-email",
                "agent-a",
                "email.send",
                EffectStatus.QUEUED,
                "gmail.send",
            )
        )
    elif event == "revoke-gmail-send":
        engine.revoke_grant("agent-a", "gmail.send")
        return True
    elif event == "cancel-email":
        engine.cancel_effect("effect-queued-email")
    elif event == "delegate-read-external-c":
        engine.add_principal(Principal("agent-c", PrincipalType.EXTERNAL, "agent-a"))
        engine.add_delegation(Delegation("d-a-c-read", "agent-a", "agent-c", "gmail.read"))
        engine.set_external_state(ExternalState("agent-c", ExternalStatus.UNKNOWN))
    elif event == "send-revocation-request":
        # A request without a response leaves the external state UNKNOWN.
        pass
    elif event == "confirm-c-revoked":
        engine.set_external_state(ExternalState("agent-c", ExternalStatus.CONFIRMED_REVOKED))
    elif event == "confirm-c-active":
        engine.set_external_state(ExternalState("agent-c", ExternalStatus.CONFIRMED_ACTIVE))
    else:
        raise ValueError(f"unsupported event {event!r}")
    return False


def _replay(scenario_id: str, events: tuple[str, ...]) -> tuple[AuthorityEngine, str, bool]:
    if scenario_id not in ACTION_FLOW:
        raise KeyError(scenario_id)
    engine, scope = _initial_state(scenario_id)
    applied: tuple[str, ...] = ()
    action_confirmed = False
    for event in events:
        if event not in ACTION_FLOW[scenario_id].get(applied, ()):
            raise ValueError(f"event {event!r} is not valid after {applied!r}")
        action_confirmed = _apply_event(engine, scenario_id, event) or action_confirmed
        applied += (event,)
    return engine, scope, action_confirmed


def _serialize(value):
    if is_dataclass(value):
        return {item.name: _serialize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    return value


def _principal_label(principal_id: str, engine: AuthorityEngine | None = None) -> str:
    principal = engine.principals.get(principal_id) if engine else None
    if principal and principal.type == PrincipalType.EXTERNAL:
        return f"External Agent {principal_id.removeprefix('agent-').upper()}"
    if principal_id.startswith("agent-"):
        return f"Agent {principal_id.removeprefix('agent-').upper()}"
    return principal_id.replace("-", " ").title()


def _resource_label(control_view, resource: str, original_scope: str | None = None) -> str:
    target = control_view.context.target_principal
    target_scopes = [
        item.scope
        for item in (*control_view.active_items, *control_view.residual_items)
        if item.principal_id == target
    ]
    target_scopes.extend(
        item.effect.required_scope
        for item in control_view.pending_items
        if item.effect.principal_id == target
    )
    # Preserve the scope of the attempted control action after revocation and effect cancellation.
    if not target_scopes and original_scope:
        target_scopes.append(original_scope)
    if "gmail.send" in target_scopes and "gmail.read" not in target_scopes:
        return f"{resource} Sending"
    return f"{resource} Access"


def _local_state(baseline, context: ControlContext) -> dict:
    principal = _principal_label(context.target_principal)
    if baseline.access_status == "UNKNOWN":
        return {"status": "UNKNOWN", "text": f"{principal}'s {context.resource} access cannot be verified."}
    if baseline.access_status == "ON":
        return {"status": "REMAINING", "text": f"{principal} still has {context.resource} access."}
    if context.requested_action.casefold() == "revoke" and context.action_confirmed:
        return {"status": "STOPPED", "text": f"{principal} no longer has {context.resource} access."}
    return {"status": "OFF", "text": f"No current {context.resource} permission is shown for the target."}


def _entry_status(entries) -> str:
    statuses = {entry.path_status for entry in entries}
    if PathStatus.UNCERTAIN in statuses:
        return "UNKNOWN"
    if PathStatus.RESIDUAL in statuses:
        return "RESIDUAL"
    if PathStatus.CLEAN in statuses:
        return "ACTIVE"
    return "REVOKED"


def _authority_chain(engine: AuthorityEngine, effective_state) -> list[dict]:
    all_entries = [
        *effective_state.active_authority,
        *effective_state.unresolved_authority,
    ]
    chain: list[dict] = []

    for grant in engine.grants:
        matching = [
            item for item in all_entries
            if item.root_source_grant_id == grant.id and item.source == "grant"
        ]
        if not grant.active:
            status = "REVOKED"
        elif any(item.path_status == PathStatus.UNCERTAIN for item in matching):
            status = "UNKNOWN"
        else:
            status = _entry_status(matching)
        chain.append({
            "from": _principal_label(grant.source_principal_id, engine),
            "to": _principal_label(grant.principal_id, engine),
            "scope": grant.scope,
            "status": status,
        })

    for delegation in engine.delegations:
        matching = [
            item for item in all_entries
            if item.principal_id == delegation.to_id
            and item.delegation_path
            and item.delegation_path[-1] == delegation.id
        ]
        if not delegation.active:
            status = "REVOKED"
        else:
            status = _entry_status(matching)
        chain.append({
            "from": _principal_label(delegation.from_id, engine),
            "to": _principal_label(delegation.to_id, engine),
            "scope": delegation.scope,
            "status": status,
        })

    scope_pairs = {
        (grant.principal_id, grant.scope) for grant in engine.grants
    } | {
        (delegation.to_id, delegation.scope) for delegation in engine.delegations
    }
    for principal_id, scope in sorted(scope_pairs):
        matching = [
            item for item in all_entries
            if item.principal_id == principal_id and item.scope == scope
        ]
        status = _entry_status(matching)
        resource = "Gmail Sending" if scope == "gmail.send" else "Gmail"
        chain.append({
            "from": _principal_label(principal_id, engine),
            "to": resource,
            "scope": scope,
            "status": status,
        })
    return chain


def _current_state_items(scenario_id: str, events: tuple[str, ...], control_view) -> list[str]:
    """Describe current facts without labeling them as a revoke outcome."""
    items = [item.description for item in control_view.active_items]
    items.extend(item.description for item in control_view.residual_items)

    if scenario_id == "residual-delegation" and "delegate-read-agent-b" not in events:
        items.append("Agent B currently has no delegated Gmail access.")
    elif scenario_id == "queued-action" and "queue-email" not in events:
        items.append("No email is currently queued.")
    elif scenario_id == "unknown-external-agent" and "delegate-read-external-c" not in events:
        items.append("External Agent C has not yet received delegated access.")

    items.extend(item.description for item in control_view.pending_items)
    items.extend(item.description for item in control_view.unknown_items)
    return items


def build_scenario_payload(scenario_id: str, events=()) -> dict:
    if not isinstance(events, (list, tuple)):
        raise ValueError("events must be a list of event IDs")
    events = tuple(events)
    engine, scope, action_confirmed = _replay(scenario_id, events)
    metadata = next(item for item in SCENARIOS if item["id"] == scenario_id)
    context = ControlContext(
        "Gmail", "revoke", "agent-a", action_confirmed=action_confirmed
    )

    # Each replay rebuilds machine truth, then both render models use the same ControlView.
    effective_state = engine.calculate()
    consequence_summary = translate_effective_state(effective_state)
    control_view = build_control_view(context, consequence_summary)
    baseline_view = build_baseline_control_view(control_view)
    authority_view = build_authority_lens_control_view(control_view)

    baseline_data = _serialize(baseline_view)
    resource_label = _resource_label(control_view, context.resource, scope)
    baseline_data.update(
        target_principal_display=_principal_label(context.target_principal),
        resource_label=resource_label,
        label=f"{resource_label}: {baseline_view.access_status}",
    )
    authority_data = _serialize(authority_view)
    authority_data["local_state"] = _local_state(baseline_view, context)
    if not (control_view.active_items or control_view.residual_items or control_view.pending_items or control_view.unknown_items):
        authority_data["empty_state_message"] = (
            "No remaining Gmail capabilities, pending actions, or unresolved access."
        )

    control_phase = (
        ControlPhase.AFTER_ACTION
        if REVOKE_ACTIONS[scenario_id] in events
        else ControlPhase.BEFORE_ACTION
    )
    current_state = None
    if control_phase == ControlPhase.BEFORE_ACTION:
        current_state = {
            "label": "Current State",
            "items": _current_state_items(scenario_id, events, control_view),
        }
        # Phase 2B's result calculation is unchanged. Before the revoke event, its
        # outcome is not presented as a result of an action that has not happened.
        authority_data["outcome"] = None
        authority_data["headline"] = None

    system_state = {
        "active_authority": _serialize([
            item for item in effective_state.active_authority
            if item.path_status == PathStatus.CLEAN
        ]),
        "residual_authority": _serialize([
            item for item in effective_state.active_authority
            if item.path_status == PathStatus.RESIDUAL
        ]),
        "unresolved_authority": _serialize(effective_state.unresolved_authority),
        "pending_effects": _serialize(effective_state.pending_effects),
        "unknown_states": _serialize(effective_state.unknown_states),
    }
    applied = tuple(events)
    timeline = [{"kind": "initial", "label": metadata["initial_state"]}]
    timeline.extend(
        {"kind": "event", "label": ACTION_LABELS[event][1]}
        for event in events
    )
    available_actions = [
        {"id": event, "label": ACTION_LABELS[event][0]}
        for event in ACTION_FLOW[scenario_id].get(applied, ())
    ]
    return {
        "scenario": metadata,
        "control_phase": control_phase,
        "current_state": current_state,
        "event_log": list(events),
        "timeline": timeline,
        "available_actions": available_actions,
        "baseline": baseline_data,
        "authority_lens": authority_data,
        "authority_chain": _authority_chain(engine, effective_state),
        "system_state": system_state,
    }


def transition_scenario(scenario_id: str, events, action: str) -> dict:
    current = tuple(events)
    if action not in ACTION_FLOW.get(scenario_id, {}).get(current, ()):
        raise ValueError(f"action {action!r} is not available after {current!r}")
    return build_scenario_payload(scenario_id, current + (action,))


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/pilot")
def pilot_page():
    """Serve the participant flow; private schedule/scoring data stay server-side."""
    return render_template("pilot.html")


def _pilot_token() -> str | None:
    return request.cookies.get(app.config["PILOT_SESSION_COOKIE"])


def _participant_state_response(action=None, *args, **kwargs):
    token = _pilot_token()
    if token is None:
        return jsonify({"error": "no active local session"}), 401
    try:
        state = action(token, *args, **kwargs) if action else pilot_sessions.current(token)
        return jsonify(state)
    except PilotSessionError as error:
        status = 404 if "not found" in str(error) else 409
        return jsonify({"error": str(error)}), status
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@app.get("/api/pilot/state")
def get_pilot_state():
    return _participant_state_response()


@app.post("/api/pilot/information/continue")
def continue_pilot_information():
    return _participant_state_response(pilot_sessions.continue_from_information)


@app.post("/api/pilot/briefing/continue")
def continue_pilot_briefing():
    return _participant_state_response(pilot_sessions.start_practice)


@app.post("/api/pilot/practice/start")
def start_pilot_practice():
    return _participant_state_response(pilot_sessions.start_practice)


@app.post("/api/pilot/practice/submit")
def submit_pilot_practice():
    body = request.get_json(silent=True) or {}
    return _participant_state_response(
        pilot_sessions.submit_practice, body.get("response", "")
    )


@app.post("/api/pilot/practice/continue")
def continue_pilot_practice():
    return _participant_state_response(pilot_sessions.begin_measured)


@app.post("/api/pilot/trial/rendered")
def acknowledge_pilot_trial_rendered():
    token = _pilot_token()
    if token is None:
        return jsonify({"error": "no active local session"}), 401
    body = request.get_json(silent=True) or {}
    try:
        pilot_sessions.mark_trial_rendered(token, body.get("order"))
        return jsonify({"ready": True})
    except PilotSessionError as error:
        return jsonify({"error": str(error)}), 409
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/pilot/response")
def submit_pilot_response():
    body = request.get_json(silent=True) or {}
    return _participant_state_response(
        pilot_sessions.submit_response,
        body.get("response", ""),
        body.get("confidence"),
    )


@app.post("/api/pilot/abort")
def abort_pilot_session():
    return _participant_state_response(pilot_sessions.abort)


@app.post("/api/pilot/withdraw")
def withdraw_pilot_session():
    return _participant_state_response(pilot_sessions.withdraw)


@app.get("/pilot/researcher")
@_researcher_required
def pilot_researcher_page():
    return render_template(
        "pilot_researcher.html", sessions=pilot_sessions.researcher_sessions()
    )


@app.post("/pilot/researcher/start")
@_researcher_required
def start_researcher_session():
    if not _same_origin_researcher_post():
        return make_response("A same-origin researcher request is required.", 403)
    seed_text = request.form.get("seed")
    try:
        if seed_text is None or not seed_text.isdecimal():
            raise ValueError("seed must be an integer from 0 to 15")
        seed = int(seed_text)
        token = pilot_sessions.create_session(seed)
        launch_token = pilot_sessions.create_launch_token(token)
    except (TypeError, ValueError) as error:
        return make_response(str(error), 400)
    return render_template(
        "pilot_launch_created.html",
        launch_url=url_for("launch_pilot_session", launch_token=launch_token),
    )


@app.get("/pilot/launch/<launch_token>")
def launch_pilot_session(launch_token: str):
    token = pilot_sessions.consume_launch_token(launch_token)
    if token is None:
        return make_response("This participant launch link is invalid, expired, or already used.", 410)
    response = make_response(redirect(url_for("pilot_page")))
    response.set_cookie(
        app.config["PILOT_SESSION_COOKIE"], token,
        httponly=True, samesite="Strict", secure=False, path="/",
    )
    return response


@app.get("/pilot/researcher/export/<token>.json")
@_researcher_required
def export_researcher_session_json(token: str):
    try:
        data = pilot_sessions.export_data(token)
    except PilotSessionError:
        return jsonify({"error": "session not found"}), 404
    response = jsonify(data)
    response.headers["Content-Disposition"] = (
        f'attachment; filename="authoritylens-pilot-{data["session"]["session_run_id"]}'
        f'-slot-{data["session"]["seed"] + 1:02d}.json"'
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/pilot/researcher/export/<token>.csv")
@_researcher_required
def export_researcher_session_csv(token: str):
    try:
        data = pilot_sessions.export_data(token)
        csv_text = pilot_sessions.export_csv(token)
    except PilotSessionError:
        return make_response("session not found", 404)
    response = make_response(csv_text)
    response.mimetype = "text/csv"
    response.headers["Content-Disposition"] = (
        f'attachment; filename="authoritylens-pilot-{data["session"]["session_run_id"]}'
        f'-slot-{data["session"]["seed"] + 1:02d}.csv"'
    )
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/scenarios")
def list_scenarios():
    return jsonify(SCENARIOS)


@app.get("/api/scenarios/<scenario_id>")
def get_scenario(scenario_id: str):
    try:
        return jsonify(build_scenario_payload(scenario_id))
    except KeyError:
        return jsonify({"error": "unknown scenario"}), 404


@app.post("/api/scenarios/<scenario_id>/transition")
def post_transition(scenario_id: str):
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(transition_scenario(scenario_id, body.get("events", []), body.get("action", "")))
    except KeyError:
        return jsonify({"error": "unknown scenario"}), 404
    except (TypeError, ValueError) as error:
        return jsonify({"error": str(error)}), 400


@app.post("/api/scenarios/<scenario_id>/reset")
def reset_scenario(scenario_id: str):
    try:
        return jsonify(build_scenario_payload(scenario_id))
    except KeyError:
        return jsonify({"error": "unknown scenario"}), 404


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
