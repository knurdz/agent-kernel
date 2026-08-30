"""Pydantic schemas for marketplace (Phase 15)."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from marketplace.auth import normalize_phone

PHONE_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class SignupRequest(BaseModel):
    role: Literal["farmer", "buyer", "rider"]
    phone_number: str
    password: str = Field(min_length=8)
    name: str = Field(min_length=1, max_length=120)
    location: Optional[str] = Field(default=None, max_length=120)
    district: Optional[str] = Field(default=None, max_length=120)
    preferred_language: Optional[str] = Field(default=None, max_length=20)
    business_name: Optional[str] = Field(default=None, max_length=120)
    contact_phone_number: Optional[str] = Field(default=None, max_length=20)
    has_vehicle: Optional[bool] = Field(default=None, description="Required for rider signup")

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except ValueError as exc:
            raise ValueError("phone_number must be E.164, e.g. +94770000001") from exc

    @field_validator("contact_phone_number")
    @classmethod
    def validate_contact_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        stripped = re.sub(r"[\s\-\(\)]", "", v.strip())
        if not stripped:
            return None
        try:
            return normalize_phone(v)
        except ValueError as exc:
            raise ValueError("contact_phone_number must be E.164, e.g. +94770000002") from exc


class LoginRequest(BaseModel):
    phone_number: str
    password: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            return normalize_phone(v)
        except ValueError as exc:
            raise ValueError("phone_number must be E.164") from exc


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ProfileOut(BaseModel):
    location: Optional[str] = None
    district: Optional[str] = None
    preferred_language: Optional[str] = None
    business_name: Optional[str] = None
    contact_phone: Optional[str] = None
    address_label: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    has_vehicle: Optional[bool] = None
    is_online: Optional[bool] = None


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
    plant_id: Optional[int] = None
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


class BuyerPublic(BaseModel):
    id: int
    name: str
    district: Optional[str] = None
    business_name: Optional[str] = None


class FarmerPublic(BaseModel):
    id: int
    name: str
    district: Optional[str] = None


class ConnectionWithListing(BaseModel):
    id: int
    listing_id: int
    buyer_id: int
    status: str
    message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    listing: ListingResponse

    model_config = {"from_attributes": True}


class ConnectionWithListingAndBuyer(BaseModel):
    id: int
    listing_id: int
    buyer_id: int
    status: str
    message: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    listing: ListingResponse
    buyer: BuyerPublic

    model_config = {"from_attributes": True}


class MatchItem(BaseModel):
    listing: ListingResponse
    score: int
    reason: str


class MatchResponse(BaseModel):
    items: list[MatchItem]
    query: dict


class ContactResponse(BaseModel):
    phone_number: str
    listing_id: int
    connection_id: int
    status: str


class ProfileUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    location: Optional[str] = Field(default=None, max_length=120)
    district: Optional[str] = Field(default=None, max_length=120)
    preferred_language: Optional[str] = Field(default=None, max_length=20)
    business_name: Optional[str] = Field(default=None, max_length=120)
    contact_phone_number: Optional[str] = Field(default=None, max_length=20)
    address_label: Optional[str] = Field(default=None, max_length=200)
    latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    has_vehicle: Optional[bool] = None

    @field_validator("contact_phone_number")
    @classmethod
    def validate_contact_phone(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        norm = re.sub(r"[\s\-\(\)]", "", v.strip())
        if not norm:
            return None
        if not PHONE_RE.match(norm):
            raise ValueError("contact_phone_number must be E.164")
        return norm


class TelegramChannelStatus(BaseModel):
    linked: bool
    eligible: bool


class WhatsAppChannelStatus(BaseModel):
    eligible: bool
    linked_by_phone: bool


class ChannelsResponse(BaseModel):
    telegram: TelegramChannelStatus
    whatsapp: WhatsAppChannelStatus


class TelegramLinkTokenResponse(BaseModel):
    token: str
    deep_link_url: str
    expires_in_minutes: int


class PublicConfigResponse(BaseModel):
    whatsapp_display_number: Optional[str] = None
    whatsapp_wa_me: Optional[str] = None
    telegram_bot_username: Optional[str] = None
    telegram_deep_link_base: Optional[str] = None
    signup_url: Optional[str] = None


class DeviceRegisterRequest(BaseModel):
    fcm_token: str = Field(min_length=10, max_length=512)
    platform: str = Field(default="android", max_length=32)


class DeviceResponse(BaseModel):
    id: int
    platform: str
    active: bool

    model_config = {"from_attributes": True}


class NotificationPreferencesUpdate(BaseModel):
    push_enabled: Optional[bool] = None
    whatsapp_enabled: Optional[bool] = None
    connection_updates: Optional[bool] = None


class NotificationPreferencesResponse(BaseModel):
    push_enabled: bool
    whatsapp_enabled: bool
    connection_updates: bool

    model_config = {"from_attributes": True}


class PlantCreate(BaseModel):
    crop: str = Field(min_length=1, max_length=80)
    name: Optional[str] = Field(default=None, max_length=120)
    planted_on: Optional[date] = None
    listing_id: Optional[int] = None

    @field_validator("crop")
    @classmethod
    def normalize_crop(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("crop must be non-empty")
        return v.lower()


class PredictionOut(BaseModel):
    label: str
    confidence: float


class ScanResult(BaseModel):
    quality_ok: bool
    quality_reason: Optional[str] = None
    predictions: list[PredictionOut] = Field(default_factory=list)
    top_label: Optional[str] = None
    top_confidence: Optional[float] = None
    confident: bool = False
    advice_summary: Optional[str] = None


class PlantObservationOut(BaseModel):
    id: int
    plant_id: int
    captured_at: datetime
    quality_ok: bool
    quality_reason: Optional[str] = None
    top_label: Optional[str] = None
    top_confidence: Optional[float] = None
    predictions: Optional[list[PredictionOut]] = None
    advice_summary: Optional[str] = None
    source: str
    photo_url: Optional[str] = None

    model_config = {"from_attributes": True}


class PlantInsights(BaseModel):
    crop: str
    observation_count: int
    first_observation_date: Optional[str] = None
    last_observation_date: Optional[str] = None
    latest_label: Optional[str] = None
    latest_confidence: Optional[float] = None
    timeline: list[dict] = Field(default_factory=list)
    health_series: list[dict] = Field(default_factory=list)
    trend: str
    crop_care: Optional[dict] = None
    growth_progress: Optional[float] = None


class PlantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=120)
    planted_on: Optional[date] = None
    clear_planted_on: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        trimmed = v.strip()
        return trimmed or None


class PlantSummary(BaseModel):
    id: int
    crop: str
    name: str
    planted_on: Optional[date] = None
    listing_id: Optional[int] = None
    observation_count: int = 0
    latest_label: Optional[str] = None
    trend: str = "unknown"
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PlantDetail(BaseModel):
    id: int
    crop: str
    name: str
    planted_on: Optional[date] = None
    listing_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    observations: list[PlantObservationOut]
    insights: PlantInsights


class PaginatedPlants(BaseModel):
    items: list[PlantSummary]
    total: int
    limit: int
    offset: int


class ListingInsights(BaseModel):
    listing_id: int
    plant_id: int
    crop: str
    observation_count: int
    first_observation_date: Optional[str] = None
    last_observation_date: Optional[str] = None
    latest_label: Optional[str] = None
    latest_confidence: Optional[float] = None
    timeline: list[dict] = Field(default_factory=list)
    trend: str


class OrderCreate(BaseModel):
    connection_id: int
    quantity_kg: float = Field(gt=0)
    fulfillment_mode: Literal["pickup", "delivery"]
    delivery_address_label: Optional[str] = Field(default=None, max_length=200)
    delivery_latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    delivery_longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class OrderCreateResponse(BaseModel):
    order: "OrderResponse"
    handoff_pin: str


class FarmerConfirmOrder(BaseModel):
    confirmed_quantity_kg: float = Field(gt=0)
    pickup_address_label: Optional[str] = Field(default=None, max_length=200)
    pickup_latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    pickup_longitude: Optional[float] = Field(default=None, ge=-180, le=180)


class OrderReject(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class HandoffConfirm(BaseModel):
    pin: str = Field(min_length=4, max_length=6)


class OrderResponse(BaseModel):
    id: int
    connection_id: int
    listing_id: int
    buyer_id: int
    farmer_id: int
    crop: str
    quantity_kg: float
    price_per_kg: Optional[float] = None
    fulfillment_mode: str
    status: str
    pickup_address_label: Optional[str] = None
    pickup_latitude: Optional[float] = None
    pickup_longitude: Optional[float] = None
    delivery_address_label: Optional[str] = None
    delivery_latitude: Optional[float] = None
    delivery_longitude: Optional[float] = None
    cancellation_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    delivery_id: Optional[int] = None
    delivery_status: Optional[str] = None

    model_config = {"from_attributes": True}


class RiderJobOut(BaseModel):
    order_id: int
    delivery_id: int
    crop: str
    quantity_kg: float
    pickup_district_area: str
    delivery_district_area: str
    distance_to_pickup_km: float
    route_distance_m: int
    route_duration_s: int
    maps_available: bool


class RiderLocationUpdate(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    heading: Optional[float] = None
    accuracy_m: Optional[float] = None


class RiderOnlineUpdate(BaseModel):
    online: bool


class DeliveryStatusUpdate(BaseModel):
    status: Literal["en_route_pickup", "arrived_pickup", "picked_up", "in_transit", "delivered"]


class TrackingResponse(BaseModel):
    order_id: int
    status: str
    fulfillment_mode: str
    quantity_kg: float
    crop: str
    pickup: dict
    delivery: dict
    rider: dict
    delivery_status: Optional[str] = None
    events: list[dict] = Field(default_factory=list)
