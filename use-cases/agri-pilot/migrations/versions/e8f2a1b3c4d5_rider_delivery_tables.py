"""Rider delivery: orders, deliveries, rider profiles, geo fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e8f2a1b3c4d5"
down_revision: Union[str, None] = "d7a1e4f9b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("reserved_quantity_kg", sa.Float(), nullable=False, server_default="0"))
    op.create_check_constraint("ck_listing_reserved_non_negative", "listings", "reserved_quantity_kg >= 0")

    op.add_column("farmer_profiles", sa.Column("address_label", sa.String(length=200), nullable=True))
    op.add_column("farmer_profiles", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("farmer_profiles", sa.Column("longitude", sa.Float(), nullable=True))

    op.add_column("buyer_profiles", sa.Column("address_label", sa.String(length=200), nullable=True))
    op.add_column("buyer_profiles", sa.Column("latitude", sa.Float(), nullable=True))
    op.add_column("buyer_profiles", sa.Column("longitude", sa.Float(), nullable=True))

    op.add_column(
        "notification_preferences",
        sa.Column("delivery_updates", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

    op.create_table(
        "rider_profiles",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("has_vehicle", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_online", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("address_label", sa.String(length=200), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("last_location_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("connection_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("buyer_id", sa.Integer(), nullable=False),
        sa.Column("farmer_id", sa.Integer(), nullable=False),
        sa.Column("crop", sa.String(length=80), nullable=False),
        sa.Column("quantity_kg", sa.Float(), nullable=False),
        sa.Column("price_per_kg", sa.Float(), nullable=True),
        sa.Column("fulfillment_mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("pickup_address_label", sa.String(length=200), nullable=True),
        sa.Column("pickup_latitude", sa.Float(), nullable=True),
        sa.Column("pickup_longitude", sa.Float(), nullable=True),
        sa.Column("delivery_address_label", sa.String(length=200), nullable=True),
        sa.Column("delivery_latitude", sa.Float(), nullable=True),
        sa.Column("delivery_longitude", sa.Float(), nullable=True),
        sa.Column("handoff_pin_hash", sa.String(length=128), nullable=True),
        sa.Column("cancellation_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity_kg > 0", name="ck_order_quantity_positive"),
        sa.CheckConstraint("price_per_kg IS NULL OR price_per_kg >= 0", name="ck_order_price_non_negative"),
        sa.ForeignKeyConstraint(["buyer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["connection_requests.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["farmer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("connection_id"),
    )
    op.create_index("ix_orders_buyer_id", "orders", ["buyer_id"])
    op.create_index("ix_orders_farmer_id", "orders", ["farmer_id"])
    op.create_index("ix_orders_status", "orders", ["status"])

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("rider_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("route_distance_m", sa.Integer(), nullable=True),
        sa.Column("route_duration_s", sa.Integer(), nullable=True),
        sa.Column("route_polyline", sa.Text(), nullable=True),
        sa.Column("rider_latitude", sa.Float(), nullable=True),
        sa.Column("rider_longitude", sa.Float(), nullable=True),
        sa.Column("rider_heading", sa.Float(), nullable=True),
        sa.Column("rider_accuracy_m", sa.Float(), nullable=True),
        sa.Column("rider_location_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("picked_up_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rider_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_id"),
    )
    op.create_index("ix_deliveries_rider_id", "deliveries", ["rider_id"])
    op.create_index("ix_deliveries_status", "deliveries", ["status"])

    op.create_table(
        "rider_job_decisions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("rider_id", sa.Integer(), nullable=False),
        sa.Column("decision", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["rider_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ux_rider_job_decisions_order_rider", "rider_job_decisions", ["order_id", "rider_id"], unique=True)

    op.create_table(
        "order_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_role", sa.String(length=20), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_events_order_id", "order_events", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_events_order_id", table_name="order_events")
    op.drop_table("order_events")
    op.drop_index("ux_rider_job_decisions_order_rider", table_name="rider_job_decisions")
    op.drop_table("rider_job_decisions")
    op.drop_index("ix_deliveries_status", table_name="deliveries")
    op.drop_index("ix_deliveries_rider_id", table_name="deliveries")
    op.drop_table("deliveries")
    op.drop_index("ix_orders_status", table_name="orders")
    op.drop_index("ix_orders_farmer_id", table_name="orders")
    op.drop_index("ix_orders_buyer_id", table_name="orders")
    op.drop_table("orders")
    op.drop_table("rider_profiles")
    op.drop_column("notification_preferences", "delivery_updates")
    op.drop_column("buyer_profiles", "longitude")
    op.drop_column("buyer_profiles", "latitude")
    op.drop_column("buyer_profiles", "address_label")
    op.drop_column("farmer_profiles", "longitude")
    op.drop_column("farmer_profiles", "latitude")
    op.drop_column("farmer_profiles", "address_label")
    op.drop_constraint("ck_listing_reserved_non_negative", "listings", type_="check")
    op.drop_column("listings", "reserved_quantity_kg")
