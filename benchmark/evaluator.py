"""Deterministic benchmark execution, structured fact extraction, and metrics."""

import csv
from dataclasses import dataclass, field, replace
import json
import math
from pathlib import Path
from typing import Iterable

from authority_lens import (
    AuthorityEngine,
    Effect,
    ExternalStatus,
    PathStatus,
)
from consequence_model import translate_effective_state
from control_view import (
    AuthorityLensControlView,
    BaselineControlView,
    ControlContext,
    ControlOutcome,
    build_authority_lens_control_view,
    build_baseline_control_view,
    build_control_view,
)
from benchmark.ground_truth import (
    Fact,
    FactType,
    derive_ground_truth_facts,
    fact_sort_key,
)
from benchmark.scenarios import (
    CANONICAL_SCENARIO_IDS,
    BenchmarkScenario,
    build_scenarios,
)


CRITICAL_FACT_TYPES = {
    FactType.RESIDUAL_CAPABILITY,
    FactType.PENDING_EFFECT,
    FactType.UNKNOWN_AUTHORITY,
}

CATEGORY_FACT_TYPES = {
    "active_authority": {FactType.ACTIVE_CAPABILITY},
    "residual_authority": {FactType.RESIDUAL_CAPABILITY},
    "pending_effect": {FactType.PENDING_EFFECT},
    "unknown_authority": {FactType.UNKNOWN_AUTHORITY},
    "complete_revocation": {FactType.COMPLETE_REVOCATION},
    "target_permission": {FactType.TARGET_PERMISSION},
}


def _in_category(fact: Fact, category: str) -> bool:
    return fact.fact_type in CATEGORY_FACT_TYPES[category]


@dataclass(frozen=True)
class Coverage:
    covered: int
    total: int
    rate: float | None


@dataclass(frozen=True)
class MacroCoverage:
    scenarios: int
    rate: float | None


@dataclass(frozen=True)
class CCOR:
    omitted: int
    total: int
    rate: float | None


@dataclass(frozen=True)
class BaselinePresentedFacts:
    """The baseline's single target-local permission field."""

    target_permission: Fact

    @property
    def facts(self) -> tuple[Fact, ...]:
        return (self.target_permission,)


@dataclass(frozen=True)
class AuthorityLensPresentedFacts:
    """Target-local state plus the consequence sections rendered by the browser."""

    target_permission: Fact
    consequence_facts: tuple[Fact, ...]

    @property
    def facts(self) -> tuple[Fact, ...]:
        return tuple(sorted((self.target_permission, *self.consequence_facts), key=fact_sort_key))


@dataclass(frozen=True)
class ScenarioResult:
    scenario: BenchmarkScenario
    control_phase: str
    comparison_eligible: bool
    ground_truth_facts: tuple[Fact, ...]
    baseline_exposed_facts: tuple[Fact, ...]
    authoritylens_exposed_facts: tuple[Fact, ...]
    baseline_coverage: Coverage
    authoritylens_coverage: Coverage
    hidden_critical_facts_baseline: tuple[Fact, ...]
    hidden_critical_facts_authoritylens: tuple[Fact, ...]
    baseline_view: BaselineControlView = field(repr=False, compare=False)
    authoritylens_view: AuthorityLensControlView = field(repr=False, compare=False)
    baseline_presented: BaselinePresentedFacts | None = field(repr=False, compare=False)
    authoritylens_presented: AuthorityLensPresentedFacts | None = field(repr=False, compare=False)


@dataclass(frozen=True)
class BenchmarkReport:
    scenario_results: tuple[ScenarioResult, ...]
    eligible_scenario_count: int
    overall_baseline_coverage: Coverage
    overall_authoritylens_coverage: Coverage
    overall_baseline_macro_coverage: MacroCoverage
    overall_authoritylens_macro_coverage: MacroCoverage
    category_coverage: dict[str, tuple[Coverage, Coverage]]
    category_macro_coverage: dict[str, tuple[MacroCoverage, MacroCoverage]]
    hidden_critical_count_baseline: int
    hidden_critical_count_authoritylens: int
    ccor_baseline: CCOR
    ccor_authoritylens: CCOR


def _resource_action(scope: str | None) -> tuple[str | None, str | None]:
    if not scope or "." not in scope:
        return None, None
    return tuple(scope.split(".", 1))


