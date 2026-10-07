from dataclasses import replace
from inspect import signature
import csv
import json

from benchmark.evaluator import (
    AuthorityLensPresentedFacts,
    BaselinePresentedFacts,
    CATEGORY_FACT_TYPES,
    CCOR,
    MacroCoverage,
    _in_category,
    calculate_coverage,
    calculate_ccor,
    calculate_macro_coverage,
    _engine_for_scenario,
    evaluate_benchmark,
    evaluate_scenario,
    extract_authoritylens_facts,
    format_report,
    report_to_dict,
    write_csv,
    write_markdown_report,
    write_results,
)
from benchmark.ground_truth import Fact, FactType, derive_ground_truth_facts
from benchmark.scenarios import CANONICAL_SCENARIO_IDS, build_scenarios
from authority_lens import EffectiveState, ExternalState, ExternalStatus
from control_view import ControlContext
from app import build_scenario_payload


def scenario_map():
    return {scenario.scenario_id: scenario for scenario in build_scenarios()}


def test_benchmark_builds_40_unique_scenarios_including_the_canonical_four():
    scenarios = build_scenarios()
    ids = [scenario.scenario_id for scenario in scenarios]
    signatures = [
        (
            tuple((item.id, str(item.type), item.parent_id) for item in scenario.principals),
            tuple((item.principal_id, item.scope, item.source_principal_id, item.id not in scenario.revoke_grant_ids) for item in scenario.grants),
            tuple((item.from_id, item.to_id, item.scope, item.id not in scenario.revoke_delegation_ids) for item in scenario.delegations),
            tuple((item.principal_id, str(item.status)) for item in scenario.external_states),
            tuple((item.principal_id, item.action, str(item.status), item.required_scope) for item in scenario.pending_effects),
            scenario.target_principal,
            scenario.requested_action,
            scenario.resource,
        )
        for scenario in scenarios
    ]

    assert len(scenarios) == 40
    assert len(set(ids)) == 40
    assert len(set(signatures)) == 40
    assert set(CANONICAL_SCENARIO_IDS) <= set(ids)


def test_complete_revocation_exposes_local_off_and_system_completion_appropriately():
    result = evaluate_scenario(scenario_map()["S001_complete_revocation"])

    assert Fact(FactType.TARGET_PERMISSION, "agent-a", "gmail", status="off") in result.baseline_exposed_facts
    assert Fact(FactType.COMPLETE_REVOCATION, resource="gmail") in result.authoritylens_exposed_facts


def test_residual_authority_is_hidden_from_baseline_but_exposed_by_authoritylens():
    result = evaluate_scenario(scenario_map()["S002_single_residual_delegate"])
    residual = next(
        fact for fact in result.ground_truth_facts
        if fact.fact_type == FactType.RESIDUAL_CAPABILITY and fact.principal_id == "agent-b"
    )

    assert residual not in result.baseline_exposed_facts
    assert residual in result.authoritylens_exposed_facts


def test_queued_effect_is_hidden_from_baseline_but_exposed_by_authoritylens():
    result = evaluate_scenario(scenario_map()["S003_queued_action"])
    pending = next(fact for fact in result.ground_truth_facts if fact.fact_type == FactType.PENDING_EFFECT)

    assert pending not in result.baseline_exposed_facts
    assert pending in result.authoritylens_exposed_facts


def test_unknown_external_authority_is_hidden_from_baseline_but_exposed_by_authoritylens():
    result = evaluate_scenario(scenario_map()["S004_unknown_external_agent"])
    unknown = next(fact for fact in result.ground_truth_facts if fact.fact_type == FactType.UNKNOWN_AUTHORITY)

    assert unknown not in result.baseline_exposed_facts
    assert unknown in result.authoritylens_exposed_facts


def test_multihop_residual_ground_truth_preserves_descendant_path_and_status():
    scenario = next(
        item for item in build_scenarios()
        if item.scenario_id == "S016_root_revoked_depth3_read"
    )
    result = evaluate_scenario(scenario)
    descendant = next(
        fact for fact in result.ground_truth_facts
        if fact.fact_type == FactType.RESIDUAL_CAPABILITY and fact.principal_id == "agent-d"
    )

    assert descendant.principal_path == ("human", "agent-a", "agent-b", "agent-c", "agent-d")
    assert descendant.delegation_path == (
        "d-agent-a-agent-b-gmail.read",
        "d-agent-b-agent-c-gmail.read",
        "d-agent-c-agent-d-gmail.read",
    )
    assert descendant.path_status == "residual"


