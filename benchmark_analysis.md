# AuthorityLens Benchmark Analysis

Generated from `benchmark_results.json`; this report does not alter the benchmark's ground truth or scores.

Scenarios executed: **40**  
Comparison-eligible AFTER_ACTION: **32**  
BEFORE_ACTION, not scored: **8**

Only confirmed-revoke AFTER_ACTION cases enter view comparisons. Before-action rows have no displayed comparison views and use N/A coverage.

The metric compares structured view-model data paths, not rendered card text or the full browser page. The AuthorityLens extractor reads nested provenance fields (including IDs and paths) not all printed in the cards; the shared authority-chain diagram and expandable system-state panel are outside the scored pair.

## Structured view-model coverage (GTC)

| View | Micro view-model GTC | Macro view-model GTC | Covered / relevant facts |
|---|---:|---:|---:|
| Conventional target-local | 34.8% | 37.9% | 32/92 |
| AuthorityLens | 100.0% | 100.0% | 92/92 |

## Category coverage

Micro coverage by disjoint fact category; N/A denotes a zero denominator.

| Category | Baseline | AuthorityLens | Facts |
|---|---:|---:|---:|
| Active authority | 0.0% | 100.0% | 8/8 |
| Complete revocation | 0.0% | 100.0% | 3/3 |
| Pending effects | 0.0% | 100.0% | 4/4 |
| Residual authority | 0.0% | 100.0% | 39/39 |
| Target-local permission | 100.0% | 100.0% | 32/32 |
| Unknown authority | 0.0% | 100.0% | 6/6 |

## Critical consequence omissions from structured view models

CCOR includes residual authority, pending effects, and unknown authority only; these are structured view-model facts, not an audit of visible text.

| View | Omitted / critical facts | CCOR | Hidden critical facts |
|---|---:|---:|---:|
| Conventional target-local | 49/49 | 100.0% | 49 |
| AuthorityLens | 0/49 | 0.0% | 0 |

| Critical fact type | Ground truth facts | Baseline omitted | AuthorityLens omitted |
|---|---:|---:|---:|
| residual_capability | 39 | 39 | 0 |
| pending_effect | 4 | 4 | 0 |
| unknown_authority | 6 | 6 | 0 |

## Scenario families

Families are assigned deterministically from the stable scenario ID patterns. Coverage uses only eligible rows in each family.

| Family | Scenarios | Eligible | Baseline micro GTC | AuthorityLens micro GTC |
|---|---:|---:|---:|---:|
| Canonical scenarios | 4 | 4 | 50.0% | 100.0% |
| Direct active authority | 2 | 0 | N/A | N/A |
| Clean delegation chains | 6 | 0 | N/A | N/A |
| Root grant revoked | 5 | 5 | 31.2% | 100.0% |
| Intermediate delegation revoked | 6 | 6 | 27.3% | 100.0% |
| Queued send with revocation | 3 | 3 | 25.0% | 100.0% |
| External principal at chain leaf | 11 | 11 | 42.3% | 100.0% |
| External principal in chain middle | 3 | 3 | 37.5% | 100.0% |

## Scenario mix

### Scope

| Value | Scenarios |
|---|---:|
| gmail.read | 20 |
| gmail.send | 20 |

### Delegation depth (links)

| Value | Scenarios |
|---|---:|
| 0 | 4 |
| 1 | 11 |
| 2 | 16 |
| 3 | 9 |

### Revocation type

| Value | Scenarios |
|---|---:|
| delegation_link | 6 |
| none | 8 |
| root_grant | 26 |

### Pending effects

| Value | Scenarios |
|---|---:|
| none | 36 |
| one_or_more | 4 |

### External state

| Value | Scenarios |
|---|---:|
| confirmed_active | 5 |
| confirmed_revoked | 5 |
| none | 25 |
| unknown | 5 |

### Control phase

| Value | Scenarios |
|---|---:|
| AFTER_ACTION | 32 |
| BEFORE_ACTION | 8 |

## Canonical scenarios

| Scenario ID | Baseline GTC | AuthorityLens GTC | Hidden critical facts (Baseline / AuthorityLens) |
|---|---:|---:|---:|
| S001_complete_revocation | 50.0% (1/2) | 100.0% (2/2) | 0 / 0 |
| S002_single_residual_delegate | 50.0% (1/2) | 100.0% (2/2) | 1 / 0 |
| S003_queued_action | 50.0% (1/2) | 100.0% (2/2) | 1 / 0 |
| S004_unknown_external_agent | 50.0% (1/2) | 100.0% (2/2) | 1 / 0 |

## Interpretation limit

This analysis measures factual information coverage only. It does not establish human comprehension, lower cognitive load, usability, preference, or improved real-world safety.

AuthorityLens fact extraction reads typed view-model fields and nested EffectiveState provenance; it does not inspect DOM, screenshots, or rendered descriptions. Exact source/delegation identifiers and full paths counted by the extractor are not all printed in the default cards. The visible authority-chain diagram communicates some path and status information but is outside the scored panels.

## Additional metric and scenario limits

- Coverage and CCOR do not penalize unsupported or contradictory facts represented by a view model; precision and false-positive claim rates are not measured.
- Coverage compares the structured BaselineControlView and AuthorityLensControlView data paths only; both the shared always-visible authority-chain diagram and expandable system-state panel are outside the scored comparison.
- The 40 synthetic scenarios use one root grant and a linear delegation chain; scopes do not mix within a scenario, and queued-effect cases contain one effect.