def _engine_for_scenario(scenario: BenchmarkScenario) -> AuthorityEngine:
    engine = AuthorityEngine()
    for principal in scenario.principals:
        engine.add_principal(principal)
    for grant in scenario.grants:
        engine.add_grant(replace(grant))

    # Delegations are issued while every external issuer is known active; final
    # external states are applied after issuance to model later uncertainty/revocation.
    for state in scenario.external_states:
        engine.set_external_state(replace(state, status=ExternalStatus.CONFIRMED_ACTIVE))
    for delegation in scenario.delegations:
        engine.add_delegation(replace(delegation))
    for effect in scenario.pending_effects:
        engine.add_effect(replace(effect))

    grants_by_id = {grant.id: grant for grant in engine.grants}
    for grant_id in scenario.revoke_grant_ids:
        grant = grants_by_id[grant_id]
        engine.revoke_grant(grant.principal_id, grant.scope)
    for delegation_id in scenario.revoke_delegation_ids:
        engine.revoke_delegation(delegation_id)
    for state in scenario.external_states:
        engine.set_external_state(state)
    return engine


def _capability_fact(fact_type: FactType, capability) -> Fact:
    resource, action = _resource_action(capability.scope)
    authority = capability.authority
    return Fact(
        fact_type=fact_type,
        principal_id=capability.principal_id,
        resource=resource,
        action=action,
        scope=capability.scope,
        authority_source_id=authority.root_source_grant_id,
        principal_path=authority.principal_path,
        delegation_path=authority.delegation_path,
        path_status=authority.path_status.value,
    )


def _unknown_fact(risk, view) -> Fact:
    authority = risk.authority
    if authority is not None:
        resource, action = _resource_action(risk.scope)
        return Fact(
            fact_type=FactType.UNKNOWN_AUTHORITY,
            principal_id=risk.principal_id,
            resource=resource,
            action=action,
            scope=risk.scope,
            authority_source_id=authority.root_source_grant_id,
            principal_path=authority.principal_path,
            delegation_path=authority.delegation_path,
            path_status=authority.path_status.value,
        )
    return Fact(
        fact_type=FactType.UNKNOWN_AUTHORITY,
        principal_id=risk.principal_id,
        resource=view.context.resource.casefold(),
        status="unknown",
        principal_path=(risk.principal_id,),
        path_status=PathStatus.UNCERTAIN.value,
    )


def extract_baseline_facts(view: BaselineControlView) -> tuple[Fact, ...]:
    """Extract only the target-local permission state displayed by the baseline."""
    return present_baseline_view(view).facts


def present_baseline_view(view: BaselineControlView) -> BaselinePresentedFacts:
    return BaselinePresentedFacts(
        target_permission=Fact(
            fact_type=FactType.TARGET_PERMISSION,
            principal_id=view.context.target_principal,
            resource=view.context.resource.casefold(),
            status=view.access_status.casefold(),
        )
    )


def present_authoritylens_view(
    view: AuthorityLensControlView,
    baseline_view: BaselineControlView,
) -> AuthorityLensPresentedFacts:
    """Represent the browser's target-local state and consequence sections."""
    facts: set[Fact] = set()

    for item in view.active_items:
        facts.add(_capability_fact(FactType.ACTIVE_CAPABILITY, item))
    for item in view.residual_items:
        facts.add(_capability_fact(FactType.RESIDUAL_CAPABILITY, item))
    for item in view.pending_items:
        effect = item.effect
        resource, _ = _resource_action(effect.required_scope)
        facts.add(
            Fact(
                fact_type=FactType.PENDING_EFFECT,
                principal_id=effect.principal_id,
                resource=resource,
                action=effect.action,
                scope=effect.required_scope,
                status=effect.status.value,
                effect_id=effect.id,
                authority_source_id=effect.authority_source_id,
            )
        )
    for item in view.unknown_items:
        facts.add(_unknown_fact(item, view))

    if view.outcome == ControlOutcome.COMPLETE:
        facts.add(
            Fact(
                fact_type=FactType.COMPLETE_REVOCATION,
                resource=view.context.resource.casefold(),
            )
        )
    # app.py serializes this same target-local status into AuthorityLens
    # local_state; headline and description text are never parsed.
    target_permission = present_baseline_view(baseline_view).target_permission
    return AuthorityLensPresentedFacts(
        target_permission=target_permission,
        consequence_facts=tuple(sorted(facts, key=fact_sort_key)),
    )


def extract_authoritylens_facts(
    view: AuthorityLensControlView,
    baseline_view: BaselineControlView,
) -> tuple[Fact, ...]:
    return present_authoritylens_view(view, baseline_view).facts


