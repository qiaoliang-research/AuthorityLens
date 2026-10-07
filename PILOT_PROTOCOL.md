# AuthorityLens Exploratory Pilot Protocol

**Status: preparation only. No human study has been conducted.** No participants have been recruited, no real participant responses have been collected, and this package contains no pilot findings. Do not recruit or collect data until the applicable institutional ethics/IRB determination and any required review or approval are complete.

## Research question and scope

When people evaluate a completed revoke action in a delegated-agent workflow, does a consequence-oriented view help them identify residual authority, pending effects, and unresolved external state more accurately than a fair target-local permission indicator? What response-time or workload cost might accompany the additional information?

This is an exploratory, post-briefing interface-communication study. It does not measure unaided mental models: all participants receive the same brief explanation of delegation, queued operations, and unknown external state. The estimand is communication by the assigned interface after the common briefing and neutral scenario context, not comprehension without prior explanation.

The views and authority model are frozen. The target-local condition truthfully reports only the named target's current local permission status. It does not claim system-wide closure. The AuthorityLens condition shows the consequence-oriented view produced from the same `EffectiveState`. A target-local `CANNOT TELL` is a valid answer when that view does not establish a system-level fact.

## Prospective hypotheses

These are hypotheses, not findings:

- **H1:** Transfer/inference accuracy for modeled consequences may be higher under AuthorityLens than under the target-local indicator.
- **H2:** AuthorityLens may reduce false-safe responses on consequence-relevant trials.
- **H3:** Additional information may impose a response-time or workload cost. Response time is prepared as a measure; workload is optional and is not currently instrumented.

The pilot is intended for task and materials validation, not confirmation of these hypotheses.

## Conditions and design

Use a between-subjects interface condition. Each participant would see 9 trials under one view only: six selected direct-retrieval items and one state from each of the three matched transfer pairs.

1. **Target-local:** conventional local permission indicator for Agent A.
2. **Consequence-oriented:** AuthorityLens local state and any populated capability, pending-effect, or uncertainty sections.

Both conditions use the same task state and question. Use the same viewport, typography, controls, and timing origin. Do not show both conditions together, provide feedback during measured trials, or expose the other panel or private scoring key.

The task bank contains 16 logical items: 10 `DIRECT_RETRIEVAL` and 6 `TRANSFER_INFERENCE`. Each session samples one item from each matched transfer pair, so a participant does not see both versions of the same question. The schedule also omits any direct item whose underlying state is identical to a selected transfer item. It retains the full catalog across sessions while avoiding a direct same-state recall cue before a transfer trial:

- multi-hop closure: can the system rule out every Gmail reader in the chain? All links revoked vs a residual descendant path;
- send control: is another control action needed to ensure no email is sent? A queued effect vs an explicitly cancelled effect;
- external closure: can the system verify that no external agent can read a new message? Unknown vs confirmed-revoked external state.

The added items apply or combine information; they do not ask participants to reconstruct the authority graph. The AuthorityLens view communicates relevant underlying facts, so transfer accuracy is a modest application measure, not proof of deep conceptual understanding.

## Common briefing and response options

Give all participants the same neutral briefing:

> These are fictional Gmail-like scenarios, not connected to a real account. A queued operation is an operation already placed for execution; it is separate from permission to start a new operation. For this prototype's stipulated model, an already-issued delegation may remain independently active after an upstream grant or principal is revoked, until that delegation is explicitly revoked. This assumption describes these scenarios only; it is not a claim about how every real platform behaves. An external state marked unknown is unresolved, not confirmed active or confirmed revoked. The scenario context names the modeled actors relevant to the question. The interface panel may summarize only part of the current system state.

Each trial shows the same condition-neutral scenario context in both interface conditions. It names relevant modeled actors and gives generic workflow/resource context, but does not state whether downstream authority remains, whether an effect is pending or cancelled, or whether an external state is active, revoked, or unknown. Matched transfer variants share the same context. This shared context is part of the post-briefing study materials, not part of either interface condition.

Do not explain which view omits information or disclose task-specific answers. For each question, collect `YES`, `NO`, or `CANNOT TELL`. Keep `CANNOT TELL` available for both view conditions.

## Task semantics and scoring

Each task has a structured query, a synthetic state, a question type, an engine-derived exact answer, a private view-supported answer for each condition, and task-specific false-safe / false-alarm response rules. The loader reconstructs each case through `AuthorityEngine` and validates truth and view annotations before scheduling. The scoring logic never interprets prose to derive answers.

