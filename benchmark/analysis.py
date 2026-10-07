"""Pure summaries for the synthetic benchmark's reproducible analysis outputs."""

from collections import Counter
import re


FAMILY_LABELS = {
    "canonical": "Canonical scenarios",
    "direct_active": "Direct active authority",
    "clean_chain": "Clean delegation chains",
    "root_revoked": "Root grant revoked",
    "link_revoked": "Intermediate delegation revoked",
    "queued_send": "Queued send with revocation",
    "external_leaf": "External principal at chain leaf",
    "external_middle": "External principal in chain middle",
}

CANONICAL_IDS = {
    "S001_complete_revocation",
    "S002_single_residual_delegate",
    "S003_queued_action",
    "S004_unknown_external_agent",
}


def classify_scenario_family(scenario_id: str) -> str:
    """Map generated stable ID patterns to the benchmark's declared families."""
    if scenario_id in CANONICAL_IDS:
        return "canonical"
    if "_direct_active_" in scenario_id:
        return "direct_active"
    if "_clean_chain_" in scenario_id:
        return "clean_chain"
    if "_root_revoked_" in scenario_id:
        return "root_revoked"
    if re.search(r"_link\d+_revoked_", scenario_id):
        return "link_revoked"
    if "_queued_send_residual_" in scenario_id:
        return "queued_send"
    if "_external_leaf_" in scenario_id:
        return "external_leaf"
    if "_external_middle_" in scenario_id:
        return "external_middle"
    raise ValueError(f"Unrecognized benchmark scenario ID: {scenario_id}")


def _pooled_coverage(rows: list[dict], view: str) -> dict:
    eligible = [row for row in rows if row["comparison_eligible"]]
    covered = sum(row[f"{view}_coverage"]["covered"] for row in eligible)
    total = sum(row[f"{view}_coverage"]["total"] for row in eligible)
    return {
        "covered": covered,
        "total": total,
        "rate": covered / total if total else None,
    }


def _coverage_rows(rows: list[dict]) -> dict:
    return {
        "scenario_count": len(rows),
        "eligible_count": sum(row["comparison_eligible"] for row in rows),
        "baseline_micro_coverage": _pooled_coverage(rows, "baseline")["rate"],
        "authoritylens_micro_coverage": _pooled_coverage(rows, "authoritylens")["rate"],
        "baseline_covered_facts": _pooled_coverage(rows, "baseline")["covered"],
        "baseline_total_facts": _pooled_coverage(rows, "baseline")["total"],
        "authoritylens_covered_facts": _pooled_coverage(rows, "authoritylens")["covered"],
        "authoritylens_total_facts": _pooled_coverage(rows, "authoritylens")["total"],
    }


def _mix(rows: list[dict]) -> dict[str, dict[str, int]]:
    dimensions = {
        "scope": Counter(),
        "delegation_depth": Counter(),
        "revocation_type": Counter(),
        "pending_effects": Counter(),
        "external_state": Counter(),
        "control_phase": Counter(),
    }
    for row in rows:
        scopes = [item["scope"] for item in row["grants"]]
        if not scopes:
            scopes = [item["scope"] for item in row["delegations"]]
        for scope in set(scopes):
            dimensions["scope"][scope] += 1

        dimensions["delegation_depth"][str(len(row["delegations"]))] += 1
        if row["revoke_grant_ids"]:
            revoke_type = "root_grant"
        elif row["revoke_delegation_ids"]:
            revoke_type = "delegation_link"
        else:
            revoke_type = "none"
        dimensions["revocation_type"][revoke_type] += 1
        dimensions["pending_effects"]["one_or_more" if row["pending_effects"] else "none"] += 1
        states = sorted({item["status"] for item in row["external_states"]})
        if not states:
            dimensions["external_state"]["none"] += 1
        else:
            for status in states:
                dimensions["external_state"][status] += 1
        dimensions["control_phase"][row["control_phase"]] += 1
    return {name: dict(sorted(values.items())) for name, values in dimensions.items()}


def _critical_omissions(rows: list[dict]) -> dict[str, dict[str, int]]:
    critical_types = ("residual_capability", "pending_effect", "unknown_authority")
    result = {name: {"total": 0, "baseline_omitted": 0, "authoritylens_omitted": 0} for name in critical_types}
    for row in rows:
        if not row["comparison_eligible"]:
            continue
        for fact in row["ground_truth_facts"]:
            fact_type = fact["type"]
            if fact_type not in result:
                continue
            result[fact_type]["total"] += 1
        for view, key in (
            ("baseline", "baseline_omitted"),
            ("authoritylens", "authoritylens_omitted"),
        ):
            for fact in row[f"hidden_critical_facts_{view}"]:
                result[fact["type"]][key] += 1
    return result


