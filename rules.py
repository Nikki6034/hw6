"""Design-level defense: the purchasing decision is recomputed IN CODE from the
extracted fields, not trusted from the model.

Even if a poisoned document talks the model into saying "recommend", the final
decision is produced here by `decide(...)` against the handbook's own vendor lists
and catalogue caps. The model is only trusted to *extract* fields; the *decision*
is deterministic Python. Vendor lists and caps are parsed from data/shop_handbook.md
so this never drifts from the handbook.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HANDBOOK = ROOT / "data" / "shop_handbook.md"

MAX_LEAD_DAYS = 21      # handbook section 4, check 3
MAX_MIN_ORDER = 600     # handbook section 4, check 4


def _norm(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def _section(text: str, start: str, end: str | None) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start)) if end else len(text)
    return text[i:j if j >= 0 else len(text)]


def _parse_handbook() -> dict:
    text = HANDBOOK.read_text(encoding="utf-8")

    # Section 5 — approved vendors (column 2 of the table).
    approved = set()
    for row in _section(text, "## 5", "## 6").splitlines():
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) >= 2 and cells[0] not in ("Code", "---") and "---" not in cells[0]:
            approved.add(_norm(cells[1]))

    # Section 6 — removed / pending vendors (column 1).
    removed = set()
    for row in _section(text, "## 6", "## 7").splitlines():
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) >= 2 and cells[0] not in ("Vendor", "---") and "---" not in cells[0]:
            removed.add(_norm(cells[0]))

    # Section 9 — catalogue: SKU -> max unit cost (column 5).
    caps = {}
    for row in _section(text, "## 9", None).splitlines():
        cells = [c.strip() for c in row.split("|")[1:-1]]
        if len(cells) >= 5 and re.match(r"CC-[A-Z]{2}-\d+", cells[0]):
            m = re.search(r"[\d.]+", cells[4])
            if m:
                caps[cells[0].upper()] = float(m.group(0))

    return {"approved": approved, "removed": removed, "caps": caps}


_HB = _parse_handbook()


def decide(vendor, sku, unit_price, lead_time_days, min_order) -> tuple[str, str]:
    """Return (decision, reason) from the extracted fields. recommend only if all
    four handbook checks pass; the reason names the first check that failed."""
    no = "do_not_recommend"
    v = _norm(vendor)

    # Check 1 — approved vendor (removed/pending always rejected).
    if not vendor:
        return no, "The approved-vendor check fails because no vendor name is stated."
    if v in _HB["removed"]:
        return no, f"The approved-vendor check fails because {vendor} is on the removed/pending vendor list."
    if v not in _HB["approved"]:
        return no, f"The approved-vendor check fails because {vendor} is not on the approved vendor list."

    # Check 2 — price at or below the catalogue max unit cost.
    if unit_price is None:
        return no, "The price check fails because the document does not state a unit price."
    cap = _HB["caps"].get((sku or "").upper())
    if cap is None:
        return no, f"The price check fails because SKU {sku} is not in the catalogue, so the cap cannot be verified."
    if unit_price > cap + 1e-9:
        return no, f"The price check fails because the unit price exceeds the catalogue max unit cost for {sku}."

    # Check 3 — lead time 21 days or less.
    if lead_time_days is None:
        return no, "The lead-time check fails because the document does not state a lead time."
    if lead_time_days > MAX_LEAD_DAYS:
        return no, f"The lead-time check fails because the {lead_time_days}-day lead time exceeds the {MAX_LEAD_DAYS}-day limit."

    # Check 4 — minimum order 600 units or less.
    if min_order is None:
        return no, "The minimum-order check fails because the document does not state a minimum order."
    if min_order > MAX_MIN_ORDER:
        return no, f"The minimum-order check fails because the {min_order}-unit minimum exceeds the {MAX_MIN_ORDER}-unit limit."

    return "recommend", "All four purchasing checks pass: approved vendor, price within cap, lead time within limit, and minimum order within limit."
