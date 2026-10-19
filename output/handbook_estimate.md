# Handbook token & cost estimate (Problem 2)

The vendor-desk agent sends the full shop handbook to the model on **every** call,
so its token cost is paid on every document. This estimates that cost before the
real runs in Problem 4.

## Token count

- **Handbook tokens: 10,058** (`data/shop_handbook.md`, 28,903 characters).
- **How it was counted:** `tiktoken` with the **`o200k_base`** encoding — the
  tokenizer OpenAI uses for its current models (gpt-4o and newer), the best proxy
  for `gpt-6-luna`. For reference, `cl100k_base` (older GPT-3.5/4 encoding) gives
  10,184 tokens — within ~1.3%, so the count is stable across encodings.

## gpt-6-luna prices (`data/prices.json`, per 1M tokens)

| Rate | $/1M tokens |
|---|---|
| input (uncached) | $0.1 |
| cached input (read) | $0.01 |
| cache write (first time) | $0.125 |
| output | 0.5 (not used — handbook is input only) |

Cost of X tokens at rate R = `X / 1,000,000 × R`.

## Cost of the handbook as input

### One call
- **Uncached:** 10,058 / 1,000,000 × $0.1 = **$0.001006** (~$0.1006¢)
- **Cached read:** 10,058 / 1,000,000 × $0.01 = **$0.000101**
- **Cache write (one-time):** 10,058 / 1,000,000 × $0.125 = **$0.001257**

### 1,000 calls
- **Without caching** (every call pays full input):
  1,000 × $0.001006 = **$1.0058**
- **With caching** (write the handbook to cache once, then read it cached on the
  other 999 calls):
  $0.001257 (1 write) + 999 × $0.000101 (cached reads)
  = **$0.1017**
- **Savings from caching over 1,000 calls:** $1.0058 − $0.1017
  = **$0.9041** (~90% cheaper).

Lower-bound note: if every call were a pure cached read (ignoring the one-time
write), 1,000 calls would be 1,000 × $0.000101 = $0.1006.

## What this predicts for Problem 4

Per document processed, the handbook alone adds **~$0.001006 uncached** or
**~$0.000101 cached** in input cost (before the document's own tokens and
the model's output). Across the 12 practice + 10 exam docs, caching the handbook
should cut the handbook portion of the bill by ~90%. These figures will be
compared against the measured token usage and cost in Problem 4.