def build_analysis(payload: dict) -> dict:
    """Summarize benchmark JSON without recalculating or changing its facts."""
    rows = payload["scenario_results"]
    if len(rows) != payload["executed_scenario_count"] or len(rows) != payload["scenario_count"]:
        raise ValueError("Benchmark scenario count does not match its scenario rows")
    eligible_count = sum(row["comparison_eligible"] for row in rows)
    if eligible_count != payload["comparison_eligible_scenario_count"]:
        raise ValueError("Eligible scenario count does not match its scenario rows")
    if len(rows) - eligible_count != payload["comparison_ineligible_before_action_scenario_count"]:
        raise ValueError("Before-action scenario count does not match its scenario rows")

    families = {name: [] for name in FAMILY_LABELS}
    for row in rows:
        families[classify_scenario_family(row["scenario_id"])].append(row)

    scenario_families = {
        name: _coverage_rows(family_rows)
        for name, family_rows in families.items()
    }
    canonical_rows = [row for row in rows if row["scenario_id"] in CANONICAL_IDS]
    canonical = {
        row["scenario_id"]: {
            "baseline_coverage": row["baseline_coverage"],
            "authoritylens_coverage": row["authoritylens_coverage"],
            "hidden_critical_facts_baseline": len(row["hidden_critical_facts_baseline"]),
            "hidden_critical_facts_authoritylens": len(row["hidden_critical_facts_authoritylens"]),
        }
        for row in canonical_rows
    }
    return {
        "scenario_count": len(rows),
        "eligible_scenario_count": eligible_count,
        "ineligible_before_action_count": len(rows) - eligible_count,
        "overall_coverage": {
            "baseline": _pooled_coverage(rows, "baseline"),
            "authoritylens": _pooled_coverage(rows, "authoritylens"),
            "baseline_macro": payload["overall_ground_truth_coverage"]["baseline"]["macro"],
            "authoritylens_macro": payload["overall_ground_truth_coverage"]["authoritylens"]["macro"],
        },
        "category_coverage": payload["category_coverage"],
        "critical_consequence_omission_rate": payload["critical_consequence_omission_rate"],
        "critical_omissions_by_type": _critical_omissions(rows),
        "hidden_critical_facts": payload["hidden_critical_facts"],
        "scenario_families": scenario_families,
        "family_labels": FAMILY_LABELS.copy(),
        "mix": _mix(rows),
        "canonical": canonical,
        "scientific_limitations": payload["scientific_limitations"],
    }


