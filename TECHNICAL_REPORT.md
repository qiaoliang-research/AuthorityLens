# AuthorityLens: Authority State and Consequence Views

**Technical report**  
**Evaluation status:** deterministic synthetic benchmark completed; no human-subject evaluation was conducted.

## Abstract

AuthorityLens is a deterministic research prototype that connects a simplified authority-state engine to two views of the same synthetic delegated-agent scenarios: a target-local permission indicator and a consequence-oriented view. Its model keeps current authority, queued effects, and unresolved external state separate. A 40-scenario benchmark exercises the engine; 32 post-action cases are eligible for a comparison of structured view-model facts. Under the project's fact taxonomy, the target-local view model matches 32 of 92 facts (34.8% micro coverage) and the AuthorityLens view model matches 92 of 92 (100.0%). This is a specification-coupled data-path conformance check: separate extraction functions share the same engine state and vocabulary, and the tested schemas intentionally expose different categories. Extraction reads nested provenance fields that are not all rendered in the comparison cards; the shared authority-chain and technical-state panels are outside the scored panels. The result is not rendered-information coverage, an independent semantic oracle, or evidence about user comprehension. No human-subject evaluation was conducted.

## 1. Introduction and motivation

Autonomous agents make it possible for one principal to grant another principal the ability to act, and for that authority to be delegated again. Revoking a grant at one principal may not answer what remains possible throughout the system. The target may have lost local authority while a descendant retains a previously issued delegation. An action may also have been queued before revocation, and an external principal may fail to confirm its state.

This motivates a distinction between **target-local permission state** and **system-level remaining consequences**. A display that says “Agent A — Gmail access: OFF” can be accurate about Agent A and still not establish that all related capabilities, effects, or uncertainties have stopped. The baseline in this prototype intentionally models that local statement as a fair conventional indicator. AuthorityLens represents additional system consequences. The comparison concerns information carried by these specific models; it is not a claim about every permission interface.

The central state principle is:

```text
System truth = ActiveAuthority + PendingEffects + UnknownStates
Authority != PendingEffect
```

Authority answers whether a principal can initiate a new action. A pending effect records an action already queued that may still complete. Unknown state is unresolved: it is neither confirmed active nor confirmed revoked.

### Research question

> When people evaluate a completed revoke action in a delegated AI-agent workflow, does a consequence-oriented view help them identify residual authority, pending effects, and unresolved state more accurately than a fair target-local permission indicator, and what decision-time or workload costs does it impose?

This is a proposed empirical question, not a result of the current prototype or benchmark. The implementation models queued effects as static scenario state; it does not execute asynchronous work or model races.

## 2. Related work and positioning

### 2.1 Authorization, delegation, and revocation are established topics

Delegation chains and revocation propagation have a long history in access-control and trust-management research. Firozabadi and Sergot study revocation schemes for delegated authority, including propagation and dominance choices. Pham et al. provide a taxonomy of delegation models. Bussard, Nano, and Pinsdorf describe abstract cross-domain delegation, grant/revoke operations, and a unified user interface with a holistic Delegation Browser. EnTrust builds delegation graphs across cooperating programs and uses those paths to elicit authorization decisions from users. These works make it untenable to claim that delegation graphs, downstream revocation semantics, or user-facing views of delegated access are new in general.

Recent agent-permission research further narrows the space for a broad novelty claim. MiniScope proposes least-privilege authorization for tool-calling agents and includes a mobile-style permission interaction. Muruaga's Bounded Agents studies bounded delegation chains. Michael and Roesner survey 21 agent-permission proposals and examine permissions handling in five commercial agents. Wu et al. study users’ data-sharing permission preferences for AI agents and build a permission-prediction system. This is an active authorization and interface area, not an empty one.

Current IETF work adds protocol and model precedents: the WIMSE Working Group's *AI Identity Management System* draft composes existing identity and authorization standards for agent workloads; Hassan's individual *Attenuated Delegation Profile for Automated Agents* draft specifies a verifiable chain with per-hop scope attenuation; and Chen and Su's individual revocation draft proposes batch/cascade revocation. These are work-in-progress documents with different status and scope, not evidence of a user-facing consequence interface or human comprehension.

### 2.2 Post-revocation state and effects have close technical precedents

