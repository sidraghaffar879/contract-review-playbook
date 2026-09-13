# Contract Review Against a Negotiation Playbook

First-pass legal review for vendor agreements, MSAs and NDAs: the tool reads a contract (PDF / DOCX / text), **finds each clause, checks it against your organisation's playbook positions, flags deviations with the exact parameter that tripped, proposes redlines, and produces a risk score** so legal spends time on the 6 clauses that matter instead of reading 40 pages.

```
contract ─► segment into clauses ─► LLM classifies clause type
                                        ▼
                    fact extraction (cap months, notice days, net days, jurisdiction, ...)
                                        ▼
                    playbook rules  ─► standard | fallback | deviation | missing
                                        ▼
                    LLM redline + negotiation note (only for non-standard clauses)
                                        ▼
                    weighted risk score + Markdown / JSON report
```

## Why it works for legal teams

- **The playbook is a YAML file lawyers own** (`playbook.yaml`): standard position, acceptable fallback, machine-checkable parameters (e.g. `cap_months_max: 24`, `notice_days_max: 60`, `allowed_jurisdictions`) and a risk weight per clause type.
- **Explainable findings**: each issue names the parameter and value ("net 60 days exceeds maximum 45", "auto-renewal term of 24 months exceeds 12"), not a vague "this looks risky".
- **Missing-clause detection** for required protections (DPA, liability cap, confidentiality...).
- **Redlines and negotiation notes** are generated only where needed, anchored to the playbook wording.
- **Risk score** = Σ weight × severity, normalised, with LOW / MEDIUM / HIGH verdict for triage of an inbound contract queue.
- Deterministic rules layer means the tests are exact: the sample vendor MSA must produce the same nine findings every run.

## Quickstart

```bash
pip install -e ".[dev,docx]"
PYTHONPATH=src python -m contractreview.cli samples/vendor_msa.txt
# Risk score: 81/87 (93%) – HIGH
# standard: 0 · fallback: 1 · deviation: 8 · missing: 0
# ## 5 Limitation of Liability — DEVIATION (risk 15)
# - obligation is not expressed as mutual
# - liability is uncapped
# **Proposed redline:** Replace with our standard position: Each party's liability capped at 12 months' fees ...
PYTHONPATH=src python -m contractreview.cli samples/clean_msa.txt       # LOW
PYTHONPATH=src uvicorn contractreview.api:app --reload                  # POST /review (multipart file)
pytest -q
```

Use `CR_LLM_PROVIDER=anthropic|openai|bedrock` for real classification and redlines; the offline responder handles the samples deterministically.

## Layout

```
src/contractreview/
  playbook.yaml  # positions, parameters, weights (edit me)
  segment.py     # PDF / DOCX / text loading, clause splitting
  rules.py       # fact extraction + parameter checks
  review.py      # orchestration, scoring, Markdown / JSON reports
  api.py, cli.py
samples/         # a risky vendor MSA and a clean one
```

## Production notes

- Swap regex fact extraction for an LLM structured-output call returning the same keys when contracts vary widely in drafting style; keep `rules.check` as the single source of truth.
- Add DOCX tracked-change output (python-docx) to push redlines straight into Word.
- Log findings per counterparty to build negotiation history.