def _rate(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def format_analysis_markdown(analysis: dict) -> str:
    lines = [
        "# AuthorityLens Benchmark Analysis",
        "",
        "Generated from `benchmark_results.json`; this report does not alter the benchmark's ground truth or scores.",
        "",
        f"Scenarios executed: **{analysis['scenario_count']}**  ",
        f"Comparison-eligible AFTER_ACTION: **{analysis['eligible_scenario_count']}**  ",
        f"BEFORE_ACTION, not scored: **{analysis['ineligible_before_action_count']}**",
        "",
        "Only confirmed-revoke AFTER_ACTION cases enter view comparisons. Before-action rows have no displayed comparison views and use N/A coverage.",
        "",
        "The metric compares structured view-model data paths, not rendered card text or the full browser page. The AuthorityLens extractor reads nested provenance fields (including IDs and paths) not all printed in the cards; the shared authority-chain diagram and expandable system-state panel are outside the scored pair.",
        "",
        "## Structured view-model coverage (GTC)",
        "",
        "| View | Micro view-model GTC | Macro view-model GTC | Covered / relevant facts |",
        "|---|---:|---:|---:|",
    ]
    coverage = analysis["overall_coverage"]
    for view, label in (("baseline", "Conventional target-local"), ("authoritylens", "AuthorityLens")):
        item = coverage[view]
        macro = coverage[f"{view}_macro"]
        lines.append(
            f"| {label} | {_rate(item['rate'])} | {_rate(macro['rate'])} | "
            f"{item['covered']}/{item['total']} |"
        )

    lines.extend([
        "",
        "## Category coverage",
        "",
        "Micro coverage by disjoint fact category; N/A denotes a zero denominator.",
        "",
        "| Category | Baseline | AuthorityLens | Facts |",
        "|---|---:|---:|---:|",
    ])
    category_labels = {
        "active_authority": "Active authority",
        "residual_authority": "Residual authority",
        "pending_effect": "Pending effects",
        "unknown_authority": "Unknown authority",
        "complete_revocation": "Complete revocation",
        "target_permission": "Target-local permission",
    }
    for name, values in analysis["category_coverage"].items():
        baseline, lens = values["baseline"], values["authoritylens"]
        lines.append(
            f"| {category_labels[name]} | {_rate(baseline['micro']['rate'])} | "
            f"{_rate(lens['micro']['rate'])} | {lens['micro']['covered']}/{lens['micro']['total']} |"
        )

    ccor = analysis["critical_consequence_omission_rate"]
    lines.extend([
        "",
        "## Critical consequence omissions from structured view models",
        "",
        "CCOR includes residual authority, pending effects, and unknown authority only; these are structured view-model facts, not an audit of visible text.",
        "",
        "| View | Omitted / critical facts | CCOR | Hidden critical facts |",
        "|---|---:|---:|---:|",
    ])
    for view, label in (("baseline", "Conventional target-local"), ("authoritylens", "AuthorityLens")):
        item = ccor[view]
        lines.append(
            f"| {label} | {item['omitted']}/{item['total']} | {_rate(item['rate'])} | "
            f"{analysis['hidden_critical_facts'][view]} |"
        )
    lines.extend([
        "",
        "| Critical fact type | Ground truth facts | Baseline omitted | AuthorityLens omitted |",
        "|---|---:|---:|---:|",
    ])
    for fact_type, item in analysis["critical_omissions_by_type"].items():
        lines.append(
            f"| {fact_type} | {item['total']} | {item['baseline_omitted']} | "
            f"{item['authoritylens_omitted']} |"
        )

    lines.extend([
        "",
        "## Scenario families",
        "",
        "Families are assigned deterministically from the stable scenario ID patterns. Coverage uses only eligible rows in each family.",
        "",
        "| Family | Scenarios | Eligible | Baseline micro GTC | AuthorityLens micro GTC |",
        "|---|---:|---:|---:|---:|",
    ])
    for name, stats in analysis["scenario_families"].items():
        lines.append(
            f"| {analysis['family_labels'][name]} | {stats['scenario_count']} | {stats['eligible_count']} | "
            f"{_rate(stats['baseline_micro_coverage'])} | {_rate(stats['authoritylens_micro_coverage'])} |"
        )

    lines.extend(["", "## Scenario mix", ""])
    mix_labels = {
        "scope": "Scope",
        "delegation_depth": "Delegation depth (links)",
        "revocation_type": "Revocation type",
        "pending_effects": "Pending effects",
        "external_state": "External state",
        "control_phase": "Control phase",
    }
    for dimension, counts in analysis["mix"].items():
        lines.extend([f"### {mix_labels[dimension]}", "", "| Value | Scenarios |", "|---|---:|"])
        lines.extend(f"| {value} | {count} |" for value, count in counts.items())
        lines.append("")

    lines.extend([
        "## Canonical scenarios",
        "",
        "| Scenario ID | Baseline GTC | AuthorityLens GTC | Hidden critical facts (Baseline / AuthorityLens) |",
        "|---|---:|---:|---:|",
    ])
    for scenario_id, item in analysis["canonical"].items():
        base = item["baseline_coverage"]
        lens = item["authoritylens_coverage"]
        lines.append(
            f"| {scenario_id} | {_rate(base['rate'])} ({base['covered']}/{base['total']}) | "
            f"{_rate(lens['rate'])} ({lens['covered']}/{lens['total']}) | "
            f"{item['hidden_critical_facts_baseline']} / {item['hidden_critical_facts_authoritylens']} |"
        )

    lines.extend([
        "",
        "## Interpretation limit",
        "",
        "This analysis measures factual information coverage only. It does not establish human comprehension, lower cognitive load, usability, preference, or improved real-world safety.",
        "",
        "AuthorityLens fact extraction reads typed view-model fields and nested EffectiveState provenance; it does not inspect DOM, screenshots, or rendered descriptions. Exact source/delegation identifiers and full paths counted by the extractor are not all printed in the default cards. The visible authority-chain diagram communicates some path and status information but is outside the scored panels.",
        "",
        "## Additional metric and scenario limits",
        "",
    ])
    lines.extend(
        f"- {limitation}"
        for limitation in analysis["scientific_limitations"]
        if limitation.startswith(("Coverage and CCOR", "Coverage compares", "The 40 synthetic scenarios"))
    )
    return "\n".join(lines) + "\n"
