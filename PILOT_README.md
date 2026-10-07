# AuthorityLens Pilot Runner

**Preparation only. No participants have been recruited and no real participant data have been collected.** The session flow is locally runnable for synthetic checks; its information page is a placeholder, not approved consent. Do not recruit participants or use this runner for real data collection as part of this work.

The runner is intended for supervised local use only. It is not a production remote-study deployment. Real supervised local pilot sessions must be run with `PILOT_STUDY_MODE=1`; this hides the ordinary AuthorityLens demo pages and scenario APIs while leaving the participant and authenticated researcher pilot routes available.

## Run locally

From PowerShell in the repository root:

```powershell
$secretBytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($secretBytes)
$env:PILOT_RESEARCHER_SECRET = [Convert]::ToBase64String($secretBytes)
$env:PILOT_STUDY_MODE = "1"
python app.py
```

The Flask app binds to `127.0.0.1:5000`. Open the researcher-only slot page on the same computer:

```text
http://127.0.0.1:5000/pilot/researcher
```

The browser requests HTTP Basic credentials: username `authoritylens-researcher` and the secret held in `PILOT_RESEARCHER_SECRET`. The secret must be at least 32 characters; it is not stored in the code or participant URL. Choose a slot from the prospectively prepared random allocation list and select **Prepare session**. The authenticated researcher page returns a one-time launch URL. Open it in a clean participant browser; it is consumed on first use or expires after 10 minutes, sets only the participant session cookie, then redirects to `/pilot`. It contains no slot, condition, or scoring metadata. A participant should never choose a slot. The participant flow contains an information/consent placeholder, common briefing, one unscored Calendar practice item, nine measured questions, optional 1–5 confidence, and an end screen. During measured trials, no correctness feedback is shown.

The page uses only same-origin HTML, CSS, JavaScript, and Flask endpoints. It makes no external requests. It does not ask for names or demographic information. The answer key and task catalog remain server-side. `/api/pilot/state` returns only the current question, assigned display, and condition-neutral scenario context; it does not return the seed, condition label, or private scoring fields. The context names relevant modeled actors but does not reveal whether downstream authority or effects remain. Matched transfer variants receive identical context. One session uses one condition; no second condition is exposed in that session. The participant cookie alone cannot access researcher controls or exports.

## Assigning the 16 slots

Seeds `0` through `15` are session slots. Even seeds use the target-local display; the adjacent odd seed uses the consequence-oriented display. Each adjacent pair has identical trial selection/order and opposite conditions:

| Researcher slots | Seeds | Allocation |
|---|---:|---|
| 1–2 | 0–1 | Same stimuli/order, opposite condition |
| 3–4 | 2–3 | Same stimuli/order, opposite condition |
| 5–6 | 4–5 | Same stimuli/order, opposite condition |
| 7–8 | 6–7 | Same stimuli/order, opposite condition |
| 9–10 | 8–9 | Same stimuli/order, opposite condition |
| 11–12 | 10–11 | Same stimuli/order, opposite condition |
| 13–14 | 12–13 | Same stimuli/order, opposite condition |
| 15–16 | 14–15 | Same stimuli/order, opposite condition |

Before any future recruitment, randomize the order of the eight pairs and, within each pair, randomly assign two eligible participants one each to the even and odd slot. Use each pair once before repeating. The seeded schedule does not randomize people. For fewer than 16 participants, report unused slots and avoid claiming full balance.

## Local data, timing, and stopping

Session assignments and answers are kept in server process memory and clear when the process exits. Werkzeug request logging is disabled; the participant cookie is HttpOnly and same-site. Researcher listings, session tokens, and JSON/CSV exports require the separate HTTP Basic researcher secret. There is no analytics, database, external service, or persistent response store. Researchers can explicitly download JSON or CSV from the separate researcher page. Those exports include scoring data, condition/seed metadata, and a random non-identifying `session_run_id`; they must remain researcher-side. The run ID distinguishes reuse of an allocation slot and is not sent to participants. Export both JSON and CSV after every participant and before preparing the next session; the in-memory session is the only copy while the server is running, and all sessions are lost when it stops.

The browser acknowledges a complete rendered trial after two `requestAnimationFrame` callbacks. A local monotonic clock starts at server receipt of that acknowledgement and stops when the answer request reaches the server. `response_time_ms` includes local browser/request overhead, so it is not a pure cognitive-time measure.

**Stop session** allows either retaining submitted answers as an explicitly incomplete session or withdrawing and discarding submitted answers from memory. Stopped sessions retain nine planned rows; unanswered rows have `missing_response=true` and are not scored. Practice is never in the measured records. No identifying fields are collected.

## Synthetic validation

Run the tests and benchmark-style scheduling checks without using the browser with participants:

```powershell
python -m pytest -q
```

To write the separate, clearly labeled serialization fixture:

```powershell
$env:PILOT_DRY_RUN = "true"
python pilot_dry_run.py --seed 0
```

The generated JSON/CSV is marked `SYNTHETIC DRY RUN — NOT PARTICIPANT DATA`. It is synthetic test material, not a participant record or study result. A server restart clears any temporary in-memory sessions created during local checks.

## Before any real human study

Determine whether institutional ethics / IRB review is required for the institution, study purpose, recruitment, and dissemination; complete applicable review before recruitment. Replace the placeholder with approved information/consent materials before recruiting anyone. Prospectively finalize eligibility, allocation, stopping/withdrawal, retention/deletion, and missing-data procedures. This repository is not ethics approval or legal advice.
