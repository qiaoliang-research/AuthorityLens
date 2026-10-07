import csv
import json
from pathlib import Path

import pytest

from pilot_study import (
    Answer,
    Condition,
    QuestionType,
    build_stimulus,
    build_stimulus_pair,
    build_session_schedule,
    calculate_metrics,
    derive_ground_truth,
    derive_view_supported_answer,
    load_task_bank,
    score_trial,
    simulate_dry_run,
    write_dry_run_outputs,
    _build_session_plan,
)


def _trial(
    answer,
    consequence_remains,
    task_id="T-test",
    view_answer=None,
    question_type=QuestionType.DIRECT_RETRIEVAL.value,
    false_safe_if=None,
    false_alarm_if=None,
):
    if false_safe_if is None:
        false_safe_if = [Answer.NO.value] if consequence_remains != Answer.NO.value else []
    if false_alarm_if is None:
        false_alarm_if = [Answer.YES.value] if answer == Answer.NO.value else []
    return {
        "trial_index": 1,
        "task_id": task_id,
        "scenario_id": "scenario-test",
        "condition": Condition.TARGET_LOCAL.value,
        "question": "Can this modeled action still happen?",
        "question_type": question_type,
        "ground_truth": {
            "answer": answer,
            "relevant_consequence_remains": consequence_remains,
        },
        "view_supported_answer": view_answer or answer,
        "false_safe_rule": {
            "false_safe_if": false_safe_if,
            "false_alarm_if": false_alarm_if,
        },
    }


def test_score_trial_marks_a_factual_yes_as_correct_without_false_safe():
    result = score_trial(_trial(Answer.YES.value, Answer.YES.value), "YES", 840, confidence=4)

    assert result["correct"] is True
    assert result["false_safe"] is False
    assert result["false_alarm"] is False
    assert result["response_time_ms"] == 840
    assert result["confidence"] == 4


def test_no_on_a_remaining_consequence_is_a_false_safe_error():
    result = score_trial(_trial(Answer.YES.value, Answer.YES.value), "NO", 1200)

    assert result["correct"] is False
    assert result["false_safe"] is True
    assert result["false_alarm"] is False


def test_yes_when_ground_truth_rules_out_a_consequence_is_a_false_alarm():
    result = score_trial(_trial(Answer.NO.value, Answer.NO.value), "YES", 900)

    assert result["correct"] is False
    assert result["false_safe"] is False
    assert result["false_alarm"] is True


def test_cannot_tell_is_a_scored_answer_and_unknown_no_is_false_safe():
    uncertain = _trial(Answer.CANNOT_TELL.value, Answer.CANNOT_TELL.value)
    correct = score_trial(uncertain, "CANNOT TELL", 1500)
    false_safe = score_trial(uncertain, "NO", 1500)
    unsupported_active_claim = score_trial(uncertain, "YES", 1500)

    assert correct["correct"] is True
    assert correct["false_safe"] is False
    assert false_safe["correct"] is False
    assert false_safe["false_safe"] is True
    assert false_safe["false_alarm"] is False
    assert unsupported_active_claim["correct"] is False
    assert unsupported_active_claim["false_safe"] is False
    assert unsupported_active_claim["false_alarm"] is False


def test_cannot_tell_response_is_never_false_safe():
    result = score_trial(_trial("YES", "YES"), "CANNOT TELL", 900)

    assert result["correct"] is False
    assert result["false_safe"] is False


def test_transfer_item_uses_its_question_specific_false_safe_polarity():
    transfer = _trial(
        answer="NO",
        consequence_remains="YES",
        question_type=QuestionType.TRANSFER_INFERENCE.value,
        false_safe_if=["YES"],
        false_alarm_if=[],
    )

    sufficient = score_trial(transfer, "YES", 720)
    cautious = score_trial(transfer, "CANNOT TELL", 800)

    assert sufficient["question_type"] == QuestionType.TRANSFER_INFERENCE.value
    assert sufficient["false_safe"] is True
    assert sufficient["correct"] is False
    assert cautious["false_safe"] is False