Several recent sources directly overlap with AuthorityLens’s state vocabulary. Choi, Jeong, and Lee’s *ResidualAuth* formalizes historical authorization state needed for correct decisions after a delegation edge is revoked. Liu, Yu, and Jiang’s VERA preprint defines edge-specific revocation over multi-agent delegation graphs while preserving independently authorized agents. Zhu and Wang’s preprint on root-scoped quiescence treats delegated work, queues, callbacks, provider operations, late effects, and indeterminate evidence. Santos-Grueiro’s *EffectBound* preprint asks when an interface boundary can truthfully report effect closure when earlier authorized work may still reach a later effect.

The closest breadth match is Watts’s September 2026 individual IETF Internet-Draft, *Revocation Closure for Agentic Authorization Systems*. It proposes authority graphs, consequential sinks, closure states including UNKNOWN, and closure receipts, with a worked example combining delegation and queued work. The Datatracker identifies it as an active individual Internet-Draft with no formal IETF standards-process standing; it must be cited as work in progress, not as an adopted standard. The recent arXiv works named above are preprints, not peer-reviewed findings. Their status does not erase the overlap: the prototype must not claim that residual authorization, queued effects, uncertainty, or closure evidence are newly identified concepts.

Abak's September 2026 individual Internet-Draft, *Evidence Requirements for Agent Control Delivery and Outcome Reconciliation*, is another adjacent evidence model. It separates issuer dispatch, receiver observation, enforcement outcome, and observed control effect. The draft defines a control effect as the runtime-state change caused by the control instruction, distinct from the business or physical effect of the action being controlled. Its freeze-race fixture also leaves one already in-flight operation's external effect UNKNOWN. This is not a general pending-business-effect model after authority revocation. The draft describes author-side technical probes and conformance fixtures, but no human study, and expressly does not define a transparency service or revoke semantics. It further rules out a broad claim that truthful reporting of uncertain control-delivery outcomes is itself new. Like the Watts draft, it has no formal IETF standards-process standing.

### 2.3 Human-facing permission work is substantial but adjacent

Usable-security studies have measured permission-scope misunderstandings, permission-state awareness, access-review decisions, and user responses to contextual permission information. EnTrust studies authorization through delegation paths. Jaferian et al. compare contextual access-review interfaces; Shen et al. study users’ misunderstandings of smartphone permission scope; Prange et al. observe permission awareness and revocation in a field study; and Baumer et al. test interface defaults in access-review decisions. *PrivWeb* studies users’ privacy controls and oversight during web-agent task execution. Janus presents an interactive agent-permission management harness evaluated with deterministic synthetic responders, not human participants. Kancherla et al. technically measure consent state that remains or fails to propagate after website revocation, but do not conduct a comprehension study. The PrEvoke project page describes a research agenda on expectations and actual consequences of privacy-permission revocation; this review did not locate a results paper for that agenda.

These works rule out claims that permission comprehension, revocation, contextual access review, or agent oversight are unstudied. In the focused sources reviewed here, I did not find a human-participant study of the exact combined comparison used by AuthorityLens: a target-local permission indicator versus a system-level post-revoke view showing descendant authority, queued effects, and unresolved external status together. This bounded observation does not establish novelty or prove that no such study exists. `HCI_POSITIONING.md` documents the search boundary and closest studies.

### 2.4 What this project contributes—and does not

The authority model is a simplified implementation, not a new authorization semantics or protocol. The artifact contributions are:

1. **SYSTEM:** An executable integration connects the frozen authority engine, consequence translator, view models, and synthetic state-transition demo.
2. **INTERFACE:** A research stimulus compares one target-local indicator with one consequence-oriented view generated from the same state. This is an implementation choice, not a claim that contextual or consequence-oriented permission interfaces are new.
3. **EVALUATION:** A deterministic structured-fact coverage check makes the prototype's view-model mappings inspectable over 40 designed scenarios. It is specification-coupled and does not independently validate the model or evaluate people.

None demonstrates better user understanding or safety.

The possible future research question is whether this specific consequence representation changes user judgments and what costs it creates. The focused literature search did not identify a participant study of this exact combined scenario comparison, but that absence is not a novelty finding; the search was not systematic and AuthorityLens has no participant data.

