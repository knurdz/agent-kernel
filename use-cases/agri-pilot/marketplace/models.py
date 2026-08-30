"""SQLAlchemy models for marketplace (Phase 15 / App.md:18-39)."""

from __future__ import annotations

import enum
from datetime import date, datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from marketplace.database import Base


class UserRole(str, enum.Enum):
    farmer = "farmer"
    buyer = "buyer"
    admin = "admin"


class SubscriptionStatus(str, enum.Enum):
    none = "none"
    active = "active"
    expired = "expired"


class ListingStatus(str, enum.Enum):
    active = "active"
    sold = "sold"
    expired = "expired"
    cancelled = "cancelled"


class ConnectionStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    declined = "declined"
    completed = "completed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    role: Mapped[str] = mapped_column(Enum(UserRole, name="user_role", native_enum=False), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    subscription_status: Mapped[str] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status", native_enum=False),
        nullable=False,
        default=SubscriptionStatus.none.value,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    # Telegram linking (contact-share flow): chat_id of the linked bot chat.
    # BigInteger — Telegram IDs are not guaranteed to fit int32. Nullable until
    # the farmer shares their contact with the bot; unique so one chat maps to
    # one account and a claimed chat cannot be re-linked elsewhere.
    telegram_chat_id: Mapped[int | None] = mapped_column(BigInteger, unique=True, nullable=True, index=True)

    farmer_profile: Mapped[FarmerProfile | None] = relationship(
        "FarmerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    buyer_profile: Mapped[BuyerProfile | None] = relationship(
        "BuyerProfile", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    listings: Mapped[list[Listing]] = relationship("Listing", back_populates="farmer", cascade="all, delete-orphan")
    plants: Mapped[list[Plant]] = relationship("Plant", back_populates="farmer", cascade="all, delete-orphan")
    devices: Mapped[list[UserDevice]] = relationship("UserDevice", back_populates="user", cascade="all, delete-orphan")
    notification_preferences: Mapped[NotificationPreference | None] = relationship(
        "NotificationPreference", back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


class FarmerProfile(Base):
    __tablename__ = "farmer_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)
    preferred_language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="farmer_profile")


class BuyerProfile(Base):
    __tablename__ = "buyer_profiles"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    business_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location: Mapped[str | None] = mapped_column(String(120), nullable=True)
    district: Mapped[str | None] = mapped_column(String(120), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="buyer_profile")


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("quantity_kg > 0", name="ck_listing_quantity_positive"),
        CheckConstraint("price_per_kg IS NULL OR price_per_kg >= 0", name="ck_listing_price_non_negative"),
        Index("ix_listings_status_crop", "status", "crop"),
        Index("ix_listings_farmer_id", "farmer_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    crop: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    price_per_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(
        Enum(ListingStatus, name="listing_status", native_enum=False),
        nullable=False,
        default=ListingStatus.active.value,
    )
    plant_id: Mapped[int | None] = mapped_column(
        ForeignKey("plants.id", ondelete="SET NULL", use_alter=True),
        unique=True,
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    farmer: Mapped[User] = relationship("User", back_populates="listings")


class Plant(Base):
    __tablename__ = "plants"
    __table_args__ = (
        Index("ix_plants_farmer_id", "farmer_id"),
        Index("ix_plants_listing_id", "listing_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    crop: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    planted_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    listing_id: Mapped[int | None] = mapped_column(
        ForeignKey("listings.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    farmer: Mapped[User] = relationship("User", back_populates="plants")
    observations: Mapped[list[PlantObservation]] = relationship(
        "PlantObservation", back_populates="plant", cascade="all, delete-orphan", order_by="PlantObservation.captured_at"
    )


class PlantObservation(Base):
    __tablename__ = "plant_observations"
    __table_args__ = (Index("ix_plant_observations_plant_id", "plant_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id", ondelete="CASCADE"), nullable=False)
    photo_path: Mapped[str] = mapped_column(String(512), nullable=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    quality_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    quality_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    top_label: Mapped[str | None] = mapped_column(String(200), nullable=True)
    top_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    predictions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    advice_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="tracking")

    plant: Mapped[Plant] = relationship("Plant", back_populates="observations")


class ConnectionRequest(Base):
    __tablename__ = "connection_requests"
    __table_args__ = (
        Index("ix_connection_listing_id", "listing_id"),
        Index("ix_connection_buyer_id", "buyer_id"),
        # DB-level backstop for the service-layer pending-uniqueness guard
        # (service.create_connection_request). Declared for BOTH dialects so
        # the in-memory SQLite test schema matches the Postgres runtime schema.
        Index(
            "ux_connection_requests_pending",
            "listing_id",
            "buyer_id",
            unique=True,
            sqlite_where=text("status = 'pending'"),
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), nullable=False)
    buyer_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(
        Enum(ConnectionStatus, name="connection_status", native_enum=False),
        nullable=False,
        default=ConnectionStatus.pending.value,
    )
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )


class TelegramLinkToken(Base):
    __tablename__ = "telegram_link_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)


class UserDevice(Base):
    __tablename__ = "user_devices"
    __table_args__ = (Index("ix_user_devices_user_active", "user_id", "active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    fcm_token: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False, default="android")
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="devices")


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    push_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    whatsapp_enabled: Mapped[bool] = mapped_column(nullable=False, default=True)
    connection_updates: Mapped[bool] = mapped_column(nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False
    )

    user: Mapped[User] = relationship("User", back_populates="notification_preferences")
