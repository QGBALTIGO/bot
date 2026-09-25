"""Typed contracts for the existing API. Unknown IDs/identity fields are rejected."""

from __future__ import annotations
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime

PositiveId = Annotated[int, Field(strict=True, ge=1, le=2**53 - 1)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=20)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Toggle(Contract):
    enabled: bool = Field(strict=True)


class Preferences(Contract):
    discoverable: bool | None = Field(default=None, strict=True)
    share_inline: bool | None = Field(default=None, strict=True)
    preserve_last: bool | None = Field(default=None, strict=True)


class Wish(Contract):
    ids: list[PositiveId] = Field(min_length=1, max_length=1000)
    enabled: bool = Field(default=True, strict=True)


class Item(Contract):
    character_id: PositiveId
    quantity: Quantity


class Selection(Contract):
    items: list[Item] = Field(min_length=1, max_length=20)


class Recycle(Selection):
    request_id: UUID


class Craft(Contract):
    recipe: str = Field(max_length=60)
    request_id: UUID


class Equip(Contract):
    cosmetic_id: str | None = Field(default=None, max_length=80)


class Listing(Item):
    price: int = Field(strict=True, ge=1, le=100000)
    kind: Literal["fixed", "auction"] = "fixed"
    hours: int = Field(default=24, strict=True, ge=1, le=72)
    request_id: UUID


class MarketAction(Contract):
    action: Literal["buy", "bid", "cancel"]
    version: int = Field(strict=True, ge=1, le=1000000)
    amount: int = Field(default=0, strict=True, ge=0, le=100000)
    request_id: UUID


class EventSpec(Contract):
    title: str = Field(min_length=3, max_length=80)
    description: str = Field(min_length=10, max_length=1000)
    character_ids: list[PositiveId] = Field(min_length=1, max_length=100)
    goal: int = Field(strict=True, ge=1, le=100000)
    daily_limit: int = Field(default=1, strict=True, ge=1, le=5)
    reward_label: str = Field(min_length=3, max_length=60)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    request_id: UUID


class Contribution(Contract):
    character_id: PositiveId
    request_id: UUID


class TradeRevision(Contract):
    expected_revision: int = Field(strict=True, ge=1, le=1000000)
    character_id: PositiveId


class TradeRespond(Contract):
    action: Literal["accept", "reject"]
    expected_revision: int | None = Field(default=None, strict=True, ge=1, le=1000000)