def test_target_local_cannot_tell_is_view_aligned_without_being_ground_truth_correct():
    hidden_residual = _trial(
        Answer.YES.value,
        Answer.YES.value,
        view_answer=Answer.CANNOT_TELL.value,
    )

    result = score_trial(hidden_residual, "CANNOT TELL", 950)

    assert result["correct"] is False
    assert result["evidence_aligned"] is True
    assert result["false_safe"] is False


def test_authoritylens_yes_can_be_both_ground_truth_correct_and_view_aligned():
    exposed_residual = _trial(
        Answer.YES.value,
        Answer.YES.value,
        view_answer=Answer.YES.value,
    )

    result = score_trial(exposed_residual, "YES", 950)

    assert result["correct"] is True
    assert result["evidence_aligned"] is True


def test_score_trial_rejects_invalid_answers_and_invalid_timing():
    with pytest.raises(ValueError, match="response"):
        score_trial(_trial(Answer.NO.value, Answer.NO.value), "MAYBE", 200)
    with pytest.raises(ValueError, match="response_time_ms"):
        score_trial(_trial(Answer.NO.value, Answer.NO.value), "NO", -1)


def test_seeded_schedule_is_reproducible_and_counterbalances_session_condition():
    first = build_session_schedule(12)
    repeat = build_session_schedule(12)
    paired = build_session_schedule(13)
    first_private = _build_session_plan(12)
    paired_private = _build_session_plan(13)

    assert first == repeat
    assert len(first) == 9
    assert len({trial["task_id"] for trial in first_private}) == 9
    assert sum(trial["question_type"] == QuestionType.DIRECT_RETRIEVAL.value for trial in first_private) == 6
    assert sum(trial["question_type"] == QuestionType.TRANSFER_INFERENCE.value for trial in first_private) == 3
    assert {
        trial["matched_pair"]
        for trial in first_private
        if trial["question_type"] == QuestionType.TRANSFER_INFERENCE.value
    } == {
        "multihop_message_readability",
        "queued_send_sufficiency",
        "external_message_readability",
    }
    assert len({trial["condition"] for trial in first_private}) == 1
    assert first_private[0]["condition"] != paired_private[0]["condition"]
    assert [trial["task_id"] for trial in first_private] == [trial["task_id"] for trial in paired_private]
    first_assignment = {trial["task_id"]: trial["condition"] for trial in first_private}
    paired_assignment = {trial["task_id"]: trial["condition"] for trial in paired_private}
    assert all(paired_assignment[task_id] != condition for task_id, condition in first_assignment.items())
    assert {_build_session_plan(seed)[0]["condition"] for seed in range(4)} == {
        Condition.TARGET_LOCAL.value,
        Condition.CONSEQUENCE.value,
    }
    task_orders = {
        tuple(trial["task_id"] for trial in _build_session_plan(seed))
        for seed in range(0, 20, 2)
    }
    assert len(task_orders) >= 5


def test_transfer_trials_do_not_repeat_an_identical_direct_state():
    tasks = {task["task_id"]: task for task in load_task_bank()}
    direct_tasks = [
        task for task in tasks.values()
        if task["question_type"] == QuestionType.DIRECT_RETRIEVAL.value
    ]
    transfer_tasks = [
        task for task in tasks.values()
        if task["question_type"] == QuestionType.TRANSFER_INFERENCE.value
    ]

    for transfer in transfer_tasks:
        exact_state_matches = {
            task["task_id"] for task in direct_tasks
            if task["state"] == transfer["state"]
        }
        assert set(transfer.get("avoid_cooccurrence_with", [])) == exact_state_matches

    for seed in range(16):
        plan = _build_session_plan(seed)
        selected_ids = {trial["task_id"] for trial in plan}
        selected_transfer = [
            tasks[trial["task_id"]] for trial in plan
            if trial["question_type"] == QuestionType.TRANSFER_INFERENCE.value
        ]
        for transfer in selected_transfer:
            assert not selected_ids.intersection(
                transfer.get("avoid_cooccurrence_with", [])
            )


