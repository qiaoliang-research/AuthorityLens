"""In-memory, local-only participant session runner for the exploratory pilot."""

from __future__ import annotations

import csv
import io
import json
import secrets
import time
from typing import Any, Callable

from pilot_context import build_neutral_scenario_contexts
from pilot_study import (
    Answer,
    Condition,
    _build_session_plan,
    calculate_metrics,
    derive_ground_truth,
    load_task_bank,
    score_trial,
)


class PilotSessionError(RuntimeError):
    """Raised when a session action is invalid for its current phase."""


class PilotSessionManager:
    """Keep session assignments and scoring records in process memory only."""

    TRIAL_COUNT = 9
    LAUNCH_TOKEN_TTL_SECONDS = 10 * 60
    PRACTICE_TRIAL = {
        "question": "Can Agent A's calendar reminder still appear at 3:00 PM?",
        "stimulus": {
            "target": "Agent A",
            "resource_label": "Calendar reminder",
            "status": "SCHEDULED",
            "detail": "One reminder is already scheduled for 3:00 PM.",
        },
    }

    def __init__(self, clock: Callable[[], float] | None = None):
        self._clock = clock or time.monotonic
        self._sessions: dict[str, dict[str, Any]] = {}
        self._launch_tokens: dict[str, tuple[str, float]] = {}
        self._task_catalog = load_task_bank()
        self._tasks_by_id = {task["task_id"]: task for task in self._task_catalog}
        self._neutral_contexts = build_neutral_scenario_contexts(self._task_catalog)

    def create_session(self, seed: int) -> str:
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 15:
            raise ValueError("seed must be an integer from 0 to 15")
        plan = _build_session_plan(seed)
        if len(plan) != self.TRIAL_COUNT:
            raise PilotSessionError("the private schedule must contain nine trials")
        token = secrets.token_urlsafe(32)
        self._sessions[token] = {
            "session_run_id": secrets.token_hex(16),
            "seed": seed,
            "condition": plan[0]["condition"],
            "plan": plan,
            "phase": "information",
            "records": {},
            "rendered_at": None,
            "withdrawn": False,
        }
        return token

    def create_launch_token(self, session_token: str) -> str:
        """Create a short-lived, single-use bridge from researcher to participant."""
        self._session(session_token)
        launch_token = secrets.token_urlsafe(32)
        self._launch_tokens[launch_token] = (
            session_token,
            self._clock() + self.LAUNCH_TOKEN_TTL_SECONDS,
        )
        return launch_token

    def consume_launch_token(self, launch_token: str) -> str | None:
        """Consume a launch token once; expiry or reuse never reveals its session."""
        entry = self._launch_tokens.pop(launch_token, None)
        if entry is None:
            return None
        session_token, expires_at = entry
        if self._clock() >= expires_at or session_token not in self._sessions:
            return None
        return session_token

    def _session(self, token: str) -> dict[str, Any]:
        if not token or token not in self._sessions:
            raise PilotSessionError("session not found; start a local researcher session first")
        return self._sessions[token]

    @staticmethod
    def _public_stimulus(stimulus: dict[str, Any]) -> dict[str, Any]:
        """Return render data only, without view name or scoring-side annotations."""
        local = stimulus.get("target_local_state")
        if local is None:
            local = {
                key: stimulus[key]
                for key in ("target", "resource_label", "status", "text")
                if key in stimulus
            }
        public = {"local_permission": local}
        for key in ("headline", "sections", "empty", "empty_state_message"):
            if key in stimulus:
                public[key] = stimulus[key]
        return public

    def current(self, token: str) -> dict[str, Any]:
        session = self._session(token)
        phase = session["phase"]
        public: dict[str, Any] = {"phase": phase}
        if phase == "information":
            public["message"] = (
                "This is a local research-prototype session. This information page is a "
                "placeholder, not approved study consent. No external service receives responses."
            )
        elif phase == "briefing":
            public["message"] = (
                "These fictional scenarios describe a completed access-control action. "
                "Permission to start a new action is separate from an operation already queued. "
                "For these scenarios, an already-issued delegation may remain active after an "
                "upstream grant is revoked. An unknown external state is unresolved: it is "
                "neither confirmed active nor confirmed revoked. The scenario context names "
                "the modeled actors relevant to the question. The interface panel may summarize "
                "only part of the current system state."
            )
        elif phase == "practice":
            public["trial"] = {
                "order": 0,
                "total": 1,
                "question": self.PRACTICE_TRIAL["question"],
                "stimulus": dict(self.PRACTICE_TRIAL["stimulus"]),
            }
        elif phase == "practice_feedback":
            public["message"] = (
                "Practice complete. The practice response is not scored or included in analysis. "
                "Measured trials will not provide correctness feedback."
            )
        elif phase == "trial":
            order = len(session["records"]) + 1
            trial = session["plan"][order - 1]
            public["trial"] = {
                "order": order,
                "total": self.TRIAL_COUNT,
                "scenario_context": self._neutral_contexts[trial["task_id"]],
                "question": trial["question"],
                "stimulus": self._public_stimulus(trial["stimulus"]),
            }
            public["response_options"] = [answer.value for answer in Answer]
            public["confidence_options"] = [1, 2, 3, 4, 5]
        elif phase == "complete":
            public["message"] = "This session is complete. You may close this page."
        elif phase == "incomplete":
            public["message"] = (
                "Your submitted answers were discarded. This session is marked incomplete."
                if session["withdrawn"]
                else "This session was stopped before all measured trials were answered. It is marked incomplete."
            )
        return public

    def continue_from_information(self, token: str) -> dict[str, Any]:
        session = self._session(token)
        self._require_phase(session, "information")
        session["phase"] = "briefing"
        return self.current(token)

    def start_practice(self, token: str) -> dict[str, Any]:
        session = self._session(token)
        # Accept information directly for the small manager-level test helper;
        # the browser uses the explicit briefing page before starting practice.
        if session["phase"] not in {"information", "briefing"}:
            raise PilotSessionError("practice can only start after the briefing")
        session["phase"] = "practice"
        return self.current(token)

    def submit_practice(self, token: str, response: str) -> dict[str, Any]:
        session = self._session(token)
        self._require_phase(session, "practice")
        self._validate_response(response)
        session["phase"] = "practice_feedback"
        return self.current(token)

    def begin_measured(self, token: str) -> dict[str, Any]:
        session = self._session(token)
        self._require_phase(session, "practice_feedback")
        session["phase"] = "trial"
        return self.current(token)

    def mark_trial_rendered(self, token: str, order: int) -> None:
        session = self._session(token)
        self._require_phase(session, "trial")
        expected_order = len(session["records"]) + 1
        if (
            isinstance(order, bool)
            or not isinstance(order, int)
            or order != expected_order
        ):
            raise PilotSessionError("render acknowledgement does not match the current trial")
        # The browser sends this only after painting the full stimulus and question.
        # Retries are idempotent so they cannot restart or extend the timer.
        if session["rendered_at"] is None:
            session["rendered_at"] = self._clock()

    def submit_response(
        self, token: str, response: str, confidence: int | None = None
    ) -> dict[str, Any]:
        session = self._session(token)
        self._require_phase(session, "trial")
        if session["rendered_at"] is None:
            raise PilotSessionError("the complete trial must be rendered before response")
        normalized = self._validate_response(response)
        if confidence is not None and (
            isinstance(confidence, bool)
            or not isinstance(confidence, int)
            or not 1 <= confidence <= 5
        ):
            raise ValueError("confidence must be an integer from 1 to 5")

        submitted_at = self._clock()
        response_time_ms = max(0, round((submitted_at - session["rendered_at"]) * 1000))
        order = len(session["records"]) + 1
        private_trial = self._scoring_trial(session, order)
        scored = score_trial(private_trial, normalized, response_time_ms, confidence)
        session["records"][order] = self._record_with_quality_fields(
            session, order, scored
        )
        session["rendered_at"] = None
        session["phase"] = "complete" if order == self.TRIAL_COUNT else "trial"
        return self.current(token)

    def abort(self, token: str) -> dict[str, Any]:
        session = self._session(token)
        if session["phase"] == "complete":
            raise PilotSessionError("a completed session cannot be marked incomplete")
        session["phase"] = "incomplete"
        session["rendered_at"] = None
        return self.current(token)

    def withdraw(self, token: str) -> dict[str, Any]:
        """Stop the session and remove all submitted responses from memory."""
        session = self._session(token)
        if session["phase"] == "complete":
            raise PilotSessionError("a completed session cannot be withdrawn")
        session["records"].clear()
        session["rendered_at"] = None
        session["withdrawn"] = True
        session["phase"] = "incomplete"
        return self.current(token)

    def _scoring_trial(self, session: dict[str, Any], order: int) -> dict[str, Any]:
        trial = session["plan"][order - 1]
        task = self._tasks_by_id[trial["task_id"]]
        return {
            **trial,
            "ground_truth": derive_ground_truth(task),
            "view_supported_answer": task["view_supported_answer_by_condition"][
                session["condition"]
            ],
            "question_type": task["question_type"],
            "false_safe_rule": task["false_safe_rule"],
        }

    @staticmethod
    def _record_with_quality_fields(
        session: dict[str, Any], order: int, scored: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            **scored,
            "seed": session["seed"],
            "session_relative_order": order,
            "condition": session["condition"],
            "missing_response": False,
        }

    @staticmethod
    def _validate_response(response: str) -> str:
        normalized = " ".join(str(response).strip().upper().replace("_", " ").replace("-", " ").split())
        allowed = {answer.value for answer in Answer}
        if normalized not in allowed:
            raise ValueError("response must be YES, NO, or CANNOT TELL")
        return normalized

    @staticmethod
    def _require_phase(session: dict[str, Any], phase: str) -> None:
        if session["phase"] != phase:
            raise PilotSessionError(f"session must be in {phase} phase")

    def export_data(self, token: str) -> dict[str, Any]:
        session = self._session(token)
        answered = [session["records"][n] for n in sorted(session["records"])]
        completed = session["phase"] == "complete" and len(answered) == self.TRIAL_COUNT
        rows = []
        for order, trial in enumerate(session["plan"], start=1):
            record = session["records"].get(order)
            if record is None:
                task = self._tasks_by_id[trial["task_id"]]
                record = {
                    "trial_index": order,
                    "trial_id": f"{trial['task_id']}-{order:02d}",
                    "task_id": trial["task_id"],
                    "scenario_id": trial["scenario_id"],
                    "question_type": task["question_type"],
                    "question": trial["question"],
                    "ground_truth": derive_ground_truth(task),
                    "response": None,
                    "correct": None,
                    "evidence_aligned": None,
                    "false_safe_eligible": None,
                    "false_safe": None,
                    "false_alarm_eligible": None,
                    "false_alarm": None,
                    "response_time_ms": None,
                    "confidence": None,
                    "seed": session["seed"],
                    "session_relative_order": order,
                    "condition": session["condition"],
                    "missing_response": True,
                }
            rows.append(record)
        metrics_by_condition = calculate_metrics(answered)
        status = (
            "complete" if completed
            else "incomplete" if session["phase"] == "incomplete"
            else "in_progress"
        )
        return {
            "session": {
                "status": status,
                "completed": completed,
                "trial_count": self.TRIAL_COUNT,
                "response_count": len(answered),
                "missing_response_indicator": len(answered) != self.TRIAL_COUNT,
                "withdrawn": session["withdrawn"],
                "session_run_id": session["session_run_id"],
                "seed": session["seed"],
                "condition": session["condition"],
                "practice_included_in_analysis": False,
            },
            "records": rows,
            "metrics": metrics_by_condition[session["condition"]],
        }

    def export_csv(self, token: str) -> str:
        export = self.export_data(token)
        buffer = io.StringIO(newline="")
        records = export["records"]
        session_fields = (
            "completed", "status", "trial_count", "response_count",
            "missing_response_indicator", "session_run_id",
        )
        fieldnames = [*session_fields, *(list(records[0]) if records else [])]
        writer = csv.DictWriter(buffer, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in records:
            row = {**export["session"], **row}
            writer.writerow({
                key: value if not isinstance(value, (dict, list)) else json.dumps(value, ensure_ascii=False)
                for key, value in row.items()
            })
        return buffer.getvalue()

    def researcher_sessions(self) -> list[dict[str, Any]]:
        rows = []
        for token, session in reversed(list(self._sessions.items())):
            export = self.export_data(token)
            rows.append({
                "token": token,
                "session_run_id": session["session_run_id"],
                "seed": session["seed"],
                "condition": session["condition"],
                "status": export["session"]["status"],
                "completed": export["session"]["completed"],
                "response_count": export["session"]["response_count"],
            })
        return rows