def calculate_coverage(ground_truth: Iterable[Fact], exposed: Iterable[Fact]) -> Coverage:
    expected = set(ground_truth)
    communicated = set(exposed)
    covered = len(expected & communicated)
    return Coverage(
        covered=covered,
        total=len(expected),
        rate=(covered / len(expected)) if expected else None,
    )


def calculate_macro_coverage(scenario_coverages: Iterable[Coverage]) -> MacroCoverage:
    rates = [item.rate for item in scenario_coverages if item.rate is not None]
    return MacroCoverage(
        scenarios=len(rates),
        rate=(math.fsum(rates) / len(rates)) if rates else None,
    )


def calculate_ccor(ground_truth: Iterable[Fact], exposed: Iterable[Fact]) -> CCOR:
    critical = {fact for fact in ground_truth if fact.fact_type in CRITICAL_FACT_TYPES}
    communicated = set(exposed)
    omitted = len(critical - communicated)
    return CCOR(
        omitted=omitted,
        total=len(critical),
        rate=(omitted / len(critical)) if critical else None,
    )


def _hidden_critical(ground_truth: tuple[Fact, ...], exposed: tuple[Fact, ...]) -> tuple[Fact, ...]:
    communicated = set(exposed)
    return tuple(
        fact for fact in ground_truth
        if fact.fact_type in CRITICAL_FACT_TYPES and fact not in communicated
    )


def evaluate_scenario(scenario: BenchmarkScenario) -> ScenarioResult:
    engine = _engine_for_scenario(scenario)
    state = engine.calculate()
    context = ControlContext(
        resource=scenario.resource,
        requested_action=scenario.requested_action,
        target_principal=scenario.target_principal,
        action_confirmed=(
            scenario.requested_action.casefold() == "revoke"
            and bool(scenario.revoke_grant_ids or scenario.revoke_delegation_ids)
        ),
    )
    comparison_eligible = context.action_confirmed
    control_phase = "AFTER_ACTION" if comparison_eligible else "BEFORE_ACTION"
    summary = translate_effective_state(state)
    control_view = build_control_view(context, summary)
    baseline_view = build_baseline_control_view(control_view)
    authoritylens_view = build_authority_lens_control_view(control_view)

    ground_truth = derive_ground_truth_facts(state, context)
    if comparison_eligible:
        baseline_presented = present_baseline_view(baseline_view)
        authoritylens_presented = present_authoritylens_view(authoritylens_view, baseline_view)
        baseline_exposed = baseline_presented.facts
        authoritylens_exposed = authoritylens_presented.facts
        baseline_coverage = calculate_coverage(ground_truth, baseline_exposed)
        authoritylens_coverage = calculate_coverage(ground_truth, authoritylens_exposed)
        hidden_baseline = _hidden_critical(ground_truth, baseline_exposed)
        hidden_lens = _hidden_critical(ground_truth, authoritylens_exposed)
    else:
        # Phase 3B.1 hides both comparison panels until a confirmed revoke occurs.
        baseline_presented = None
        authoritylens_presented = None
        baseline_exposed = ()
        authoritylens_exposed = ()
        baseline_coverage = Coverage(0, 0, None)
        authoritylens_coverage = Coverage(0, 0, None)
        hidden_baseline = ()
        hidden_lens = ()
    return ScenarioResult(
        scenario=scenario,
        control_phase=control_phase,
        comparison_eligible=comparison_eligible,
        ground_truth_facts=ground_truth,
        baseline_exposed_facts=baseline_exposed,
        authoritylens_exposed_facts=authoritylens_exposed,
        baseline_coverage=baseline_coverage,
        authoritylens_coverage=authoritylens_coverage,
        hidden_critical_facts_baseline=hidden_baseline,
        hidden_critical_facts_authoritylens=hidden_lens,
        baseline_view=baseline_view,
        authoritylens_view=authoritylens_view,
        baseline_presented=baseline_presented,
        authoritylens_presented=authoritylens_presented,
    )