def test_direct_items_rotate_across_eight_variant_blocks():
    tasks = load_task_bank()
    direct_ids = {
        task["task_id"] for task in tasks
        if task["question_type"] == QuestionType.DIRECT_RETRIEVAL.value
    }
    exposures = {task_id: 0 for task_id in direct_ids}
    availability = {task_id: 0 for task_id in direct_ids}

    for pair_index in range(8):
        plan = _build_session_plan(pair_index * 2)
        transfer_tasks = [
            task for task in tasks
            if task["question_type"] == QuestionType.TRANSFER_INFERENCE.value
            and task["task_id"] in {trial["task_id"] for trial in plan}
        ]
        excluded = {
            task_id
            for transfer in transfer_tasks
            for task_id in transfer.get("avoid_cooccurrence_with", [])
        }
        for task_id in direct_ids:
            if task_id not in excluded:
                availability[task_id] += 1
        for trial in plan:
            if trial["question_type"] == QuestionType.DIRECT_RETRIEVAL.value:
                exposures[trial["task_id"]] += 1

    limited_ids = {
        task_id
        for task in tasks
        if task["question_type"] == QuestionType.TRANSFER_INFERENCE.value
        for task_id in task.get("avoid_cooccurrence_with", [])
    }
    assert all(exposures[task_id] == availability[task_id] for task_id in limited_ids)
    unpaired_exposure_counts = [
        exposures[task_id] for task_id in direct_ids - limited_ids
    ]
    assert max(unpaired_exposure_counts) - min(unpaired_exposure_counts) <= 1


def test_transfer_variant_assignment_is_balanced_across_eight_seed_pairs():
    counts = {pair_id: {} for pair_id in (
        "external_message_readability",
        "multihop_message_readability",
        "queued_send_sufficiency",
    )}

    for pair_index in range(8):
        selected = _build_session_plan(pair_index * 2)
        for trial in selected:
            if trial["question_type"] == QuestionType.TRANSFER_INFERENCE.value:
                variants = counts[trial["matched_pair"]]
                variants[trial["task_id"]] = variants.get(trial["task_id"], 0) + 1

    assert all(len(variants) == 2 and set(variants.values()) == {4} for variants in counts.values())


def test_task_catalog_has_private_condition_specific_evidence_answers():
    answers = {
        task["task_id"]: task["view_supported_answer_by_condition"]
        for task in load_task_bank()
    }

    assert answers["P02"] == {
        Condition.TARGET_LOCAL.value: Answer.CANNOT_TELL.value,
        Condition.CONSEQUENCE.value: Answer.YES.value,
    }
    assert answers["P03"] == {
        Condition.TARGET_LOCAL.value: Answer.CANNOT_TELL.value,
        Condition.CONSEQUENCE.value: Answer.YES.value,
    }
    assert all(set(value) == {condition.value for condition in Condition} for value in answers.values())

    schedule = build_session_schedule(12)
    assert all("view_supported_answer" not in trial for trial in schedule)
    assert all("view_supported_answer_by_condition" not in trial["stimulus"] for trial in schedule)


def test_task_bank_rejects_view_answer_key_that_disagrees_with_structured_view(tmp_path):
    catalog = json.loads(Path("PILOT_TASKS.json").read_text(encoding="utf-8"))
    p02 = next(task for task in catalog["tasks"] if task["task_id"] == "P02")
    p02["view_supported_answer_by_condition"][Condition.TARGET_LOCAL.value] = Answer.NO.value
    corrupted_catalog = tmp_path / "pilot_tasks_invalid.json"
    corrupted_catalog.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(ValueError, match="target_local view supports CANNOT TELL"):
        load_task_bank(corrupted_catalog)