**Explicitly not novel:** delegation and revocation propagation; the possibility that downstream authority survives a revoke under some policies; pending work after authority changes; uncertain or indeterminate closure; authority lineage; and the general idea of giving users contextual access information.

**Explicit engineering assumptions:** the prototype permits an already-issued delegation to remain independently active after upstream revocation; a queued effect remains pending until explicitly cancelled or completed; external state is scenario-stipulated; and scopes are exact strings. The model is not a distributed authorization protocol and does not represent provider enforcement, leases, runtime scheduling, races, or actual service outcomes.

## 3. Authority and effect model

### 3.1 Principals, grants, and delegations

A **Principal** is a human, internal agent, or external agent. A **Grant** assigns a scope to a holder and names its source principal. A **Delegation** transfers a scope from one principal to another and has a stable ID. Authority entries preserve the holder, immediate delegator, root grant source, principal path, delegation path, and a path-health status. Scopes are exact strings such as `gmail.read` and `gmail.send`; the engine checks that a delegated scope does not exceed the delegator's effective authority at issuance.

Path health distinguishes three cases:

- **CLEAN:** relevant upstream grants and delegation links are confirmed valid.
- **RESIDUAL:** some upstream grant, link, or principal has been revoked, while a previously issued descendant delegation remains independently active under the prototype assumption.
- **UNCERTAIN:** the path includes an external principal whose state is unknown.

Unknown authority is kept separate from confirmed active authority. A path through an unknown external principal is unresolved, even if a downstream delegation remains represented. An external principal with confirmed-revoked state is not itself active; surviving downstream links can be marked residual.

### 3.2 Explicit delegation-survival assumption

The model does not automatically cascade-revoke descendants when an upstream grant or link is revoked. An already-issued delegation can remain independently active until that delegation is explicitly revoked. This is a deliberate research-model assumption that makes residual descendants observable. It is not a statement that real agent platforms preserve authority this way; production systems may apply different cascade, token, lease, or provider-side rules.

This assumption is consequential to the experiment. It is therefore shown in the demo and documented in the scenario fixtures, rather than being hidden in the implementation. Findings about residual authority are conditional on this model.

### 3.3 Effects and external state

An **Effect** represents a queued, completed, or cancelled operation. It records its principal, action, required scope, and (when available) the authority source ID that enabled it. Revoking the enabling scope prevents a new operation under that scope in the prototype, but does not itself cancel an already-queued effect. An explicit cancellation changes the effect state. The engine models state; it does not execute email or guarantee that an external service will carry out or cancel an operation.

**ExternalState** records `confirmed_active`, `confirmed_revoked`, or `unknown`. Unknown remains an explicit uncertainty. The model does not infer confirmation merely from sending a simulated revocation request.

## 4. System design and implementation

The implementation is intentionally small: Python domain objects and an `AuthorityEngine`; a deterministic consequence translator; frozen control-view models; a Flask backend; and plain HTML, CSS, and JavaScript. It has no database or real service integration.

For a scenario or replayed event history, the backend reconstructs a fresh engine state, applies the scenario's grants, delegation events, queued effects, revocations, and external-state changes, then calculates the views:

```text
AuthorityEngine
  -> EffectiveState
  -> translate_effective_state()
  -> ControlSummary
  -> build_control_view()
  -> BaselineControlView + AuthorityLensControlView
  -> JSON response
  -> browser rendering
```

The browser keeps a short event history in page memory and submits it for replay. The backend validates the next transition and rebuilds state; reset reconstructs the scenario's initial state. The four interactive scenarios are complete revocation, residual delegation, queued action, and unknown external agent. State changes and both views are recalculated together, so the presentation does not maintain a separate UI truth.

## 5. Interface models

### Conventional Permission View

The baseline models a target-local permission indicator. It is `ON` when the target principal itself has relevant confirmed active or residual authority; `UNKNOWN` when that target has relevant unresolved authority; and `OFF` when the target has no relevant current authority. Descendant authority, a pending effect, or uncertainty belonging to another principal does not change the target's local status. This is intended to approximate a conventional permission display, not every existing product.

### AuthorityLens

AuthorityLens is derived from the same `ControlView` and preserves the target-local status while presenting structured active capabilities, residual capabilities, pending consequences, unknown risks, and a complete outcome when the confirmed revoke leaves no relevant consequence. It does not describe a pending effect as current authority and does not convert unknown into safe or revoked.