def _aggregate_coverage(results: Iterable[ScenarioResult], category: str | None = None) -> tuple[Coverage, Coverage]:
    baseline_covered = baseline_total = lens_covered = lens_total = 0
    for result in results:
        if not result.comparison_eligible:
            continue
        ground_truth = result.ground_truth_facts
        baseline = result.baseline_exposed_facts
        lens = result.authoritylens_exposed_facts
        if category is not None:
            ground_truth = tuple(fact for fact in ground_truth if _in_category(fact, category))
            baseline = tuple(fact for fact in baseline if _in_category(fact, category))
            lens = tuple(fact for fact in lens if _in_category(fact, category))
        baseline_metric = calculate_coverage(ground_truth, baseline)
        lens_metric = calculate_coverage(ground_truth, lens)
        baseline_covered += baseline_metric.covered
        baseline_total += baseline_metric.total
        lens_covered += lens_metric.covered
        lens_total += lens_metric.total

    return (
        Coverage(baseline_covered, baseline_total, baseline_covered / baseline_total if baseline_total else None),
        Coverage(lens_covered, lens_total, lens_covered / lens_total if lens_total else None),
    )


def _aggregate_macro_coverage(
    results: Iterable[ScenarioResult], category: str | None = None
) -> tuple[MacroCoverage, MacroCoverage]:
    baseline_rates: list[Coverage] = []
    lens_rates: list[Coverage] = []
    for result in results:
        if not result.comparison_eligible:
            continue
        ground_truth = result.ground_truth_facts
        baseline = result.baseline_exposed_facts
        lens = result.authoritylens_exposed_facts
        if category is not None:
            ground_truth = tuple(fact for fact in ground_truth if _in_category(fact, category))
            baseline = tuple(fact for fact in baseline if _in_category(fact, category))
            lens = tuple(fact for fact in lens if _in_category(fact, category))
        baseline_rates.append(calculate_coverage(ground_truth, baseline))
        lens_rates.append(calculate_coverage(ground_truth, lens))
    return calculate_macro_coverage(baseline_rates), calculate_macro_coverage(lens_rates)


def _aggregate_ccor(results: Iterable[ScenarioResult], lens: bool) -> CCOR:
    omitted = total = 0
    for result in results:
        if not result.comparison_eligible:
            continue
        exposed = result.authoritylens_exposed_facts if lens else result.baseline_exposed_facts
        value = calculate_ccor(result.ground_truth_facts, exposed)
        omitted += value.omitted
        total += value.total
    return CCOR(omitted, total, omitted / total if total else None)


def evaluate_benchmark(scenarios: Iterable[BenchmarkScenario] | None = None) -> BenchmarkReport:
    scenario_results = tuple(
        evaluate_scenario(item) for item in (scenarios if scenarios is not None else build_scenarios())
    )
    overall_baseline, overall_lens = _aggregate_coverage(scenario_results)
    overall_baseline_macro, overall_lens_macro = _aggregate_macro_coverage(scenario_results)
    categories = {
        name: _aggregate_coverage(scenario_results, name)
        for name in CATEGORY_FACT_TYPES
    }
    category_macros = {
        name: _aggregate_macro_coverage(scenario_results, name)
        for name in CATEGORY_FACT_TYPES
    }
    hidden_baseline = sum(len(item.hidden_critical_facts_baseline) for item in scenario_results)
    hidden_lens = sum(len(item.hidden_critical_facts_authoritylens) for item in scenario_results)
    return BenchmarkReport(
        scenario_results=scenario_results,
        eligible_scenario_count=sum(item.comparison_eligible for item in scenario_results),
        overall_baseline_coverage=overall_baseline,
        overall_authoritylens_coverage=overall_lens,
        overall_baseline_macro_coverage=overall_baseline_macro,
        overall_authoritylens_macro_coverage=overall_lens_macro,
        category_coverage=categories,
        category_macro_coverage=category_macros,
        hidden_critical_count_baseline=hidden_baseline,
        hidden_critical_count_authoritylens=hidden_lens,
        ccor_baseline=_aggregate_ccor(scenario_results, lens=False),
        ccor_authoritylens=_aggregate_ccor(scenario_results, lens=True),
    )


def fact_to_dict(fact: Fact) -> dict:
    return {
        "type": fact.fact_type.value,
        "principal_id": fact.principal_id,
        "resource": fact.resource,
        "action": fact.action,
        "scope": fact.scope,
        "status": fact.status,
        "effect_id": fact.effect_id,
        "authority_source_id": fact.authority_source_id,
        "principal_path": list(fact.principal_path),
        "delegation_path": list(fact.delegation_path),
        "path_status": fact.path_status,
    }


def _coverage_to_dict(coverage: Coverage) -> dict:
    return {
        "covered": coverage.covered,
        "total": coverage.total,
        "rate": coverage.rate,
    }