def test_task_bank_answers_match_authorityengine_derived_truth():
    tasks = load_task_bank()

    assert len(tasks) == 16
    assert sum(task["question_type"] == QuestionType.DIRECT_RETRIEVAL.value for task in tasks) == 10
    assert sum(task["question_type"] == QuestionType.TRANSFER_INFERENCE.value for task in tasks) == 6
    assert {task["expected_answer"] for task in tasks} >= {"YES", "NO", "CANNOT TELL"}
    assert {
        answer: sum(task["expected_answer"] == answer for task in tasks)
        for answer in ("YES", "NO", "CANNOT TELL")
    } == {"YES": 8, "NO": 6, "CANNOT TELL": 2}
    assert {task["family"] for task in tasks} >= {
        "residual",
        "multi_hop_residual",
        "pending_effect",
        "no_pending_effect",
        "unknown_external",
        "confirmed_revoked_external",
        "complete_revocation",
        "mixed_residual_pending",
        "send_authority",
        "transfer_multihop_closed",
        "transfer_multihop_residual",
        "transfer_pending_closure_action",
        "transfer_cancelled_closure_action",
        "transfer_external_unknown",
        "transfer_external_revoked",
    }


def test_original_direct_retrieval_questions_are_preserved_verbatim():
    expected = {
        "P01": "After Agent A's Gmail read grant was revoked, can Agent A initiate a new Gmail read?",
        "P02": "After Agent A's Gmail read grant was revoked, can Agent B initiate a new Gmail read?",
        "P03": "After Agent A's Gmail send grant was revoked, could an email already queued by Agent A still be sent?",
        "P04": "After Agent A's Gmail read grant was revoked, can External Agent C initiate a new Gmail read?",
        "P05": "After Agent A's Gmail send grant was revoked, can any agent still initiate a new Gmail send?",
        "P06": "After Agent A's Gmail send grant was revoked, can Agent A still initiate a new Gmail read?",
        "P07": "After Agent A's Gmail read grant was revoked, can Agent C initiate a new Gmail read?",
        "P08": "Can External Agent C initiate a new Gmail read now?",
        "P09": "Could an email queued before Agent A's Gmail send grant was revoked still be sent?",
        "P10": "After Agent A's Gmail read grant was revoked, can Agent D initiate a new Gmail read?",
    }
    tasks = {task["task_id"]: task for task in load_task_bank()}

    assert {task_id: tasks[task_id]["question"]["text"] for task_id in expected} == expected
    assert all(tasks[task_id]["question_type"] == QuestionType.DIRECT_RETRIEVAL.value for task_id in expected)