def test_coverage_calculation_is_exact_and_empty_denominator_is_not_a_score():
    first = Fact(FactType.COMPLETE_REVOCATION, resource="gmail")
    second = Fact(FactType.PENDING_EFFECT, principal_id="agent-a", resource="gmail", effect_id="e1")

    assert calculate_coverage([first, second], [first]).rate == 0.5
    assert calculate_coverage([], [first]).rate is None


def test_extraction_uses_structured_fields_and_ignores_display_text():
    scenario = scenario_map()["S002_single_residual_delegate"]
    result = evaluate_scenario(scenario)
    original = result.authoritylens_view
    changed_text = replace(
        original,
        headline="arbitrary replacement headline",
        residual_items=tuple(replace(item, description="unrelated arbitrary text") for item in original.residual_items),
    )

    assert extract_authoritylens_facts(changed_text, result.baseline_view) == result.authoritylens_exposed_facts


def test_full_benchmark_metrics_are_deterministic():
    first = evaluate_benchmark()
    second = evaluate_benchmark()

    assert first.overall_baseline_coverage == second.overall_baseline_coverage
    assert first.overall_authoritylens_coverage == second.overall_authoritylens_coverage
    assert first.category_coverage == second.category_coverage
    assert len(first.scenario_results) == 40


def test_active_authority_category_does_not_double_count_target_permission():
    before_action = evaluate_benchmark([scenario_map()["S005_direct_active_read"]])
    baseline, authoritylens = before_action.category_coverage["active_authority"]
    assert baseline.total == authoritylens.total == 0
    assert baseline.rate is authoritylens.rate is None

    after_action_scenario = next(
        item for item in build_scenarios() if item.revoke_delegation_ids
    )
    report = evaluate_benchmark([after_action_scenario])
    baseline, authoritylens = report.category_coverage["active_authority"]

    assert (baseline.covered, baseline.total) == (0, 1)
    assert (authoritylens.covered, authoritylens.total) == (1, 1)


def test_ground_truth_api_does_not_accept_a_control_view():
    assert tuple(signature(derive_ground_truth_facts).parameters) == ("state", "context")


def test_complete_revocation_is_derived_directly_from_state_and_confirmed_context():
    state = EffectiveState()
    confirmed = ControlContext("Gmail", "revoke", "agent-a", action_confirmed=True)
    unconfirmed = replace(confirmed, action_confirmed=False)
    unrelated_action = replace(confirmed, requested_action="delegate")

    complete = Fact(FactType.COMPLETE_REVOCATION, resource="gmail")
    assert complete in derive_ground_truth_facts(state, confirmed)
    assert complete not in derive_ground_truth_facts(state, unconfirmed)
    assert complete not in derive_ground_truth_facts(state, unrelated_action)

    for scenario_id in (
        "S002_single_residual_delegate",
        "S003_queued_action",
        "S004_unknown_external_agent",
    ):
        result = evaluate_scenario(scenario_map()[scenario_id])
        assert complete not in result.ground_truth_facts

    active_scenario = scenario_map()["S005_direct_active_read"]
    active_state = _engine_for_scenario(active_scenario).calculate()
    assert complete not in derive_ground_truth_facts(active_state, confirmed)


def test_authoritylens_exposed_facts_include_the_displayed_target_local_state():
    result = evaluate_scenario(scenario_map()["S002_single_residual_delegate"])
    local_off = Fact(FactType.TARGET_PERMISSION, "agent-a", "gmail", status="off")

    assert result.baseline_view.access_status == "OFF"
    assert isinstance(result.baseline_presented, BaselinePresentedFacts)
    assert isinstance(result.authoritylens_presented, AuthorityLensPresentedFacts)
    assert local_off in result.baseline_exposed_facts
    assert local_off in result.authoritylens_exposed_facts


def test_fact_categories_do_not_overlap_target_permission_and_active_authority():
    target_on = Fact(FactType.TARGET_PERMISSION, "agent-a", "gmail", status="on")
    assert _in_category(target_on, "target_permission")
    assert not _in_category(target_on, "active_authority")
    assert set(CATEGORY_FACT_TYPES) == {
        "active_authority",
        "residual_authority",
        "pending_effect",
        "unknown_authority",
        "complete_revocation",
        "target_permission",
    }
    categories = tuple(CATEGORY_FACT_TYPES.values())
    assert set.union(*categories) == set(FactType)
    assert all(
        not categories[left] & categories[right]
        for left in range(len(categories))
        for right in range(left + 1, len(categories))
    )
    report = evaluate_benchmark()
    assert sum(pair[0].total for pair in report.category_coverage.values()) == report.overall_baseline_coverage.total
    assert sum(pair[1].total for pair in report.category_coverage.values()) == report.overall_authoritylens_coverage.total


