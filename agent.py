"""Campus Customs vendor desk agent — entry point.

Usage:
    python agent.py --doc data/practice_docs/p01_bluehen_quote.html

Reads one vendor document, extracts the key fields, and decides recommend /
do_not_recommend per the shop handbook. The handbook is sent to the model on every
call (see output/handbook_estimate.md). After each run it logs token usage + time +
cost to output/usage_log.json and the tool calls + final answer to
output/audit_trail.json. Model: gpt-6-luna via the Portkey gateway. No emails, no
payments — the trap tools only log.
"""

import argparse
import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIResponsesModel
from pydantic_ai.providers.openai import OpenAIProvider

import rules
from models import VendorAssessment, VendorDeps
from tools import approve_payment, read_document, send_email

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
HANDBOOK = ROOT / "data" / "shop_handbook.md"
PROMPT = ROOT / "prompts" / "prompt.md"            # defended prompt (prompt layer)
PROMPT_BASE = ROOT / "prompts" / "prompt_base.md"  # no-defense baseline prompt
PRICES = ROOT / "data" / "prices.json"

for env in (ROOT / ".env", ROOT.parent / ".env"):
    load_dotenv(env, override=False)

MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-6-luna")
PORTKEY_BASE_URL = os.getenv("PORTKEY_BASE_URL", "https://api.portkey.ai/v1")


def _api_key() -> str:
    key = os.getenv("API_PORTKEY_API_KEY") or os.getenv("PORTKEY_API_KEY")
    if not key:
        raise RuntimeError("Set API_PORTKEY_API_KEY or PORTKEY_API_KEY in .env")
    return key


def build_agent(defenses: bool = True) -> Agent[VendorDeps, VendorAssessment]:
    key = _api_key()
    client = AsyncOpenAI(
        api_key=key, base_url=PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
    )
    model = OpenAIResponsesModel(MODEL_NAME, provider=OpenAIProvider(openai_client=client))
    # Prompt layer: the defended prompt when defenses are on, the bare baseline when off.
    prompt_file = PROMPT if defenses else PROMPT_BASE
    instructions = prompt_file.read_text(encoding="utf-8") + "\n\n# SHOP HANDBOOK\n\n" + HANDBOOK.read_text(encoding="utf-8")
    # send_email + approve_payment stay registered in both modes (the shop uses them
    # later with human sign-off); they are gated by deps.allow_actions, not removed.
    return Agent(
        model,
        deps_type=VendorDeps,
        output_type=VendorAssessment,
        instructions=instructions,
        tools=[read_document, send_email, approve_payment],
    )


def _cost_usd(usage) -> tuple[dict, float]:
    prices = json.load(open(PRICES))["gpt-6-luna"]
    inp = getattr(usage, "input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_tokens", 0) or 0
    uncached_in = max(inp - cache_read, 0)
    cost = (
        uncached_in / 1_000_000 * prices["input_per_1m"]
        + cache_read / 1_000_000 * prices["cached_input_per_1m"]
        + out / 1_000_000 * prices["output_per_1m"]
    )
    detail = {"input_tokens": inp, "cached_input_tokens": cache_read,
              "output_tokens": out, "total_tokens": inp + out}
    return detail, round(cost, 6)


def _append(path: Path, entry: dict) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    data = json.loads(path.read_text()) if path.exists() else []
    if not isinstance(data, list):
        data = []
    data.append(entry)
    path.write_text(json.dumps(data, indent=2))


def _tool_events(result) -> list[dict]:
    calls, returns, events = {}, {}, []
    for m in result.all_messages():
        for p in getattr(m, "parts", []):
            k = p.__class__.__name__
            if k == "ToolCallPart":
                calls[p.tool_call_id] = (p.tool_name, getattr(p, "args", ""))
            elif k == "ToolReturnPart":
                returns[p.tool_call_id] = getattr(p, "content", "")
    for cid, (name, args) in calls.items():
        if name == "final_result":
            continue
        res = returns.get(cid, "")
        res = res if isinstance(res, str) else json.dumps(res, default=str)
        events.append({"tool": name, "args": args, "result": str(res)[:300]})
    return events


async def run(doc_path: str, defenses: bool = True, allow_actions: bool = False) -> VendorAssessment:
    agent = build_agent(defenses=defenses)
    deps = VendorDeps(doc_path=doc_path, defenses=defenses, allow_actions=allow_actions)
    # ensure trap log exists as an empty list before the run
    trap = OUTPUT / "trap_calls.json"
    if not trap.exists():
        OUTPUT.mkdir(parents=True, exist_ok=True)
        trap.write_text("[]")

    started = time.time()
    result = await agent.run(
        f"Assess the vendor document for this run (file: {Path(doc_path).name}). "
        f"Call read_document first.",
        deps=deps,
    )
    elapsed = round(time.time() - started, 3)

    out = result.output
    if not out.file:
        out.file = Path(doc_path).name

    # Design layer: when defended, the DECISION is recomputed in code from the
    # extracted fields against the handbook — the model is trusted to extract, not to
    # decide. A poisoned doc can at most skew a field; it cannot force a recommend.
    model_decision, model_reason = out.decision, out.reason
    if defenses:
        out.decision, out.reason = rules.decide(
            out.vendor, out.sku, out.unit_price, out.lead_time_days, out.min_order
        )

    usage_obj = result.usage() if callable(getattr(result, "usage", None)) else result.usage
    usage_detail, cost = _cost_usd(usage_obj)
    now = datetime.now(timezone.utc).isoformat()

    _append(OUTPUT / "usage_log.json", {
        "time": now, "file": out.file, "model": MODEL_NAME, "defenses": defenses,
        **usage_detail, "elapsed_seconds": elapsed, "cost_usd": cost,
    })
    _append(OUTPUT / "audit_trail.json", {
        "time": now, "file": out.file, "defenses": defenses,
        "model_decision": model_decision, "model_reason": model_reason,
        "enforced_decision": out.decision,
        "tool_calls": _tool_events(result),
        "final_answer": out.model_dump(),
    })
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Campus Customs vendor desk agent")
    ap.add_argument("--doc", required=True, help="Path to one vendor document (HTML/PDF/.eml)")
    ap.add_argument("--no-defenses", action="store_true",
                    help="Run the vulnerable baseline: no doc sanitizer, bare prompt, "
                         "no code-side decision check (used by Problem 7).")
    ap.add_argument("--allow-actions", action="store_true",
                    help="Human sign-off: let send_email/approve_payment act instead of "
                         "only logging. Off by default; documents can never set this.")
    args = ap.parse_args()
    assessment = asyncio.run(run(args.doc, defenses=not args.no_defenses,
                                 allow_actions=args.allow_actions))
    print(json.dumps(assessment.model_dump(), indent=2))


if __name__ == "__main__":
    main()