def test_transfer_items_form_three_matched_state_pairs_and_derive_answers():
    tasks = {task["task_id"]: task for task in load_task_bank()}
    pairs = (("T01", "T02"), ("T03", "T04"), ("T05", "T06"))

    for left_id, right_id in pairs:
        left, right = tasks[left_id], tasks[right_id]
        assert left["question_type"] == QuestionType.TRANSFER_INFERENCE.value
        assert right["question_type"] == QuestionType.TRANSFER_INFERENCE.value
        assert left["question"]["text"] == right["question"]["text"]
        assert left["expected_answer"] == derive_ground_truth(left)["answer"]
        assert right["expected_answer"] == derive_ground_truth(right)["answer"]
        assert left["relevant_consequence_remains"] == derive_ground_truth(left)["relevant_consequence_remains"]
        assert right["relevant_consequence_remains"] == derive_ground_truth(right)["relevant_consequence_remains"]
        assert left["view_supported_answer_by_condition"][Condition.TARGET_LOCAL.value] == Answer.CANNOT_TELL.value
        assert right["view_supported_answer_by_condition"][Condition.TARGET_LOCAL.value] == Answer.CANNOT_TELL.value

    for task_id in ("T01", "T02", "T05", "T06"):
        assert tasks[task_id]["question"]["query_type"] == "guarantee_no_scope"
    assert (tasks["T01"]["expected_answer"], tasks["T02"]["expected_answer"]) == ("YES", "NO")
    assert (tasks["T03"]["expected_answer"], tasks["T04"]["expected_answer"]) == ("YES", "NO")
    assert (tasks["T05"]["expected_answer"], tasks["T06"]["expected_answer"]) == ("NO", "YES")
    assert tasks["T05"]["relevant_consequence_remains"] == "CANNOT TELL"
    t01_state = {key: value for key, value in tasks["T01"]["state"].items() if key != "revoked_delegations"}
    t02_state = {key: value for key, value in tasks["T02"]["state"].items() if key != "revoked_delegations"}
    assert t01_state == t02_state
    assert tasks["T01"]["state"]["revoked_delegations"] == ["d-a-b-read", "d-b-c-read"]
    assert tasks["T02"]["state"]["revoked_delegations"] == []
    assert tasks["T03"]["state"]["effects"][0]["status"] == "queued"
    assert tasks["T04"]["state"]["effects"][0]["status"] == "cancelled"
    assert tasks["T05"]["state"]["external_states"][0]["status"] == "unknown"
    assert tasks["T06"]["state"]["external_states"][0]["status"] == "confirmed_revoked"


def test_transfer_answer_claims_are_not_printed_verbatim_in_either_panel():
    tasks = {task["task_id"]: task for task in load_task_bank()}
    claims = {
        "T01": "The system can guarantee that no agent will read a new Gmail message.",
        "T02": "The system cannot guarantee that no agent will read a new Gmail message.",
        "T03": "Another control action is needed to ensure no email is sent from Gmail now.",
        "T04": "No other control action is needed to ensure no email is sent from Gmail now.",
        "T05": "There is enough confirmed state to guarantee no external agent can read a new Gmail message.",
        "T06": "There is not enough confirmed state to guarantee no external agent can read a new Gmail message.",
    }

    for task_id, claim in claims.items():
        task = tasks[task_id]
        shown = " ".join(
            json.dumps(build_stimulus(task, condition.value), ensure_ascii=False)
            for condition in Condition
        )
        assert claim not in shown


def test_transfer_false_safe_polarity_is_explicit_and_cannot_tell_is_excluded():
    tasks = {task["task_id"]: task for task in load_task_bank()}

    expected_false_safe = {
        "T01": [], "T02": ["YES"], "T03": ["NO"],
        "T04": [], "T05": ["YES"], "T06": [],
    }
    expected_false_alarm = {
        "T01": ["NO"], "T02": [], "T03": [],
        "T04": ["YES"], "T05": [], "T06": ["NO"],
    }
    assert {
        task_id: tasks[task_id]["false_safe_rule"]["false_safe_if"]
        for task_id in expected_false_safe
    } == expected_false_safe
    assert {
        task_id: tasks[task_id]["false_safe_rule"]["false_alarm_if"]
        for task_id in expected_false_alarm
    } == expected_false_alarm
    assert all(
        "CANNOT TELL" not in task["false_safe_rule"]["false_safe_if"]
        for task in tasks.values()
    )


def test_transfer_scoring_uses_engine_truth_and_task_level_polarity():
    task = next(task for task in load_task_bank() if task["task_id"] == "T03")
    transfer_trial = {
        "trial_index": 1,
        "task_id": task["task_id"],
        "scenario_id": task["scenario_id"],
        "condition": Condition.CONSEQUENCE.value,
        "question": task["question"]["text"],
        "question_type": task["question_type"],
        "ground_truth": derive_ground_truth(task),
        "view_supported_answer": task["view_supported_answer_by_condition"][Condition.CONSEQUENCE.value],
        "false_safe_rule": task["false_safe_rule"],
    }

    result = score_trial(transfer_trial, "NO", 1100)

    assert result["ground_truth"]["answer"] == "YES"
    assert result["ground_truth"]["relevant_consequence_remains"] == "YES"
    assert result["false_safe"] is True
    assert result["evidence_aligned"] is False
    assert result["question_type"] == "TRANSFER_INFERENCE"


