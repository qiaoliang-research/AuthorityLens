from benchmark.analysis import build_analysis, classify_scenario_family, format_analysis_markdown
from benchmark.evaluator import evaluate_benchmark, report_to_dict


def test_scenario_ids_map_to_the_declared_synthetic_families():
    assert classify_scenario_family("S001_complete_revocation") == "canonical"
    assert classify_scenario_family("S019_link1_revoked_depth2_send") == "link_revoked"
    assert classify_scenario_family("S040_external_middle_unknown_read") == "external_middle"


def test_analysis_uses_only_eligible_rows_for_coverage_and_retains_all_counts():
    analysis = build_analysis(report_to_dict(evaluate_benchmark()))

    assert analysis["scenario_count"] == 40
    assert analysis["eligible_scenario_count"] == 32
    assert analysis["ineligible_before_action_count"] == 8
    assert sum(item["scenario_count"] for item in analysis["scenario_families"].values()) == 40
    assert sum(item["eligible_count"] for item in analysis["scenario_families"].values()) == 32
    assert analysis["scenario_families"]["direct_active"]["baseline_micro_coverage"] is None
    assert analysis["scenario_families"]["canonical"]["baseline_micro_coverage"] == 0.5
    assert analysis["scenario_families"]["canonical"]["authoritylens_micro_coverage"] == 1.0
    assert analysis["critical_omissions_by_type"] == {
        "residual_capability": {"total": 39, "baseline_omitted": 39, "authoritylens_omitted": 0},
        "pending_effect": {"total": 4, "baseline_omitted": 4, "authoritylens_omitted": 0},
        "unknown_authority": {"total": 6, "baseline_omitted": 6, "authoritylens_omitted": 0},
    }
    assert analysis["mix"]["scope"] == {"gmail.read": 20, "gmail.send": 20}
    assert analysis["mix"]["delegation_depth"] == {"0": 4, "1": 11, "2": 16, "3": 9}
    markdown = format_analysis_markdown(analysis)
    assert "34.8%" in markdown
    assert "100.0%" in markdown
    assert "32/92" in markdown
    assert "does not establish human comprehension" in markdown
    assert "Coverage and CCOR do not penalize unsupported or contradictory facts represented by a view model" in markdown
    assert "both the shared always-visible authority-chain diagram and expandable system-state panel are outside the scored comparison" in markdown
    assert "one root grant and a linear delegation chain" in markdown