`DIRECT_RETRIEVAL` items ask for a named permission/effect fact, such as whether an agent can initiate a read or an already-queued effect could still complete. These items measure direct factual communication, not deep comprehension.

`TRANSFER_INFERENCE` items ask participants to infer whether a system-level closure claim is warranted for a new message, or whether the current queued-send state needs another control action. They do not repeat a panel answer sentence verbatim. The question and interface still share the same underlying concepts; this is modest transfer, not an independent theory test.

Exact truth and evidence alignment remain separate. Exact truth is the engine-derived answer. Evidence alignment is the answer supported by the assigned structured view. For descendant, external, or effect facts omitted from the target-local indicator, `CANNOT TELL` can be evidence-aligned even when exact engine truth is YES or NO.

### Primary exploratory outcome: false-safe rate

A false-safe error is a task-specific answer that communicates closure or absence when a relevant consequence remains possible or unresolved. Each task explicitly lists its `false_safe_if` responses because closure questions and action-needed questions have different polarity. `CANNOT TELL` is prohibited from that list and is never false-safe. For example, `YES` is false-safe when an active or unresolved reader remains; `NO` is false-safe on the queued-send item because it claims no further control is needed while an email may still be sent.

Let `R_i` be the engine-derived `relevant_consequence_remains` value, and `F_i` indicate that response `A_i` is listed by that task's validated false-safe rule:

```text
FalseSafeRate_c = count(valid trial i in condition c where R_i ∈ {YES, CANNOT TELL} and F_i)
                  / count(valid trial i in condition c where R_i ∈ {YES, CANNOT TELL})

ConfirmedRemainingFSR_c = count(F_i where R_i = YES) / count(valid trial i where R_i = YES)
UnresolvedFSR_c = count(F_i where R_i = CANNOT TELL) / count(valid trial i where R_i = CANNOT TELL)
```

Report counts and denominators for each rate. If a denominator is zero, report N/A. `YES` means a confirmed relevant consequence remains; `CANNOT TELL` means consequence closure is unresolved. This is a study-specific operational definition, not a validated clinical or safety metric.

### Secondary outcomes

- `DIRECT_RETRIEVAL` exact accuracy, separately from transfer;
- `TRANSFER_INFERENCE` exact accuracy, separately from direct retrieval;
- evidence alignment, separately by question type;
- false-alarm rate, using each task's explicit `false_alarm_if` rule only when the engine establishes `relevant_consequence_remains = NO`;
- response time from completed rendering to answer submission, with missing/timeouts reported;
- optional confidence on a fixed 1–5 scale (1 = not at all sure; 5 = very sure), only if consistently collected.

Do not combine direct and transfer into one comprehension score. Do not label `CANNOT TELL` as either active or revoked. Exact accuracy and evidence alignment answer different questions and both should be reported.

## Randomization, balanced slots, and researcher assignment

The deterministic runner supports seeds 0–15. Each schedule contains six direct items and one selected variant from each transfer pair. Exact-state duplicates are excluded, and the remaining direct items rotate across seed-pair blocks. Adjacent seeds `2k` / `2k+1` share selected stimuli and order while assigning opposite conditions: even seeds use `target_local`; odd seeds use `consequence_oriented`. Across eight pair blocks, each transfer variant is selected four times; the rotating direct items appear five or six times, while state-limited items appear whenever they do not duplicate the selected transfer state.

The runner does not randomize people. For up to 16 sessions, prepare a randomized order of the eight adjacent seed pairs before recruitment. For each pair, assign the next two eligible participants to its even and odd slots in randomized order, one each. Use each pair once before reusing any slot. Do not choose a slot based on participant characteristics or responses. With fewer than 16 sessions, report the unused slots and do not claim full schedule balance. The local researcher page accepts the already assigned slot; participants do not select or see their slot. A participant sees one interface condition only. Within-condition learning and the common briefing remain limitations.

## Session runner, timing, privacy, and withdrawal

`/pilot` implements an information/consent placeholder, common briefing, one unscored practice item, 9 measured questions, optional confidence on a 1–5 scale, and an end screen. The information page explicitly says that it is not approved consent and that the prepared runner is for synthetic checks only. Do not recruit or use this prototype with participants during this work. The separate practice item concerns an already scheduled Calendar reminder, is not part of `PILOT_TASKS.json`, is not scored, and is excluded from the analysis. Measured trials provide no correctness feedback.