The demo distinguishes `BEFORE_ACTION` and `AFTER_ACTION`. Before the scenario's designated revoke event, it shows a neutral current-state presentation rather than a revoke result. After confirmed revoke evidence, the frozen outcomes are `COMPLETE`, `PARTIAL`, `PENDING_EFFECTS`, and `UNCERTAIN`. The benchmark does not change Phase 1–3 semantics.

## 6. Synthetic benchmark methodology

### 6.1 Scenario set

The benchmark has four canonical scenarios and 36 generated cases, for 40 unique stable IDs. The generated families vary direct and delegated authority, delegation depth from zero to three links, read and send scopes, root-grant and intermediate-link revocation, queued send effects, external state (`confirmed_active`, `confirmed_revoked`, or `unknown`), and external principals at a leaf or in the middle of a chain. The family distribution is in `benchmark_analysis.md`. Each case is executed through the real `AuthorityEngine` rather than a separate hand-written authority calculator.

Eight cases are `BEFORE_ACTION`. The Phase 3B.1 interface intentionally does not show either revoke-comparison panel in those states. They are retained in the results with engine-derived ground truth but have N/A view scores. The primary comparison therefore uses the 32 confirmed-revoke `AFTER_ACTION` cases. This eligibility rule aligns the metric with the actual presentation phase; it also means this benchmark does not estimate view coverage for the neutral pre-action display.

### 6.2 Independent ground truth

For each scenario, the evaluator constructs the engine, calculates `EffectiveState`, and derives atomic facts from `EffectiveState` plus `ControlContext` and confirmed action evidence. The ground-truth function does not accept `ControlView`, `ControlOutcome`, `BaselineControlView`, or `AuthorityLensControlView`.

The fact taxonomy is disjoint:

- **TARGET_PERMISSION:** target principal's local state for the selected resource.
- **ACTIVE_CAPABILITY:** relevant `CLEAN` authority.
- **RESIDUAL_CAPABILITY:** relevant `RESIDUAL` authority.
- **PENDING_EFFECT:** relevant queued effect.
- **UNKNOWN_AUTHORITY:** unresolved external state or `UNCERTAIN` authority path.
- **COMPLETE_REVOCATION:** confirmed revoke evidence and no relevant active, residual, pending, or unknown facts.

Authority facts retain principal, scope, source grant, path, delegation IDs, and path status. A complete-revocation fact is computed directly from engine state and confirmed action evidence, not copied from the displayed outcome.

The frozen `ExternalState` has no resource field. The benchmark conservatively treats an unknown external state as relevant to the controlled resource. Scenario fixtures that list grant or delegation revocation are treated as confirmed control-action evidence. External principals are set active at delegation issuance, then assigned their final scenario status.

### 6.3 Presented facts and extraction

The benchmark does not parse headlines or descriptions and uses no LLM. `BaselinePresentedFacts` reads the target-local structured permission field the baseline renders. `AuthorityLensPresentedFacts` includes that same target-local state plus the active, residual, pending, unknown, and complete facts carried by the AuthorityLens view model. Both representations come from the same constructed `ControlView`; the target-local state is shared. This scoring rule does not inspect the DOM, screenshots, or rendered card text.

The AuthorityLens extractor reads nested authority provenance, including source-grant IDs, delegation paths, and path status. The default comparison cards render descriptions, not all of those structured identifiers. The browser also has an always-visible authority-chain diagram that shows some path and status context and an expandable system-state panel with more detail; both surfaces are outside the scored pair of panels. Therefore, “exposed” in the benchmark means present in the typed view-model data path, not necessarily displayed in a comparison card or salient to a reader. The result is not rendered-information coverage of the full page.

### 6.4 Metrics

For each eligible scenario, Ground Truth Coverage is:

```text
GTC = relevant ground-truth facts matched by the view / relevant ground-truth facts
```

**Micro GTC** pools the covered and total fact instances across eligible scenarios. **Macro GTC** is the unweighted mean of eligible per-scenario rates; empty-denominator scenarios are omitted and reported as N/A where applicable. Category metrics use the disjoint fact types above, so target permission is not double-counted as active authority. GTC measures coverage (recall) only: unsupported or contradictory facts present in a view do not reduce it. The benchmark does not measure precision or false-positive claim rates.