def _macro_to_dict(coverage: MacroCoverage, scenario_population: int) -> dict:
    return {
        "included_scenario_count": coverage.scenarios,
        "scenario_population": scenario_population,
        "rate": coverage.rate,
    }


def _ccor_to_dict(value: CCOR) -> dict:
    return {"omitted": value.omitted, "total": value.total, "rate": value.rate}


def _scenario_to_dict(scenario: BenchmarkScenario) -> dict:
    return {
        "scenario_id": scenario.scenario_id,
        "description": scenario.description,
        "principals": [
            {"id": item.id, "type": str(item.type), "parent_id": item.parent_id}
            for item in scenario.principals
        ],
        "grants": [
            {
                "id": item.id,
                "principal_id": item.principal_id,
                "scope": item.scope,
                "source_principal_id": item.source_principal_id,
            }
            for item in scenario.grants
        ],
        "delegations": [
            {"id": item.id, "from_id": item.from_id, "to_id": item.to_id, "scope": item.scope}
            for item in scenario.delegations
        ],
        "external_states": [
            {"principal_id": item.principal_id, "status": str(item.status)}
            for item in scenario.external_states
        ],
        "pending_effects": [
            {
                "id": item.id,
                "principal_id": item.principal_id,
                "action": item.action,
                "status": str(item.status),
                "required_scope": item.required_scope,
                "authority_source_id": item.authority_source_id,
            }
            for item in scenario.pending_effects
        ],
        "revoke_grant_ids": list(scenario.revoke_grant_ids),
        "revoke_delegation_ids": list(scenario.revoke_delegation_ids),
        "requested_action": scenario.requested_action,
        "target_principal": scenario.target_principal,
        "resource": scenario.resource,
    }


def result_to_dict(result: ScenarioResult) -> dict:
    return {
        **_scenario_to_dict(result.scenario),
        "control_phase": result.control_phase,
        "comparison_eligible": result.comparison_eligible,
        "comparison_status": (
            "ELIGIBLE_AFTER_ACTION"
            if result.comparison_eligible
            else "INELIGIBLE_BEFORE_ACTION"
        ),
        "ground_truth_facts": [fact_to_dict(fact) for fact in result.ground_truth_facts],
        "baseline_presented": (
            {
                "target_permission": fact_to_dict(result.baseline_presented.target_permission),
            }
            if result.baseline_presented is not None
            else None
        ),
        "authoritylens_presented": (
            {
                "target_permission": fact_to_dict(result.authoritylens_presented.target_permission),
                "consequence_facts": [
                    fact_to_dict(fact)
                    for fact in result.authoritylens_presented.consequence_facts
                ],
            }
            if result.authoritylens_presented is not None
            else None
        ),
        "baseline_exposed_facts": [fact_to_dict(fact) for fact in result.baseline_exposed_facts],
        "authoritylens_exposed_facts": [fact_to_dict(fact) for fact in result.authoritylens_exposed_facts],
        "baseline_coverage": _coverage_to_dict(result.baseline_coverage),
        "authoritylens_coverage": _coverage_to_dict(result.authoritylens_coverage),
        "hidden_critical_facts_baseline": [
            fact_to_dict(fact) for fact in result.hidden_critical_facts_baseline
        ],
        "hidden_critical_facts_authoritylens": [
            fact_to_dict(fact) for fact in result.hidden_critical_facts_authoritylens
        ],
    }


