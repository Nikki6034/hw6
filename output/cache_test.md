# Problem 4 — Caching A/B test (handbook cached vs not)

I ran the Problem 3 agent on **all 12 practice docs** in two setups and recorded the
**API-reported** token counts + USD cost (from `data/prices.json`) for every run to
[`output/cache_test.json`](cache_test.json). Script: [`scripts/cache_test.py`](../scripts/cache_test.py).

## The two setups

- **`cached`** — the instructions (my prompt + the full shop handbook) are byte-for-byte
  identical on every call, so the model's prompt cache is reused.
- **`no_cache`** — a unique `Run token: <uuid>` is prepended to the instructions on
  **every model request**, so the cacheable prefix differs every time and the cache can
  never be reused.

> **Caching is confirmed by the API's own numbers.** Every `no_cache` run reports
> `cache_read_tokens = 0` (the whole point of the setup). Every `cached` run reports
> `cache_read_tokens = 21,618`. That is the only difference that matters, and the agent
> did not change — only the prefix did.

### Why the nonce has to regenerate per *request*, not per *doc*

The agent makes **2 model requests per doc** (one to call `read_document`, one to answer),
so the handbook is sent to the model **twice per doc**. My first attempt put one uuid on
the agent for the whole run — the 2nd request then reused the cache the 1st request wrote,
and `no_cache` runs wrongly showed `cache_read ≈ 10,844`. Making the instructions a
**callable** that mints a fresh uuid on every request fixed it → `cache_read = 0` on all 12.

## Prices used (`data/prices.json`, gpt-6-luna, per 1M tokens)

| input | cached input (read) | cache write | output |
|------:|--------------------:|------------:|-------:|
| $0.10 | $0.01 (10× cheaper) | $0.125 (1.25× **premium**) | $0.50 |

Cost per run = `uncached_input × $0.10 + cache_read × $0.01 + cache_write × $0.125 + output × $0.50`
(all ÷ 1e6), where `uncached_input = input − cache_read − cache_write`.

## Per-doc cost (USD)

| Doc | no_cache | cached | cache_read (nc / cached) |
|-----|---------:|-------:|-------------------------:|
| p01_bluehen_quote.html       | 0.002874 | 0.000387 | 0 / 21,618 |
| p02_elmcity_quote.html       | 0.002853 | 0.000406 | 0 / 21,618 |
| p03_ivyprint_catalog.html    | 0.002930 | 0.000439 | 0 / 21,618 |
| p04_harborstitch_quote.html  | 0.002881 | 0.000402 | 0 / 21,618 |
| p05_maplemills_quote.pdf     | 0.002886 | 0.000386 | 0 / 21,618 |
| p06_qtextile_quote.pdf       | 0.002883 | 0.000382 | 0 / 21,618 |
| p07_longwharf_quote.pdf      | 0.002912 | 0.000429 | 0 / 21,618 |
| p08_chapelst_email.eml       | 0.002872 | 0.000386 | 0 / 21,618 |
| p09_westville_email.eml      | 0.002903 | 0.000449 | 0 / 21,618 |
| p10_eastrock_email.eml       | 0.002919 | 0.000411 | 0 / 21,618 |
| p11_yorkst_quote.html        | 0.002851 | 0.000381 | 0 / 21,618 |
| p12_bluehen_quote.pdf        | 0.002955 | 0.000397 | 0 / 21,618 |

## Totals (12 docs)

| Setup | Total cost | Avg / doc | Cost / 1k docs |
|-------|-----------:|----------:|---------------:|
| no_cache | **$0.034719** | $0.002893 | $2.893 |
| cached   | **$0.004855** | $0.000405 | $0.405 |
| **Savings** | **$0.029864** | — | **86.0%** |

Caching cut the bill by **86.0%** across the 12 docs.

## Comparison with the Problem 2 estimate

Problem 2 measured the handbook at **10,058 tokens** and estimated, for the handbook text alone:

| | per call | per 1k calls |
|---|---:|---:|
| P2 uncached | $0.001006 | $1.006 |
| P2 cached | $0.000101 | $0.102 |
| P2 predicted savings | ~90% | |

The real runs cost **more** than the P2 estimate, for two concrete reasons:

1. **The handbook is billed ~2× per doc.** P2 modeled a single handbook send; the agent
   actually makes 2 model requests per doc (tool-call round-trip), resending the whole
   handbook each time. This shows up directly: cached `cache_read = 21,618 ≈ 2 × 10,058`.
2. **`no_cache` pays the 1.25× write premium.** Because the prefix is unique every request,
   the API *writes* a fresh cache each time (~21,837 write tokens/doc) at $0.125/1M and never
   reads it back. So defeating the cache costs **more** than naive input pricing, not less.

Reconciliation (per doc):
- no_cache ≈ 2 × 10,058 × $0.125/1M = **$0.00251** handbook writes + prompt/doc/output ≈ **$0.00289** ✔
- cached ≈ 21,618 × $0.01/1M = **$0.000216** reads + ~287 output × $0.50/1M ≈ **$0.000405** ✔

Measured savings **86.0%** vs P2's **~90%**: the gap is the **output tokens**, which are
identical in both setups and can never be cached, so they dilute the percentage once the
input side is made cheap.

## Projection — 1kk docs/day over 30 days

Reading **1kk = 1,000,000 docs/day**, so **30 days = 30,000,000 docs**. Using the measured
per-doc averages:

| Setup | Per day (1,000,000 docs) | 30 days (30,000,000 docs) |
|-------|-------------------------:|--------------------------:|
| no_cache | $2,893.25 | **$86,797.50** |
| cached   | $404.58   | **$12,137.50** |
| **Savings** | $2,488.67 | **$74,660.00** |

Caching saves roughly **$74.7k over the month** at this volume.

## Results & surprises

- **Caching works and the API proves it:** `cache_read` is exactly 0 in every no_cache run
  and a steady 21,618 in every cached run — no guessing, the provider reports it.
- **Surprise 1 — "no cache" is worse than plain pricing.** With a per-call write premium,
  forcing unique prefixes actively *raises* cost (every call writes a cache nobody reads).
  The real baseline for "no caching benefit" is therefore the write-premium cost, not the
  plain input cost P2 used.
- **Surprise 2 — the handbook is paid for twice per doc.** The tool-call round-trip means
  two model requests, each carrying the full handbook. This is the single biggest reason
  real cost is ~2.9× the P2 single-send estimate, and it's the strongest argument for
  caching here: a big, fixed, repeated prefix is the ideal thing to cache.
- **Steady-state cached cost is tiny and flat** (~$0.0004/doc regardless of doc), because
  the only per-doc variation is the small document body + the output tokens.