Critical Consequence Omission Rate is:

```text
CCOR = critical residual, pending, or unknown facts not exposed / total critical facts
```

A zero denominator yields N/A. The evaluator also records each scenario's ground-truth facts, exposed facts, coverage, and hidden critical facts in JSON and CSV. Machine-generated Markdown and figures are derived from these outputs.

## 7. Results: structured representation coverage

The benchmark executed 40 scenarios; 32 post-action cases were eligible and 8 pre-action cases were N/A. Across 92 defined fact instances, the target-local baseline matches 32 (34.8% micro GTC), and the AuthorityLens structured view matches 92 (100.0%). Macro GTC is 37.9% for the baseline and 100.0% for AuthorityLens, averaged across 32 eligible scenarios. These are descriptive counts over this designed fixture set, not estimates over users, products, or deployed agent systems.

| Fact category | Baseline model facts matched / total | Baseline coverage | AuthorityLens model facts matched / total | AuthorityLens coverage |
|---|---:|---:|---:|---:|
| Target permission | 32/32 | 100.0% | 32/32 | 100.0% |
| Active authority | 0/8 | 0.0% | 8/8 | 100.0% |
| Residual authority | 0/39 | 0.0% | 39/39 | 100.0% |
| Pending effect | 0/4 | 0.0% | 4/4 | 100.0% |
| Unknown authority | 0/6 | 0.0% | 6/6 | 100.0% |
| Complete revocation | 0/3 | 0.0% | 3/3 | 100.0% |

For the 49 critical fact instances (39 residual, 4 pending, 6 unknown), CCOR is 100.0% for the baseline (49 omitted) and 0.0% for AuthorityLens (none omitted). These counts are exact matches under the defined taxonomy; categories receive no severity weights, and this metric does not penalize unsupported claims.

Each canonical case has two relevant facts. The target-local model matches one of two (50.0%) in each; the AuthorityLens model matches two of two (100.0%). Hidden critical counts, baseline / AuthorityLens, are 0/0 for complete revocation, 1/0 for residual delegation, 1/0 for queued action, and 1/0 for unknown external agent. Family coverage and scenario composition appear in `benchmark_analysis.md`; the complete row-level data are in `benchmark_results.json` and `benchmark_results.csv`.

## 8. Discussion

The coverage difference follows the defined scope of the two representations. The baseline carries a target-local permission status; it correctly communicates that status for all 32 eligible target-permission facts. It does not carry descendant residual capabilities, pending effects, external unknowns, or a system-level completion fact, so it does not match those ground-truth categories. AuthorityLens's structured view model carries these categories and matches them in this scenario set; this does not mean all the matched fields are printed in its comparison card.

This result demonstrates a property of the prototype's structured data path under a defined fact taxonomy. It should not be framed as evidence that AuthorityLens is a better interface for people. Ground-truth facts are derived in a separate function from `EffectiveState` and action context, while presented facts are extracted from each structured view; however, both paths share the same AuthorityEngine output, state vocabulary, and specification. In that sense, this is a self-consistency / representation-conformance check, not an independent semantic oracle or human interpretation task. The intended contrast is also built into the compared schemas: the baseline exposes target-local permission, whereas AuthorityLens exposes the additional consequence fields. The result makes those mappings inspectable and reproducible, but does not show that the modeled world is complete or that the interface succeeds with people.

The 100% result should be read especially narrowly. The fact extractor can access structured lineage carried by the view objects, including IDs and paths not rendered in the comparison card. The authority-chain diagram displays some path structure, and the technical panel exposes further state detail, but neither is part of the scored pair of panels. Whether people notice these elements, open the technical panel, or connect the labels to an action remains unknown. The figure is not a performance target for future benchmark design; coverage definitions should remain stable and omissions should be reported rather than optimized away.

## 9. Limitations

The authority model uses exact scopes, synthetic principals, and simplified confirmation events. It is not a token, lease, distributed-systems, or provider-revocation model. Residual descendant survival is a chosen assumption. Real systems may cascade revocation, delay enforcement, retain independent credentials, or have other provider-specific effects that are not represented here.

