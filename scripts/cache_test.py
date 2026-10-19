"""Problem 4 — caching A/B test across all 12 practice docs.

Two setups:
  - "cached": the handbook prefix is identical every call, so the model's prompt
    cache is reused (cache_read_tokens > 0).
  - "no_cache": a unique nonce is prepended to the instructions each call, so the
    cacheable prefix differs every time and the cache can't be reused.

Records every run's API-reported token counts and the USD cost (from prices.json)
to output/cache_test.json.
"""

import asyncio
import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from openai import AsyncOpenAI  # noqa: E402
from pydantic_ai import Agent  # noqa: E402
from pydantic_ai.models.openai import OpenAIResponsesModel  # noqa: E402
from pydantic_ai.providers.openai import OpenAIProvider  # noqa: E402

import agent as agent_mod  # reuse config + key  # noqa: E402
from models import VendorAssessment, VendorDeps  # noqa: E402
from tools import approve_payment, read_document, send_email  # noqa: E402

PRICES = json.load(open(ROOT / "data" / "prices.json"))["gpt-6-luna"]
BASE_INSTRUCTIONS = (
    (ROOT / "prompts" / "prompt.md").read_text(encoding="utf-8")
    + "\n\n# SHOP HANDBOOK\n\n"
    + (ROOT / "data" / "shop_handbook.md").read_text(encoding="utf-8")
)
DOCS = sorted((ROOT / "data" / "practice_docs").glob("*"))


def _model() -> OpenAIResponsesModel:
    key = agent_mod._api_key()
    client = AsyncOpenAI(
        api_key=key, base_url=agent_mod.PORTKEY_BASE_URL,
        default_headers={"x-portkey-api-key": key, "x-portkey-provider": "openai"},
    )
    return OpenAIResponsesModel(agent_mod.MODEL_NAME, provider=OpenAIProvider(openai_client=client))


def _make_agent(instructions) -> Agent:
    # instructions may be a static string (cached setup) or a callable that is
    # re-evaluated on EVERY model request (no_cache setup). A callable returning a
    # fresh uuid prefix each request means even the two requests inside one run have
    # different prefixes, so the prompt cache is never reused -> cache_read == 0.
    return Agent(
        _model(), deps_type=VendorDeps, output_type=VendorAssessment,
        instructions=instructions, tools=[read_document, send_email, approve_payment],
    )


def _dynamic_instructions() -> str:
    """Fresh unique prefix every model request -> defeats caching entirely."""
    return f"Run token: {uuid.uuid4()}\n\n" + BASE_INSTRUCTIONS


def _cost(u) -> float:
    inp = u.input_tokens or 0
    cr = getattr(u, "cache_read_tokens", 0) or 0
    cw = getattr(u, "cache_write_tokens", 0) or 0
    out = u.output_tokens or 0
    uncached = max(inp - cr - cw, 0)
    return (
        uncached / 1e6 * PRICES["input_per_1m"]
        + cr / 1e6 * PRICES["cached_input_per_1m"]
        + cw / 1e6 * PRICES["cache_write_per_1m"]
        + out / 1e6 * PRICES["output_per_1m"]
    )


async def one_run(instructions: str, doc: Path, setup: str) -> dict:
    ag = _make_agent(instructions)
    r = await ag.run("Assess the vendor document. Call read_document first.",
                     deps=VendorDeps(doc_path=str(doc)))
    u = r.usage
    return {
        "setup": setup, "doc": doc.name,
        "input_tokens": u.input_tokens,
        "cache_read_tokens": getattr(u, "cache_read_tokens", 0),
        "cache_write_tokens": getattr(u, "cache_write_tokens", 0),
        "output_tokens": u.output_tokens,
        "total_tokens": u.total_tokens,
        "requests": u.requests,
        "cost_usd": round(_cost(u), 6),
    }


async def main() -> None:
    records = []
    # no_cache first: a callable regenerates a unique prefix on EVERY model request
    # (both requests inside a run), so the cache is never reused -> cache_read == 0.
    for doc in DOCS:
        records.append(await one_run(_dynamic_instructions, doc, "no_cache"))
        print("no_cache ", doc.name, records[-1]["cost_usd"], "cache_read", records[-1]["cache_read_tokens"])
    # cached: identical prefix every call -> cache is reused
    for doc in DOCS:
        records.append(await one_run(BASE_INSTRUCTIONS, doc, "cached"))
        print("cached   ", doc.name, records[-1]["cost_usd"], "cache_read", records[-1]["cache_read_tokens"])

    (ROOT / "output").mkdir(exist_ok=True)
    (ROOT / "output" / "cache_test.json").write_text(json.dumps(records, indent=2))
    print("saved output/cache_test.json")


if __name__ == "__main__":
    asyncio.run(main())
