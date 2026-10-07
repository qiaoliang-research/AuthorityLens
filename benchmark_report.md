# AuthorityLens Benchmark

Scenarios executed through AuthorityEngine: 40
Comparison-eligible AFTER_ACTION scenarios: 32
BEFORE_ACTION scenarios excluded from view scoring: 8

## Structured view-model ground-truth coverage

Only confirmed-revoke AFTER_ACTION rows contribute view-comparison metrics. BEFORE_ACTION rows retain engine-derived ground truth but have no exposed comparison facts and are excluded.
Micro pools eligible fact instances; macro averages eligible per-scenario rates and omits eligible scenarios with zero ground-truth facts.

| View | Micro GTC (covered / facts) | Macro GTC (mean / scenarios) |
|---|---:|---:|
| Baseline | 34.8% (32/92) | 37.9% (32/32) |
| AuthorityLens | 100.0% (92/92) | 100.0% (32/32) |

## Category coverage

Fact categories are disjoint. Micro pools eligible category facts; macro averages eligible scenarios with at least one fact in that category.

| Category | Baseline micro | Baseline macro (included / eligible scenarios) | AuthorityLens micro | AuthorityLens macro (included / eligible scenarios) |
|---|---:|---:|---:|---:|
| Active authority | 0.0% (0/8) | 0.0% (6/32) | 100.0% (8/8) | 100.0% (6/32) |
| Residual authority | 0.0% (0/39) | 0.0% (25/32) | 100.0% (39/39) | 100.0% (25/32) |
| Pending effects | 0.0% (0/4) | 0.0% (4/32) | 100.0% (4/4) | 100.0% (4/32) |
| Unknown authority | 0.0% (0/6) | 0.0% (5/32) | 100.0% (6/6) | 100.0% (5/32) |
| Complete revocation | 0.0% (0/3) | 0.0% (3/32) | 100.0% (3/3) | 100.0% (3/32) |
| Target-local permission | 100.0% (32/32) | 100.0% (32/32) | 100.0% (32/32) | 100.0% (32/32) |

## Critical consequence omission rate

CCOR pools critical fact instances (residual authority, pending effect, unknown authority) from eligible AFTER_ACTION rows; denominator is total eligible critical facts. Zero denominator is N/A.

| View | Omitted / critical facts | CCOR |
|---|---:|---:|
| Baseline | 49/49 | 100.0% |
| AuthorityLens | 0/49 | 0.0% |

## Counting assumptions

- AuthorityLens target-local state uses the same structured target permission status as the baseline field rendered in the browser.
- For revoked delegation-link scenarios, the target is the revoked recipient; surviving descendants remain separate system-level facts.
- A grant or delegation ID listed for revocation in a scenario fixture is treated as confirmed control-action evidence.
- External principals are treated as confirmed active when a delegation is issued, then the listed final external status is applied.
- `ExternalState` has no scope field, so UNKNOWN external states are conservatively relevant to the controlled resource.
- An issued descendant delegation may remain independently active after upstream revocation under the prototype assumption.

Hidden critical facts — Baseline: 49; AuthorityLens: 0.

## Canonical scenarios

| Scenario | Baseline GTC | AuthorityLens GTC | Hidden critical facts (Baseline / AuthorityLens) |
|---|---:|---:|---:|
| S001_complete_revocation | 50.0% (1/2) | 100.0% (2/2) | 0 / 0 |
| S002_single_residual_delegate | 50.0% (1/2) | 100.0% (2/2) | 1 / 0 |
| S003_queued_action | 50.0% (1/2) | 100.0% (2/2) | 1 / 0 |
| S004_unknown_external_agent | 50.0% (1/2) | 100.0% (2/2) | 1 / 0 |

## Structural coverage limitation

Coverage is structured view-model data-path matching, not rendered-information coverage: the AuthorityLens extractor reads nested provenance fields, including source-grant IDs and delegation paths, that are not all printed in default comparison cards. The always-visible authority-chain diagram displays some path/status context, but it and the expandable system-state panel are outside the scored pair of panels.

## Scientific limitation

This benchmark measures factual information coverage only. It does not establish human comprehension, lower cognitive load, usability, user preference, or improved real-world safety; those claims require later empirical study.
Coverage and CCOR do not penalize unsupported or contradictory facts represented by a view model; precision and false-positive claim rates are not measured.
Coverage compares the structured BaselineControlView and AuthorityLensControlView data paths only; both the shared always-visible authority-chain diagram and expandable system-state panel are outside the scored comparison.
The 40 synthetic scenarios use one root grant and a linear delegation chain; scopes do not mix within a scenario, and queued-effect cases contain one effect.