Unknown external state is unscoped, so it is treated as relevant to the resource under evaluation. This is conservative but can overstate the number of resource-relevant unknown facts. Fixture-listed revocations stand for confirmed action evidence; real revoke requests can fail or remain unconfirmed. The model has no clock, asynchronous runtime, network, or race semantics. Queued effects are static states that change only through deterministic scenario actions; they illustrate a distinction between current authority and already-started work but do not simulate asynchronous execution.

The benchmark has 40 designed cases rather than a sample of real authorization systems. Its generated combinations are systematic but not an exhaustive distribution of agent workflows: each case uses one root grant and a linear delegation chain, scopes do not mix within a scenario, and queued-effect scenarios have one effect. It uses one fair target-local baseline, not a representative survey of conventional products. Micro results depend on how many fact instances each scenario contributes; macro results give each eligible scenario equal weight. Both are descriptive of this fixture set.

Finally, the evaluation compares structured fact objects using an explicit taxonomy and equality rules. The shared state source and specification make it a narrow conformance check, not independent validation that the state model is correct or exhaustive. It does not inspect a participant's interpretation, default-card salience, accessibility in actual use, task completion, cognitive load, or user preference. It proves neither comprehensibility nor real-world safety. No human-subject data were collected.

## 10. Future work

The next empirical question is whether people using the consequence-oriented view more accurately distinguish remaining authority, pending effects, and unknown external state, and what time or workload cost the added information creates. Adjacent studies on permission understanding, access-review interfaces, and agent controls motivate these measures but do not predict that AuthorityLens will help. `FUTURE_USER_STUDY.md` proposes a randomized, counterbalanced comparison, measures, analysis plan, and ethics/privacy considerations. It is explicitly a proposed protocol, not a conducted study or a result. Before recruitment or data collection, determine which institutional and jurisdictional ethics requirements apply and obtain any required review and approval.

Before any broader claim, a later engineering phase could also compare additional fair target-local and system-consequence representations, define richer but still defensible external-state scope, and test model assumptions against real system semantics without introducing live credentials or production access into this prototype.

## 11. Conclusion

AuthorityLens is an exploratory artifact that integrates a simplified authority-state engine with target-local and consequence-oriented views. Delegation revocation, residual authority, pending work, and uncertain closure all have close precedents; this report makes no claim that the underlying semantics are novel. The 40-scenario benchmark is a specification-level structured fact-coverage check: the target-local view matched 34.8% and the AuthorityLens view 100.0% of 92 defined facts over 32 eligible post-action cases. Those counts do not establish user comprehension, better decisions, or safety. The proposed human comparison remains open and should be treated as a research question, not a result.

## Reproducibility

Requires Python 3.11 or newer (`enum.StrEnum`); checked with Python 3.12.8. From the repository directory in PowerShell:

```powershell
python -m pip install -r requirements.txt
python -m pip install pytest  # if pytest is not already installed
python -m pytest -q
python evaluate.py
python -m pip install -r requirements-analysis.txt
python generate_figures.py
python app.py
```

Open `http://127.0.0.1:5000` for the demo. The benchmark writes `benchmark_results.json`, `benchmark_results.csv`, and `benchmark_report.md`. The analysis command writes `benchmark_analysis.md` and five PNG/SVG pairs under `artifacts/figures/`. The optional plotting packages are pinned. These artifacts were regenerated and hash-checked for repeatability in the current workspace.

## References

Publication status is stated for recent, not-yet-peer-reviewed sources. ArXiv submissions are cited as preprints; Internet-Drafts are marked as individual submissions or WIMSE working-group documents and as work in progress. These sources establish overlap or context; they do not validate AuthorityLens's semantics, benchmark, or user-outcome claims.

### Authorization, agent systems, and revocation