def report_to_dict(report: BenchmarkReport) -> dict:
    return {
        "benchmark": "AuthorityLens Benchmark",
        "scenario_count": len(report.scenario_results),
        "executed_scenario_count": len(report.scenario_results),
        "comparison_eligible_scenario_count": report.eligible_scenario_count,
        "comparison_ineligible_before_action_scenario_count": (
            len(report.scenario_results) - report.eligible_scenario_count
        ),
        "overall_ground_truth_coverage": {
            "baseline": {
                "micro": _coverage_to_dict(report.overall_baseline_coverage),
                "macro": _macro_to_dict(report.overall_baseline_macro_coverage, report.eligible_scenario_count),
            },
            "authoritylens": {
                "micro": _coverage_to_dict(report.overall_authoritylens_coverage),
                "macro": _macro_to_dict(report.overall_authoritylens_macro_coverage, report.eligible_scenario_count),
            },
        },
        "category_coverage": {
            name: {
                "baseline": {
                    "micro": _coverage_to_dict(values[0]),
                    "macro": _macro_to_dict(report.category_macro_coverage[name][0], report.eligible_scenario_count),
                },
                "authoritylens": {
                    "micro": _coverage_to_dict(values[1]),
                    "macro": _macro_to_dict(report.category_macro_coverage[name][1], report.eligible_scenario_count),
                },
            }
            for name, values in report.category_coverage.items()
        },
        "critical_consequence_omission_rate": {
            "denominator": "pooled critical fact instances in comparison-eligible AFTER_ACTION scenarios",
            "critical_fact_types": sorted(item.value for item in CRITICAL_FACT_TYPES),
            "baseline": _ccor_to_dict(report.ccor_baseline),
            "authoritylens": _ccor_to_dict(report.ccor_authoritylens),
        },
        "metric_definitions": {
            "comparison_eligibility": "only confirmed-revoke AFTER_ACTION rows are scored; BEFORE_ACTION rows retain ground truth but present no comparison facts and contribute no metric denominator",
            "micro": "pooled fact instances covered divided by pooled relevant ground-truth fact instances in eligible rows",
            "macro": "unweighted mean of eligible per-scenario coverage rates, omitting eligible scenarios with zero facts in the evaluated category",
            "ccor": "pooled critical consequence fact omissions divided by pooled critical facts in eligible AFTER_ACTION rows",
            "categories": "disjoint fact-type partitions",
        },
        "benchmark_assumptions": [
            "The AuthorityLens browser local-state field uses the same target-local status as BaselineControlView.",
            "For delegation-link revocation scenarios, the target-local permission estimand is the revoked recipient; any surviving descendant authority remains a separate system-level fact.",
            "A grant or delegation ID listed for revocation in a scenario fixture is treated as confirmed control-action evidence.",
            "External principals are treated as confirmed active when a delegation is issued, then the scenario's listed external status is applied.",
            "ExternalState has no resource or scope field, so an UNKNOWN external state is conservatively treated as relevant to the controlled resource.",
            "Already-issued descendant delegations may remain independently active after upstream revocation under the prototype assumption.",
        ],
        "hidden_critical_facts": {
            "baseline": report.hidden_critical_count_baseline,
            "authoritylens": report.hidden_critical_count_authoritylens,
        },
        "scenario_results": [result_to_dict(item) for item in report.scenario_results],
        "scientific_limitations": [
            "This benchmark measures factual information coverage only.",
            "Coverage is structured view-model data-path matching, not rendered-information coverage: the AuthorityLens extractor reads nested provenance fields, including source-grant IDs and delegation paths, that are not all printed in default comparison cards. The always-visible authority-chain diagram displays some path/status context, but it and the expandable system-state panel are outside the scored pair of panels.",
            "It does not prove users understand the information.",
            "It does not prove AuthorityLens reduces cognitive load.",
            "It does not prove AuthorityLens improves real-world safety.",
            "It does not establish user preference; those claims require later empirical study.",
            "Coverage and CCOR do not penalize unsupported or contradictory facts represented by a view model; precision and false-positive claim rates are not measured.",
            "Coverage compares the structured BaselineControlView and AuthorityLensControlView data paths only; both the shared always-visible authority-chain diagram and expandable system-state panel are outside the scored comparison.",
            "The 40 synthetic scenarios use one root grant and a linear delegation chain; scopes do not mix within a scenario, and queued-effect cases contain one effect.",
        ],
    }