The participant browser receives only the current display stimulus, question, response options, flow phase, and session-relative trial order. It receives no seed, condition field or label, task/scenario ID, expected answer, ground truth, false-safe rule, view-supported answer, or private catalog. The assigned view is built server-side from the frozen catalog and private schedule. No route returns the other condition.

The browser acknowledges a measured trial only after rendering its complete stimulus, question, and controls and waiting two animation frames. The local server starts a monotonic timer at receipt of that acknowledgement and stops it at receipt of the answer submission. `response_time_ms` therefore includes local browser/request handling overhead and is not a pure measure of cognitive time. Confidence is optional and does not change scoring.

The app binds to `127.0.0.1`, disables Werkzeug request access logging, uses an HttpOnly same-site participant cookie, and sends no analytics or external requests. Researcher controls and all scoring exports require HTTP Basic authentication using the password in `PILOT_RESEARCHER_SECRET` (username: `authoritylens-researcher`). The server fails closed when the environment variable is absent or shorter than 32 characters. The participant cookie never authorizes researcher routes. A researcher creates a session and receives a random one-time launch link; it expires after 10 minutes or first use, then sets only the participant cookie and redirects to `/pilot`. The launch URL contains no seed, condition, or scoring metadata. Use a separate clean browser for the participant flow.

Responses and schedules remain in process memory; stopping the server clears them. JSON/CSV files are generated only by an authenticated, explicit researcher export. A random 128-bit `session_run_id`, unrelated to identity and hidden from participants, distinguishes repeated uses of the same allocation slot and is included in researcher export filenames. No names, emails, IP addresses, precise locations, device fingerprints, participant codes, or unnecessary demographics are collected. The participant can stop and retain submitted answers as an incomplete session, or withdraw and discard submitted answers from memory. The researcher export marks `completed`, `trial_count`, `response_count`, `missing_response_indicator`, `session_relative_order`, `condition`, `seed`, and `session_run_id`. Missing trials are present as unscored rows with `missing_response=true`; practice is excluded. This is an operational prototype, not a secure data-management system.

## Measures and analysis unit

Use participant/session as the condition-assignment unit; repeated task responses within a session are clustered and are not independent participants. Report counts and denominators per condition, question type, matched pair, and task. Show raw values next to percentages. Across the 16-item bank, the exact-answer mix is 8 YES, 6 NO, and 2 CANNOT TELL; direct retrieval is 5/3/2 and transfer is 3/3/0. The T05 external-state item answers NO to whether closure is sufficiently confirmed, while its relevant consequence remains CANNOT TELL. A participant sees six of ten direct items and one item per transfer pair; the selected direct answer mix varies by schedule. The bank is small and deliberately not a population-balanced instrument.

Do not make a power or sample-size claim. A small pilot should emphasize direction and failure-mode discovery, not significance. No workload instrument is included in this package; if workload is retained as an outcome later, select and justify a brief measure before data collection rather than adding one post hoc.

## Recruitment, ethics, privacy, and stopping

No participants are recruited or studied as part of this work. Before any real human-subject data collection, determine whether institutional ethics / IRB review is required for the host institution, recruitment, purpose, publication, jurisdiction, and dissemination; complete any required review before recruitment. Replace the placeholder information/consent material with institutionally approved participant information and consent materials before recruiting anyone. Also finalize eligibility, recruitment language, withdrawal/pause procedures, individual-session stop conditions, study-level stopping criteria, missing-data handling, and data retention. Use fictional scenarios only. This repository is not legal advice or ethics approval.

No stopping rule is specified because no participant study is being run. A future approved protocol must define one prospectively. Do not treat synthetic dry-run records as human observations or results.

## Limitations and interpretation

This design measures post-briefing use of two specific displays on a small fictional task bank. It cannot establish unaided mental models, population effects, usability in real agent systems, user preference, acceptable cognitive load, improved decisions, safety, or harm reduction. The target-local condition intentionally has narrower information scope, so evidence alignment must be reported alongside engine-truth accuracy. Transfer items provide a limited application test and may still be answerable from explicit AuthorityLens facts. Excluding exact same-state direct/transfer pairs reduces one recall route but does not remove within-session learning or semantic overlap. Any future confirmatory study would need independently reviewed materials, a justified sample-size plan, predeclared analysis, and prospective participant allocation.