def test_intermediate_delegation_revocation_targets_the_recipient_local_view():
    revoked_link_scenarios = [
        item for item in build_scenarios() if item.revoke_delegation_ids
    ]
    assert revoked_link_scenarios
    for scenario in revoked_link_scenarios:
        revoked = next(
            item for item in scenario.delegations
            if item.id in scenario.revoke_delegation_ids
        )
        assert scenario.target_principal == revoked.to_id


def test_ccor_uses_critical_fact_omissions_and_reports_zero_denominator_as_na():
    facts = [
        Fact(FactType.RESIDUAL_CAPABILITY, "agent-b", "gmail", scope="gmail.read"),
        Fact(FactType.PENDING_EFFECT, "agent-a", "gmail", effect_id="e1"),
        Fact(FactType.UNKNOWN_AUTHORITY, "external-c", "gmail"),
        Fact(FactType.ACTIVE_CAPABILITY, "agent-a", "gmail", scope="gmail.read"),
    ]
    result = calculate_ccor(facts, [facts[0], facts[2]])
    assert result == CCOR(omitted=1, total=3, rate=1 / 3)
    assert calculate_ccor([facts[3]], []).rate is None


def test_scenario_macro_coverage_averages_nonempty_scenario_rates():
    values = [
        calculate_coverage([Fact(FactType.TARGET_PERMISSION)], [Fact(FactType.TARGET_PERMISSION)]),
        calculate_coverage([Fact(FactType.TARGET_PERMISSION), Fact(FactType.ACTIVE_CAPABILITY)], []),
        calculate_coverage([], []),
    ]
    assert calculate_macro_coverage(values) == MacroCoverage(scenarios=2, rate=0.5)
    assert calculate_macro_coverage([calculate_coverage([], [])]) == MacroCoverage(0, None)


def test_external_target_unknown_state_sets_target_permission_unknown_without_entry():
    state = EffectiveState(unknown_states=[ExternalState("external-c", ExternalStatus.UNKNOWN)])
    context = ControlContext("Gmail", "revoke", "external-c", action_confirmed=True)

    target_unknown = Fact(FactType.TARGET_PERMISSION, "external-c", "gmail", status="unknown")
    assert target_unknown in derive_ground_truth_facts(state, context)


def test_lens_target_local_fact_matches_browser_local_state_for_residual_case():
    result = evaluate_scenario(scenario_map()["S002_single_residual_delegate"])
    payload = build_scenario_payload(
        "residual-delegation",
        ["delegate-read-agent-b", "revoke-agent-a"],
    )
    assert payload["baseline"]["access_status"] == "OFF"
    assert payload["authority_lens"]["local_state"]["status"] == "STOPPED"
    assert result.authoritylens_presented.target_permission.status == "off"
    assert result.authoritylens_presented.target_permission in result.authoritylens_exposed_facts


def test_full_benchmark_metrics_and_artifacts_are_deterministic(tmp_path):
    first = evaluate_benchmark()
    second = evaluate_benchmark()
    assert report_to_dict(first) == report_to_dict(second)
    assert format_report(first) == format_report(second)
    data = report_to_dict(first)
    assert data["overall_ground_truth_coverage"]["baseline"]["micro"]["total"] > 0
    assert data["overall_ground_truth_coverage"]["baseline"]["macro"]["included_scenario_count"] == 32
    assert data["overall_ground_truth_coverage"]["baseline"]["macro"]["scenario_population"] == 32
    assert "critical_consequence_omission_rate" in data

    first_json, second_json = tmp_path / "first.json", tmp_path / "second.json"
    first_csv, second_csv = tmp_path / "first.csv", tmp_path / "second.csv"
    first_md, second_md = tmp_path / "first.md", tmp_path / "second.md"
    write_results(first, first_json)
    write_results(second, second_json)
    write_csv(first, first_csv)
    write_csv(second, second_csv)
    write_markdown_report(first, first_md)
    write_markdown_report(second, second_md)
    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_csv.read_bytes() == second_csv.read_bytes()
    assert first_md.read_bytes() == second_md.read_bytes()
    assert json.loads(first_json.read_text(encoding="utf-8"))["scenario_count"] == 40
    with first_csv.open(encoding="utf-8", newline="") as stream:
        csv_rows = list(csv.DictReader(stream))
    assert len(csv_rows) == 40
    ineligible = next(row for row in csv_rows if row["comparison_status"] == "INELIGIBLE_BEFORE_ACTION")
    assert ineligible["baseline_exposed_facts"] == "[]"
    assert ineligible["baseline_coverage_total"] == "0"
    assert ineligible["baseline_coverage_rate"] == "N/A"