def test_no_reader_guarantee_query_uses_engine_authority_and_unknown_state():
    tasks = {task["task_id"]: task for task in load_task_bank()}

    for task_id, query_id, expected in (
        ("T01", "guarantee_no_reader_closed", ("YES", "NO")),
        ("T02", "guarantee_no_reader_residual", ("NO", "YES")),
        ("T05", "guarantee_no_external_reader_unknown", ("NO", "CANNOT TELL")),
        ("T06", "guarantee_no_external_reader_revoked", ("YES", "NO")),
    ):
        task = json.loads(json.dumps(tasks[task_id]))
        task["question"]["id"] = query_id
        task["question"]["query_type"] = "guarantee_no_scope"
        task["question"]["scope"] = "gmail.read"
        if task_id in {"T05", "T06"}:
            task["question"]["principal_type"] = "external"
        derived = derive_ground_truth(task)
        assert (derived["answer"], derived["relevant_consequence_remains"]) == expected
        expected_authoritylens_answer = {
            "T01": "YES",
            "T02": "NO",
            "T05": "NO",
            "T06": "YES",
        }[task_id]
        assert derive_view_supported_answer(task, Condition.TARGET_LOCAL.value) == "CANNOT TELL"
        assert (
            derive_view_supported_answer(task, Condition.CONSEQUENCE.value)
            == expected_authoritylens_answer
        )

def test_both_trial_stimuli_share_engine_state_and_unknown_label_is_clean():
    task = next(task for task in load_task_bank() if task["task_id"] == "P04")
    baseline = build_stimulus(task, Condition.TARGET_LOCAL.value)
    consequence = build_stimulus(task, Condition.CONSEQUENCE.value)

    assert baseline["target"] == consequence["target_local_state"]["target"]
    assert baseline["status"] == "OFF"
    assert consequence["target_local_state"]["status"] == "STOPPED"
    assert consequence["target_local_state"]["text"] == (
        "Agent A no longer has Gmail access."
    )
    unknown_text = " ".join(consequence["sections"][0]["items"])
    assert "External Agent C" in unknown_text
    assert "External External Agent C" not in unknown_text
    assert "expected_answer" not in consequence


def test_comparison_views_are_rendered_from_one_effective_state():
    task = next(task for task in load_task_bank() if task["task_id"] == "T02")
    pair = build_stimulus_pair(task)

    assert pair["effective_state"].descendant_authority
    assert pair[Condition.TARGET_LOCAL.value]["status"] == "OFF"
    assert pair[Condition.CONSEQUENCE.value]["sections"]
    assert pair[Condition.TARGET_LOCAL.value] == build_stimulus(task, Condition.TARGET_LOCAL.value)
    assert pair[Condition.CONSEQUENCE.value] == build_stimulus(task, Condition.CONSEQUENCE.value)


def test_truth_derivation_uses_structured_query_not_question_prose():
    task = next(task for task in load_task_bank() if task["task_id"] == "T02")
    original = derive_ground_truth(task)
    task_with_reworded_prose = json.loads(json.dumps(task))
    task_with_reworded_prose["question"]["text"] = "Unrelated display wording; query fields are unchanged."

    assert derive_ground_truth(task_with_reworded_prose) == original


def test_consequence_stimulus_uses_same_local_fact_and_scope_label():
    task = next(task for task in load_task_bank() if task["task_id"] == "P03")
    baseline = build_stimulus(task, Condition.TARGET_LOCAL.value)
    consequence = build_stimulus(task, Condition.CONSEQUENCE.value)

    assert baseline["resource_label"] == "Gmail Sending"
    assert consequence["target_local_state"]["resource_label"] == "Gmail Sending"
    assert consequence["target_local_state"]["status"] == "STOPPED"
    assert consequence["target_local_state"]["text"] == (
        "Agent A can no longer send email through Gmail."
    )


