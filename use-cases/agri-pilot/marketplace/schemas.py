"""Pydantic schemas for marketplace (Phase 15)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class SignupRequest(BaseModel):
    role: Literal["farmer", "buyer"]
    phone_number: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)
    location: Optional[str] = Field(default=None, max_length=120)
    district: Optional[str] = Field(default=None, max_length=120)
    preferred_language: Optional[str] = Field(default=None, max_length=20)
    business_name: Optional[str] = Field(default=None, max_length=120)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        # Normalize: strip spaces/dashes like auth.normalize_phone, but keep validation here too.
        norm = re.sub(r"[\s\-\(\)]", "", v.strip())
        if not PHONE_RE.match(norm):
            raise ValueError("phone_number must be E.164, e.g. +94770000001")
        return norm


class LoginRequest(BaseModel):
    phone_number: str
    password: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        norm = re.sub(r"[\s\-\(\)]", "", v.strip())
        if not PHONE_RE.match(norm):
            raise ValueError("phone_number must be E.164")
        return norm


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileOut(BaseModel):
    location: Optional[str] = None
    district: Optional[str] = None
    preferred_language: Optional[str] = None
    business_name: Optional[str] = None


class MeResponse(BaseModel):
    id: int
    phone_number: str
    role: str
    subscription_status: str
    name: str
    created_at: datetime
    profile: Optional[ProfileOut] = None


class ListingCreate(BaseModel):
    crop: str = Field(min_length=1, max_length=80)
    quantity_kg: float = Field(gt=0)
    price_per_kg: Optional[float] = Field(default=None, ge=0)
    harvest_date: Optional[date] = None

    @field_validator("crop")
    @classmethod
    def normalize_crop(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("crop must be non-empty")
        return v.lower()


class ListingUpdate(BaseModel):
    crop: Optional[str] = Field(default=None, min_length=1, max_length=80)
    quantity_kg: Optional[float] = Field(default=None, gt=0)
    price_per_kg: Optional[float] = Field(default=None, ge=0)
    harvest_date: Optional[date] = None
    status: Optional[Literal["active", "sold", "expired", "cancelled"]] = None

    @field_validator("crop")
    @classmethod
    def normalize_crop(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            raise ValueError("crop must be non-empty")
        return v.lower()


class ListingResponse(BaseModel):
    id: int
    farmer_id: int
    crop: str
    quantity_kg: float
    price_per_kg: Optional[float] = None
    harvest_date: Optional[date] = None
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PaginatedListings(BaseModel):
    items: list[ListingResponse]
    total: int
    limit: int
    offset: int


class ConnectionCreate(BaseModel):
    message: Optional[str] = Field(default=None, max_length=500)


class ConnectionResponse(BaseModel):
    id: int
    listing_id: int
    buyer_id: int
    status: str
    message: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
