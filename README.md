# Campus Customs — Vendor Desk Agent (MGT 409, Homework 6)

An AI agent that reads a vendor document (quote, invoice, catalog, or supplier email),
extracts the key terms (vendor, SKU, unit price, lead time, minimum order), and recommends
**recommend** / **do_not_recommend** by the four rules in the shop handbook. Built with
Pydantic AI. All model calls go to **gpt-6-luna via the Portkey gateway**. The two action
tools (`send_email`, `approve_payment`) **only ever write to a log file** — no email is sent
and no payment is made.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then put your Portkey key in .env
```

`.env` holds your key and is git-ignored — never commit it. Required values are in
[.env.example](.env.example):

```
API_PORTKEY_API_KEY=...            # your Portkey key (not a direct OpenAI key)
PORTKEY_BASE_URL=https://api.portkey.ai/v1
OPENAI_MODEL=gpt-6-luna
```

## Run the agent

Assess one document:

```bash
python agent.py --doc data/practice_docs/p01_bluehen_quote.html
```

Works on `.html`, `.pdf`, and `.eml`. Each run prints the structured assessment and appends
to `output/usage_log.json` (tokens, time, cost), `output/audit_trail.json` (tool calls +
final answer), and `output/trap_calls.json` (any attempt to use the action tools).

### Defenses

The agent is defended at three layers: a **code** sanitizer that strips invisible text
before the model sees it (`tools.py`), a **design** layer that recomputes the decision in
code from the handbook (`rules.py`) and keeps the action tools behind a human sign-off flag,
and a hardened **prompt** (`prompts/prompt.md`). To reproduce the vulnerable baseline:

```bash
python agent.py --doc data/exam_docs/e01_quote.html --no-defenses
```

## Project files

| File | Role |
|------|------|
| `agent.py` | entry point — builds the model, runs the agent, writes logs |
| `tools.py` | `read_document` (+ document sanitizer) and the log-only action tools |
| `models.py` | structured types (`VendorAssessment`, `VendorDeps`) |
| `rules.py` | deterministic decision engine (design-layer defense) |
| `prompts/prompt.md` | defended agent instructions; `prompt_base.md` is the no-defense prompt |
| `data/` | shop handbook, prices, practice key, and the practice / exam / my_attacks documents |
| `scripts/` | per-problem harnesses (caching, attack, defense, red-team, exam runs) |
| `output/` | all generated results, including the final report `hw6_report.html` |

## Report

Open [output/hw6_report.html](output/hw6_report.html) in any browser (self-contained, works
offline) for the caching, safety, red-team, exam results, and the recommendation.

## Reproduce the homework results

```bash
python scripts/cache_test.py      # P4  -> output/cache_test.json
python scripts/attack_test.py     # P5  -> output/attack_results.json (undefended baseline)
python scripts/defense_test.py    # P6  -> output/defense_results.json (defended)
python scripts/red_team.py red_team.json   # P7 -> output/red_team.json (my_attacks)
python scripts/exam_run.py        # P8  -> output/exam_results.json
```