def test_scheduled_trial_contains_only_the_assigned_view():
    schedule = build_session_schedule(4)

    titles = set()
    private_fields = {
        "expected_answer", "view_supported_answer", "view_supported_answer_by_condition",
        "ground_truth", "question_type", "query_type", "false_safe_rule",
        "false_alarm_rule", "task_id", "scenario_id", "condition", "state",
        "description", "matched_pair", "relevant_consequence_remains",
    }

    def nested_keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from nested_keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from nested_keys(child)

    for trial in schedule:
        titles.add(trial["stimulus"]["title"])
        assert private_fields.isdisjoint(nested_keys(trial))
    assert len(titles) == 1
    assert titles <= {"Conventional Permission View", "AuthorityLens"}


def test_catalog_stimuli_match_engine_derived_view_models_for_all_tasks():
    for task in load_task_bank():
        baseline = build_stimulus(task, Condition.TARGET_LOCAL.value)
        consequence = build_stimulus(task, Condition.CONSEQUENCE.value)
        declared = task["stimuli"]

        baseline_text = (
            f"{baseline['target']}\n{baseline['resource_label']}\n{baseline['status']}"
        )
        assert baseline_text == declared["target_local"]["target_local_text"]

        authority_declared = declared["authoritylens"]
        summary = authority_declared["consequence_view_summary"]
        rendered_sections = {
            section["title"]: section["items"]
            for section in consequence["sections"]
        }
        rendered_capabilities = (
            rendered_sections.get("Current capabilities", [])
            + rendered_sections.get("Remaining delegated access", [])
        )
        local = consequence["target_local_state"]
        local_text = f"{local['status']} — {local['text']}"

        # These assertions check that the static catalog mirrors the current
        # render model. Ground truth remains derived from EffectiveState above.
        assert consequence["headline"] == summary["headline"]
        assert local_text == authority_declared["target_local_text"]
        assert rendered_capabilities == summary["remaining_capabilities"]
        assert rendered_sections.get("Pending consequences", []) == summary["pending_consequences"]
        assert rendered_sections.get("Cannot verify", []) == summary["unknown_risks"]
        assert consequence.get("empty_state_message") == summary.get("empty_state_message")


def test_trial_records_contain_no_identity_or_device_fields():
    record = score_trial(_trial(Answer.NO.value, Answer.NO.value), "NO", 500)
    forbidden = {"name", "email", "ip_address", "location", "device_fingerprint"}

    assert forbidden.isdisjoint(record)
    assert "participant_code" not in record
    assert record["trial_index"] == 1


def test_metrics_keep_direct_and_transfer_accuracy_separate():
    records = [
        score_trial(_trial("YES", "YES", task_id="D1"), "NO", 100),
        score_trial(
            _trial(
                "NO", "YES", task_id="T1",
                question_type=QuestionType.TRANSFER_INFERENCE.value,
                false_safe_if=["YES"], false_alarm_if=[],
            ),
            "YES", 300,
        ),
        score_trial(
            _trial(
                "YES", "NO", task_id="T2",
                question_type=QuestionType.TRANSFER_INFERENCE.value,
                false_safe_if=[], false_alarm_if=["NO"],
            ),
            "NO", 500,
        ),
    ]

    metrics = calculate_metrics(records)[Condition.TARGET_LOCAL.value]

    assert metrics["by_question_type"]["DIRECT_RETRIEVAL"]["accuracy_count"] == 0
    assert metrics["by_question_type"]["DIRECT_RETRIEVAL"]["trials"] == 1
    assert metrics["by_question_type"]["TRANSFER_INFERENCE"]["accuracy_count"] == 0
    assert metrics["by_question_type"]["TRANSFER_INFERENCE"]["trials"] == 2
    assert metrics["false_safe_count"] == 2
    assert metrics["false_safe_denominator"] == 2
    assert metrics["false_alarm_count"] == 1
    assert metrics["false_alarm_denominator"] == 1
    assert metrics["by_question_type"]["TRANSFER_INFERENCE"]["false_safe_rate"] == 1


