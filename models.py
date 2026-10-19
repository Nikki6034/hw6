"""Structured types for the Campus Customs vendor desk agent."""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


@dataclass
class VendorDeps:
    """Per-run dependencies. The agent reads only this one document (via the
    read_document tool), so it cannot be tricked into opening other files.

    `defenses` toggles the code-level document sanitizer (strip invisible text
    before the model sees it). `allow_actions` is the human sign-off gate for the
    send_email / approve_payment tools: a document can never flip it — only a human
    running the agent can — so a poisoned doc can never reach a live action.
    """

    doc_path: str
    defenses: bool = True
    allow_actions: bool = False


class VendorAssessment(BaseModel):
    """The agent's structured verdict on one vendor document."""

    file: str = Field(description="The document file name that was assessed.")
    vendor: str | None = Field(description="Vendor name, or null if the document does not state it.")
    sku: str | None = Field(description="Campus Customs SKU, or null if not stated.")
    unit_price: float | None = Field(description="Quoted unit price in USD, or null if not stated.")
    lead_time_days: int | None = Field(description="Lead time in days, or null if not stated.")
    min_order: int | None = Field(description="Minimum order in units, or null if not stated.")
    decision: Literal["recommend", "do_not_recommend"] = Field(
        description="recommend only if all four handbook checks pass; otherwise do_not_recommend."
    )
    reason: str = Field(
        description="One sentence naming the purchasing check that decided it."
    )
