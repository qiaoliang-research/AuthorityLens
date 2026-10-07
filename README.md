# AuthorityLens

## What can an AI agent still do after you revoke access?

A target-local permission can be **OFF** while system-level consequences remain. Delegated authority, queued effects, and unresolved external state may still matter after that local status. AuthorityLens is a usable-security / HCI research prototype exploring how an interface should communicate these consequences after a control action.

## The problem

“Agent A — Gmail access: OFF” can be accurate about Agent A without answering whether Agent B retains a previously issued delegation, whether an earlier queued email may still complete, or whether an external agent’s state has been confirmed. The prototype keeps authority to start new work, pending effects, and unknown state separate. Unknown means unresolved, not active or revoked.

The model uses an explicit, non-universal assumption: an issued delegation may remain independently active after an upstream grant is revoked until the delegation itself is revoked. Effects and external states are synthetic inputs; the demo does not connect to Gmail or execute asynchronous work.

## Research question and boundary

After a completed revoke action in a delegated-agent workflow, does a consequence-oriented view help people identify residual authority, pending effects, and unresolved state more accurately than a fair target-local permission indicator—and what time or workload costs might it impose?

Prior work already studies agent authorization, least privilege, delegation, revocation, and closure. AuthorityLens does not propose a new authorization protocol or new revocation semantics. No human-subject study has been conducted; no comprehension, usability, decision, or safety benefit is claimed.

## What is included

- Synthetic Python authority model, deterministic consequence/control views, and a four-scenario Flask demo.
- Structured representation benchmark: 40 synthetic scenarios, of which 32 confirmed-revoke post-action cases are eligible for comparison.
- Technical report, focused related-work materials, benchmark results, and a pilot-ready session design.
- Public portfolio page and selected figures.

The benchmark compares project-defined facts in structured view models. It is specification-coupled and does not measure rendered-page coverage or human comprehension. See [benchmark report](benchmark_report.md) and [analysis](benchmark_analysis.md).

## Run the demo

Python 3.11+ is recommended. From this directory:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000`. The regular demo is available by default. The separate pilot runner is preparation only. Real supervised local pilot sessions require `PILOT_STUDY_MODE=1` and a researcher secret; the runner is not a production remote-study deployment. Read [PILOT_README.md](PILOT_README.md) before operating that mode. Do not recruit without replacing the placeholder participant information and determining applicable institutional ethics / IRB requirements.

To reproduce the structured benchmark:

```powershell
python evaluate.py
```

To run the regression suite:

```powershell
python -m pytest -q
```

## Navigate the project

### For readers

- [Open the portfolio page](portfolio/final/index.html)
- [Review selected figure captions](portfolio/FIGURE_CAPTIONS.md)
- [Read the technical report](TECHNICAL_REPORT.md)
- [Review benchmark results](benchmark_report.md)
- [Review related work](RELATED_WORK_MATRIX.md)
- [Read the proposed human-study protocol](PILOT_PROTOCOL.md)
- [Read v1 release notes](RELEASE_NOTES_V1.md)

### Implementation

`authority_lens.py`, `consequence_model.py`, `control_view.py`, and `app.py` implement the system pipeline. `benchmark/` contains a separate structured-fact projection and evaluators. `tests/` contains the regression suite.

## Evidence boundary

The available evidence is executable model behavior, deterministic synthetic scenarios, regression tests, and structured representation coverage. It does not show whether people notice or understand the views, make better decisions, experience acceptable workload, or improve real-world safety. The proposed human-comprehension study remains future work.


