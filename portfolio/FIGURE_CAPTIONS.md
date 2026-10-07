# AuthorityLens portfolio figures

The portfolio uses four primary visuals. They are deliberately limited to the motivating contradiction, the data path, the four modeled outcomes, and the structured benchmark.

## 1. Hero — Residual delegation

- **Description:** Before revocation, Agent A has Gmail read authority and Agent B receives a delegation; afterward, the target-local view shows Agent A as OFF while AuthorityLens shows Agent B can still read Gmail under the prototype assumption.
- **Notice:** The local indicator is accurate about its target, while the system-level view carries a surviving descendant authority.
- **Supports:** The research question about communicating consequences beyond a target-local permission state.
- **Does not establish:** Universal revocation behavior, prevalence in deployed platforms, or user comprehension.
- **Assets:** `portfolio/final/assets/hero-residual.svg` and `hero-residual.png`.

## 2. Architecture — Shared state, separate fact projection

- **Description:** `EffectiveState` feeds the consequence/control pipeline and both comparison views; a separate projection from `EffectiveState` supplies benchmark ground-truth facts.
- **Notice:** The benchmark fact projection does not derive its expected facts from `ControlView`, while both views share the same backend state.
- **Supports:** The implemented data flow and evaluation architecture.
- **Does not establish:** Model completeness, correspondence to real provider behavior, or independence from the model vocabulary.
- **Asset:** `portfolio/final/assets/architecture.svg`.

## 3. Four modeled post-control states

- **Description:** The synthetic cases distinguish complete closure, residual delegated authority, a pending effect, and an unknown external state.
- **Notice:** A completed local revoke can coexist with distinct system-level outcomes; pending effects are not authority, and unknown state is not confirmed active or revoked.
- **Supports:** The state distinctions represented by the demo and benchmark scenarios.
- **Does not establish:** How often these states occur in deployed systems or how people interpret them.
- **Asset:** `portfolio/final/assets/four-states.svg`.

## 4. Structured representation coverage

- **Description:** Exact structured-view-model matches for project-defined residual, pending, and unknown fact categories in eligible post-action scenarios.
- **Notice:** The target-local baseline reports its target-local scope; the consequence view also carries the modeled system-level categories.
- **Supports:** A deterministic representation check under the project’s taxonomy.
- **Does not establish:** Rendered-page coverage, comprehension, usability, safety, or an independent semantic oracle. Some scored provenance fields are not printed in the default cards.
- **Asset:** `portfolio/final/assets/structured-coverage.svg`.