- Abak, A. T. (2026). *Evidence Requirements for Agent Control Delivery and Outcome Reconciliation.* Internet-Draft draft-abak-agent-control-delivery-evidence-01, updated September 4, 2026; active individual I-D. The draft body says “Intended status: Informational”; the Datatracker metadata lists no intended status. It is not endorsed and has no formal IETF standards-process standing. [Datatracker record and version](https://datatracker.ietf.org/doc/draft-abak-agent-control-delivery-evidence/01/).
- Bussard, L., Nano, A., & Pinsdorf, U. (2009). Delegation of access rights in multi-domain service compositions. *Identity in the Information Society, 2*, 137–154. [https://doi.org/10.1007/s12394-009-0031-5](https://doi.org/10.1007/s12394-009-0031-5).
- Chen, M., & Su, L. (2026). *OAuth 2.0 Agent Authorization Explicit Revocation.* Internet-Draft draft-chen-oauth-agent-revocation-00, April 27, 2026; active individual I-D, no formal IETF standards-process standing. The draft body says “Intended status: Standards Track,” but Datatracker metadata lists no intended status. [Datatracker record](https://datatracker.ietf.org/doc/draft-chen-oauth-agent-revocation/).
- Choi, M., Jeong, S., & Lee, S. (2026). *ResidualAuth: What Authorization State Must Language Agents Preserve under Revocable Delegation?* arXiv:2609.08062, version 1 (preprint submitted September 8, 2026). [https://arxiv.org/abs/2609.08062](https://arxiv.org/abs/2609.08062).
- Firozabadi, B. S., & Sergot, M. J. (2002). Revocation schemes for delegated authorities. In *Proceedings of the Third International Workshop on Policies for Distributed Systems and Networks* (pp. 210–213). IEEE. [https://doi.org/10.1109/POLICY.2002.1011310](https://doi.org/10.1109/POLICY.2002.1011310).
- Hassan, A. (2026). *An Attenuated Delegation Profile for Automated Agents.* Internet-Draft draft-hamr-oauth-agent-delegation-02, September 20, 2026; active individual I-D, no formal IETF standards-process standing. The draft body says “Intended status: Standards Track,” while Datatracker metadata lists no intended status. [Datatracker record](https://datatracker.ietf.org/doc/draft-hamr-oauth-agent-delegation/02/).
- Kasselman, P., Lombardo, J., Rosomakho, Y., Campbell, B., Steele, N., & Parecki, A. (2026). *AI Identity Management System.* WIMSE Working Group Internet-Draft draft-ietf-wimse-aims-00, September 15, 2026; WG document, not a final RFC. [Datatracker record](https://datatracker.ietf.org/doc/draft-ietf-wimse-aims/).
- Liu, L., Yu, H., & Jiang, X. (2026). *VERA: Authority-Preserving Edge Revocation for Federated AI-Agent Workflows.* arXiv:2608.30091, version 1 (preprint submitted August 30, 2026). [https://arxiv.org/abs/2608.30091](https://arxiv.org/abs/2608.30091).
- Brigham, N. G., Bagdasarian, E., Kohno, T., & Roesner, F. (2026). *Janus: A Playground for User-Involved Agentic Permission Management.* arXiv:2607.01510 (preprint submitted July 1, 2026; inspected record lists no venue). [https://arxiv.org/abs/2607.01510](https://arxiv.org/abs/2607.01510).
- Michael, A. E., & Roesner, F. (2026). *How Agents Ask for Permission: User Permissions for AI Agents, from Interfaces to Enforcement.* arXiv:2607.13718 (preprint submitted July 15, 2026). [https://arxiv.org/abs/2607.13718](https://arxiv.org/abs/2607.13718).
- Muruaga, X. (2026). *Bounded Agents: Delegation Security for Multi-Agent AI Systems.* arXiv:2608.15888, version 1 (preprint submitted August 16, 2026). [https://arxiv.org/abs/2608.15888](https://arxiv.org/abs/2608.15888).
- Pham, Q., Reid, J., McCullagh, A., & Dawson, E. (2010). On a taxonomy of delegation. *Computers & Security, 29*(5), 565–579. [https://doi.org/10.1016/j.cose.2009.12.009](https://doi.org/10.1016/j.cose.2009.12.009).
- Petracca, G., Sun, Y., Reineh, A.-A., McDaniel, P., Grossklags, J., & Jaeger, T. (2019). EnTrust: Regulating sensor access by cooperating programs via delegation graphs. In *28th USENIX Security Symposium* (pp. 567–584). USENIX Association. [https://www.usenix.org/conference/usenixsecurity19/presentation/petracca](https://www.usenix.org/conference/usenixsecurity19/presentation/petracca).
- Santos-Grueiro, I. (2026). *When Does Authorization End? Effect Closure at Provider Boundaries.* arXiv:2609.02866, version 1 (preprint submitted September 2, 2026). [https://arxiv.org/abs/2609.02866](https://arxiv.org/abs/2609.02866).
- Watts, D. (2026). *Revocation Closure for Agentic Authorization Systems.* Internet-Draft draft-watts-oauth-agent-revocation-closure-00, submitted September 13, 2026; active individual I-D, intended status Informational, no formal IETF standards-process standing. [Datatracker record](https://datatracker.ietf.org/doc/draft-watts-oauth-agent-revocation-closure/).
- Wu, Y., Yang, K., Roesner, F., Kohno, T., Zhang, N., & Iqbal, U. (2026). Towards automating data access permissions in AI agents. In *2026 IEEE Symposium on Security and Privacy*. IEEE. [https://doi.org/10.1109/SP63933.2026.00018](https://doi.org/10.1109/SP63933.2026.00018).
- Zhu, J., Tseng, K., Vernik, G., Huang, X., Patil, S. G., Fang, V., & Popa, R. A. (2025). *MiniScope: A Least Privilege Framework for Authorizing Tool Calling Agents.* arXiv:2512.11147, version 1 (preprint submitted December 11, 2025). [https://arxiv.org/abs/2512.11147](https://arxiv.org/abs/2512.11147).
- Zhu, G., & Wang, C. (2026). *Authorization Revocation for Long-Running AI Agents: Root-Scoped Quiescence under Delegation and Asynchronous Execution.* arXiv:2609.21284, version 1 (preprint submitted September 18, 2026). [https://arxiv.org/abs/2609.21284](https://arxiv.org/abs/2609.21284).

### Usable security, permission interfaces, and agent control

- Baumer, T., Reittinger, T., Kern, S., & Pernul, G. (2024). Digital nudges for access reviews: Guiding deciders to revoke excessive authorizations. In *Twentieth Symposium on Usable Privacy and Security (SOUPS 2024)* (pp. 239–258). USENIX Association. [USENIX paper page](https://www.usenix.org/conference/soups2024/presentation/baumer).
- Jaferian, P., Rashtian, H., & Beznosov, K. (2014). To authorize or not authorize: Helping users review access policies in organizations. In *Tenth Symposium on Usable Privacy and Security (SOUPS 2014)* (pp. 301–320). USENIX Association. [USENIX paper page](https://www.usenix.org/conference/soups2014/proceedings/presentation/jaferian).
- Kancherla, G. P., Bielova, N., Santos, C. T., & Bichhawat, A. (2025). Johnny can’t revoke consent either: Measuring compliance of consent revocation on the web. *Proceedings on Privacy Enhancing Technologies, 2025*(4), 329–347. [https://doi.org/10.56553/popets-2025-0133](https://doi.org/10.56553/popets-2025-0133).
- Prange, S., Knierim, P., Knoll, G., Dietz, F., De Luca, A., & Alt, F. (2024). “I do (not) need that Feature!” – Understanding users’ awareness and control of privacy permissions on Android smartphones. In *Twentieth Symposium on Usable Privacy and Security (SOUPS 2024)* (pp. 453–472). USENIX Association. [USENIX paper page](https://www.usenix.org/conference/soups2024/presentation/prange).
- PrEvoke research project. *Supporting users in informed privacy permission revocation.* Official project page; cited as a research agenda, not a results paper. [Project page](https://www.rz.unibw-muenchen.de/usable-security-and-privacy-en/research/projekte/prevoke).
- Shen, B., Wei, L., Xiang, C., Wu, Y., Shen, M., Zhou, Y., & Jin, X. (2021). Can systems explain permissions better? Understanding users’ misperceptions under smartphone runtime permission model. In *30th USENIX Security Symposium* (pp. 751–768). USENIX Association. [USENIX paper page](https://www.usenix.org/conference/usenixsecurity21/presentation/shen-bingyu).
- Zhang, S., Jiang, Y., Ma, R., Yang, Y., Xu, M., Huang, Z., Yi, X., & Li, H. (2026). PrivWeb: Unobtrusive and content-aware privacy protection for web agents. In *Proceedings of the 2026 CHI Conference on Human Factors in Computing Systems*. ACM. [https://doi.org/10.1145/3772318.3790919](https://doi.org/10.1145/3772318.3790919).