def write_results(report: BenchmarkReport, path: str | Path) -> None:
    output = Path(path)
    output.write_text(
        json.dumps(report_to_dict(report), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_csv(report: BenchmarkReport, path: str | Path) -> None:
    output = Path(path)
    columns = (
        "scenario_id",
        "description",
        "control_phase",
        "comparison_eligible",
        "comparison_status",
        "target_principal",
        "resource",
        "requested_action",
        "ground_truth_facts",
        "baseline_exposed_facts",
        "authoritylens_exposed_facts",
        "baseline_coverage_covered",
        "baseline_coverage_total",
        "baseline_coverage_rate",
        "authoritylens_coverage_covered",
        "authoritylens_coverage_total",
        "authoritylens_coverage_rate",
        "hidden_critical_facts_baseline",
        "hidden_critical_facts_authoritylens",
    )
    with output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for result in report.scenario_results:
            writer.writerow({
                "scenario_id": result.scenario.scenario_id,
                "description": result.scenario.description,
                "control_phase": result.control_phase,
                "comparison_eligible": result.comparison_eligible,
                "comparison_status": (
                    "ELIGIBLE_AFTER_ACTION"
                    if result.comparison_eligible
                    else "INELIGIBLE_BEFORE_ACTION"
                ),
                "target_principal": result.scenario.target_principal,
                "resource": result.scenario.resource,
                "requested_action": result.scenario.requested_action,
                "ground_truth_facts": json.dumps(
                    [fact_to_dict(item) for item in result.ground_truth_facts],
                    sort_keys=True,
                ),
                "baseline_exposed_facts": json.dumps(
                    [fact_to_dict(item) for item in result.baseline_exposed_facts],
                    sort_keys=True,
                ),
                "authoritylens_exposed_facts": json.dumps(
                    [fact_to_dict(item) for item in result.authoritylens_exposed_facts],
                    sort_keys=True,
                ),
                "baseline_coverage_covered": result.baseline_coverage.covered,
                "baseline_coverage_total": result.baseline_coverage.total,
                "baseline_coverage_rate": (
                    result.baseline_coverage.rate
                    if result.baseline_coverage.rate is not None
                    else "N/A"
                ),
                "authoritylens_coverage_covered": result.authoritylens_coverage.covered,
                "authoritylens_coverage_total": result.authoritylens_coverage.total,
                "authoritylens_coverage_rate": (
                    result.authoritylens_coverage.rate
                    if result.authoritylens_coverage.rate is not None
                    else "N/A"
                ),
                "hidden_critical_facts_baseline": json.dumps(
                    [fact_to_dict(item) for item in result.hidden_critical_facts_baseline],
                    sort_keys=True,
                ),
                "hidden_critical_facts_authoritylens": json.dumps(
                    [fact_to_dict(item) for item in result.hidden_critical_facts_authoritylens],
                    sort_keys=True,
                ),
            })


def _percent(coverage: Coverage) -> str:
    return "N/A" if coverage.rate is None else f"{coverage.rate * 100:.1f}%"


def _percent_rate(rate: float | None) -> str:
    return "N/A" if rate is None else f"{rate * 100:.1f}%"


def format_report(report: BenchmarkReport) -> str:
    baseline_macro = report.overall_baseline_macro_coverage
    lens_macro = report.overall_authoritylens_macro_coverage
    lines = [
        "# AuthorityLens Benchmark",
        "",
        f"Scenarios executed through AuthorityEngine: {len(report.scenario_results)}",
        f"Comparison-eligible AFTER_ACTION scenarios: {report.eligible_scenario_count}",
        f"BEFORE_ACTION scenarios excluded from view scoring: {len(report.scenario_results) - report.eligible_scenario_count}",
        "",
        "## Structured view-model ground-truth coverage",
        "",
        "Only confirmed-revoke AFTER_ACTION rows contribute view-comparison metrics. BEFORE_ACTION rows retain engine-derived ground truth but have no exposed comparison facts and are excluded.",
        "Micro pools eligible fact instances; macro averages eligible per-scenario rates and omits eligible scenarios with zero ground-truth facts.",
        "",
        "| View | Micro GTC (covered / facts) | Macro GTC (mean / scenarios) |",
        "|---|---:|---:|",
        f"| Baseline | {_percent(report.overall_baseline_coverage)} ({report.overall_baseline_coverage.covered}/{report.overall_baseline_coverage.total}) | {_percent_rate(baseline_macro.rate)} ({baseline_macro.scenarios}/{report.eligible_scenario_count}) |",
        f"| AuthorityLens | {_percent(report.overall_authoritylens_coverage)} ({report.overall_authoritylens_coverage.covered}/{report.overall_authoritylens_coverage.total}) | {_percent_rate(lens_macro.rate)} ({lens_macro.scenarios}/{report.eligible_scenario_count}) |",
        "",
        "## Category coverage",
        "",
        "Fact categories are disjoint. Micro pools eligible category facts; macro averages eligible scenarios with at least one fact in that category.",
        "",
        "| Category | Baseline micro | Baseline macro (included / eligible scenarios) | AuthorityLens micro | AuthorityLens macro (included / eligible scenarios) |",
        "|---|---:|---:|---:|---:|",
    ]
    labels = {
        "active_authority": "Active authority",
        "residual_authority": "Residual authority",
        "pending_effect": "Pending effects",
        "unknown_authority": "Unknown authority",
        "complete_revocation": "Complete revocation",
        "target_permission": "Target-local permission",
    }
    for name, (baseline, lens) in report.category_coverage.items():
        baseline_category_macro, lens_category_macro = report.category_macro_coverage[name]
        lines.append(
            f"| {labels[name]} | {_percent(baseline)} ({baseline.covered}/{baseline.total}) | "
            f"{_percent_rate(baseline_category_macro.rate)} ({baseline_category_macro.scenarios}/{report.eligible_scenario_count}) | "
            f"{_percent(lens)} ({lens.covered}/{lens.total}) | "
            f"{_percent_rate(lens_category_macro.rate)} ({lens_category_macro.scenarios}/{report.eligible_scenario_count}) |"
        )
    lines.extend(
        [
            "",
            "## Critical consequence omission rate",
            "",
            "CCOR pools critical fact instances (residual authority, pending effect, unknown authority) from eligible AFTER_ACTION rows; denominator is total eligible critical facts. Zero denominator is N/A.",
            "",
            "| View | Omitted / critical facts | CCOR |",
            "|---|---:|---:|",
            f"| Baseline | {report.ccor_baseline.omitted}/{report.ccor_baseline.total} | {_percent_rate(report.ccor_baseline.rate)} |",
            f"| AuthorityLens | {report.ccor_authoritylens.omitted}/{report.ccor_authoritylens.total} | {_percent_rate(report.ccor_authoritylens.rate)} |",
            "",
            "## Counting assumptions",
            "",
            "- AuthorityLens target-local state uses the same structured target permission status as the baseline field rendered in the browser.",
            "- For revoked delegation-link scenarios, the target is the revoked recipient; surviving descendants remain separate system-level facts.",
            "- A grant or delegation ID listed for revocation in a scenario fixture is treated as confirmed control-action evidence.",
            "- External principals are treated as confirmed active when a delegation is issued, then the listed final external status is applied.",
            "- `ExternalState` has no scope field, so UNKNOWN external states are conservatively relevant to the controlled resource.",
            "- An issued descendant delegation may remain independently active after upstream revocation under the prototype assumption.",
            "",
            f"Hidden critical facts — Baseline: {report.hidden_critical_count_baseline}; AuthorityLens: {report.hidden_critical_count_authoritylens}.",
            "",
            "## Canonical scenarios",
            "",
            "| Scenario | Baseline GTC | AuthorityLens GTC | Hidden critical facts (Baseline / AuthorityLens) |",
            "|---|---:|---:|---:|",
        ]
    )
    canonical_ids = set(CANONICAL_SCENARIO_IDS)
    for result in report.scenario_results:
        if result.scenario.scenario_id not in canonical_ids:
            continue
        lines.append(
            f"| {result.scenario.scenario_id} | {_percent(result.baseline_coverage)} "
            f"({result.baseline_coverage.covered}/{result.baseline_coverage.total}) | "
            f"{_percent(result.authoritylens_coverage)} "
            f"({result.authoritylens_coverage.covered}/{result.authoritylens_coverage.total}) | "
            f"{len(result.hidden_critical_facts_baseline)} / {len(result.hidden_critical_facts_authoritylens)} |"
        )
    lines.extend(
        [
            "",
            "## Structural coverage limitation",
            "",
            "Coverage is structured view-model data-path matching, not rendered-information coverage: the AuthorityLens extractor reads nested provenance fields, including source-grant IDs and delegation paths, that are not all printed in default comparison cards. The always-visible authority-chain diagram displays some path/status context, but it and the expandable system-state panel are outside the scored pair of panels.",
            "",
            "## Scientific limitation",
            "",
            "This benchmark measures factual information coverage only. It does not establish human comprehension, lower cognitive load, usability, user preference, or improved real-world safety; those claims require later empirical study.",
            "Coverage and CCOR do not penalize unsupported or contradictory facts represented by a view model; precision and false-positive claim rates are not measured.",
            "Coverage compares the structured BaselineControlView and AuthorityLensControlView data paths only; both the shared always-visible authority-chain diagram and expandable system-state panel are outside the scored comparison.",
            "The 40 synthetic scenarios use one root grant and a linear delegation chain; scopes do not mix within a scenario, and queued-effect cases contain one effect.",
        ]
    )
    return "\n".join(lines)


def write_markdown_report(report: BenchmarkReport, path: str | Path) -> None:
    Path(path).write_text(format_report(report) + "\n", encoding="utf-8")