def test_metric_denominators_and_medians_use_the_defined_trial_sets():
    records = [
        score_trial(_trial("YES", "YES", "T1"), "NO", 100, confidence=4),
        score_trial(_trial("NO", "NO", "T2"), "YES", 300, confidence=2),
        score_trial(_trial("CANNOT TELL", "CANNOT TELL", "T3"), "CANNOT TELL", 200, confidence=3),
    ]
    records[0]["condition"] = Condition.TARGET_LOCAL.value
    records[1]["condition"] = Condition.TARGET_LOCAL.value
    records[2]["condition"] = Condition.TARGET_LOCAL.value

    metrics = calculate_metrics(records)

    assert metrics[Condition.TARGET_LOCAL.value]["by_question_type"]["DIRECT_RETRIEVAL"]["accuracy_count"] == 1
    assert metrics[Condition.TARGET_LOCAL.value]["by_question_type"]["DIRECT_RETRIEVAL"]["accuracy_rate"] == pytest.approx(1 / 3)
    assert metrics[Condition.TARGET_LOCAL.value]["false_safe_count"] == 1
    assert metrics[Condition.TARGET_LOCAL.value]["false_safe_denominator"] == 2
    assert metrics[Condition.TARGET_LOCAL.value]["false_safe_rate"] == pytest.approx(1 / 2)
    assert metrics[Condition.TARGET_LOCAL.value]["by_question_type"]["DIRECT_RETRIEVAL"]["evidence_aligned_rate"] == pytest.approx(1 / 3)
    assert metrics[Condition.TARGET_LOCAL.value]["false_alarm_count"] == 1
    assert metrics[Condition.TARGET_LOCAL.value]["false_alarm_denominator"] == 1
    assert metrics[Condition.TARGET_LOCAL.value]["by_question_type"]["DIRECT_RETRIEVAL"]["median_response_time_ms"] == 200
    assert metrics[Condition.CONSEQUENCE.value]["trials"] == 0
    assert metrics[Condition.CONSEQUENCE.value]["false_safe_rate"] is None
    assert metrics[Condition.CONSEQUENCE.value]["by_question_type"]["TRANSFER_INFERENCE"]["accuracy_rate"] is None


def test_dry_run_is_labeled_synthetic_and_writes_json_and_csv(tmp_path):
    data = simulate_dry_run(42)
    json_path, csv_path = write_dry_run_outputs(tmp_path, 42)
    saved = json.loads(json_path.read_text(encoding="utf-8"))

    assert data["dataset_label"] == "SYNTHETIC DRY RUN — NOT PARTICIPANT DATA"
    assert len(data["records"]) == 9
    assert len({record["condition"] for record in data["records"]}) == 1
    assert saved["dataset_label"] == "SYNTHETIC DRY RUN — NOT PARTICIPANT DATA"
    assert "SYNTHETIC_DRY_RUN" in json_path.name
    assert "SYNTHETIC_DRY_RUN" in csv_path.name
    rows = list(csv.DictReader(csv_path.open(encoding="utf-8", newline="")))
    assert rows
    assert {row["dataset_label"] for row in rows} == {
        "SYNTHETIC DRY RUN — NOT PARTICIPANT DATA"
    }
    assert all(row["response_time_ms"] for row in rows)


def test_no_real_participant_response_store_is_present():
    forbidden_paths = (
        Path("participant_data"),
        Path("participant_responses.csv"),
        Path("participant_responses.json"),
    )

    assert all(not path.exists() for path in forbidden_paths)