def test_empty_benchmark_reports_zero_denominators_as_na():
    report = evaluate_benchmark([])
    payload = report_to_dict(report)
    assert payload["overall_ground_truth_coverage"]["baseline"]["micro"]["rate"] is None
    assert payload["overall_ground_truth_coverage"]["baseline"]["macro"]["rate"] is None
    assert payload["critical_consequence_omission_rate"]["baseline"]["rate"] is None
    assert "N/A" in format_report(report)


def test_reports_explain_structural_fact_path_matching_limitation():
    report = evaluate_benchmark()
    explanation = (
        "Coverage is structured view-model data-path matching, not rendered-information coverage: the AuthorityLens extractor reads nested provenance fields, including source-grant IDs and delegation paths, that are not all printed in default comparison cards. "
        "The always-visible authority-chain diagram displays some path/status context, but it and the expandable system-state panel are outside the scored pair of panels."
    )
    assert explanation in report_to_dict(report)["scientific_limitations"]
    assert explanation in format_report(report)


def test_reports_scope_coverage_to_comparison_panels_and_name_unmeasured_errors():
    report = evaluate_benchmark()
    limitations = report_to_dict(report)["scientific_limitations"]
    expected = (
        "Coverage and CCOR do not penalize unsupported or contradictory facts represented by a view model; precision and false-positive claim rates are not measured.",
        "Coverage compares the structured BaselineControlView and AuthorityLensControlView data paths only; both the shared always-visible authority-chain diagram and expandable system-state panel are outside the scored comparison.",
        "The 40 synthetic scenarios use one root grant and a linear delegation chain; scopes do not mix within a scenario, and queued-effect cases contain one effect.",
    )

    for statement in expected:
        assert statement in limitations
        assert statement in format_report(report)


def test_pre_action_cases_are_retained_but_ineligible_for_comparison_scoring():
    report = evaluate_benchmark()
    assert len(report.scenario_results) == 40
    assert report.eligible_scenario_count == 32
    pre_action = [item for item in report.scenario_results if not item.comparison_eligible]
    after_action = [item for item in report.scenario_results if item.comparison_eligible]

    assert len(pre_action) == 8
    assert len(after_action) == 32
    assert all(item.control_phase == "BEFORE_ACTION" for item in pre_action)
    assert all(item.control_phase == "AFTER_ACTION" for item in after_action)
    for item in pre_action:
        assert item.ground_truth_facts
        assert item.baseline_exposed_facts == ()
        assert item.authoritylens_exposed_facts == ()
        assert item.baseline_presented is None
        assert item.authoritylens_presented is None
        assert item.baseline_coverage.covered == item.baseline_coverage.total == 0
        assert item.authoritylens_coverage.covered == item.authoritylens_coverage.total == 0
        assert item.baseline_coverage.rate is None
        assert item.authoritylens_coverage.rate is None
        assert item.hidden_critical_facts_baseline == ()
        assert item.hidden_critical_facts_authoritylens == ()


def test_aggregate_metrics_use_only_eligible_after_action_scenarios():
    report = evaluate_benchmark()
    eligible = [item for item in report.scenario_results if item.comparison_eligible]
    assert report.overall_baseline_coverage.total == sum(len(item.ground_truth_facts) for item in eligible)
    assert report.overall_authoritylens_coverage.total == sum(len(item.ground_truth_facts) for item in eligible)
    assert report.ccor_baseline.total == sum(
        sum(fact.fact_type in {
            FactType.RESIDUAL_CAPABILITY,
            FactType.PENDING_EFFECT,
            FactType.UNKNOWN_AUTHORITY,
        } for fact in item.ground_truth_facts)
        for item in eligible
    )
    payload = report_to_dict(report)
    assert payload["scenario_count"] == 40
    assert payload["executed_scenario_count"] == 40
    assert payload["comparison_eligible_scenario_count"] == 32
    assert payload["overall_ground_truth_coverage"]["baseline"]["macro"]["scenario_population"] == 32
    assert payload["scenario_results"][0]["comparison_eligible"] is True
    pre_action_row = next(row for row in payload["scenario_results"] if not row["comparison_eligible"])
    assert pre_action_row["control_phase"] == "BEFORE_ACTION"
    assert pre_action_row["comparison_status"] == "INELIGIBLE_BEFORE_ACTION"
    assert pre_action_row["baseline_exposed_facts"] == []
    assert pre_action_row["authoritylens_exposed_facts"] == []
    assert pre_action_row["baseline_coverage"] == {"covered": 0, "total": 0, "rate": None}
