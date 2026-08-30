"""Plant tracking tables and listing plant link."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d7a1e4f9b2c3"
down_revision: Union[str, None] = "c3f9a2b1d8e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plants",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("farmer_id", sa.Integer(), nullable=False),
        sa.Column("crop", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("planted_on", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["farmer_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plants_farmer_id", "plants", ["farmer_id"])

    op.add_column("listings", sa.Column("plant_id", sa.Integer(), nullable=True))
    op.create_index("ix_listings_plant_id", "listings", ["plant_id"], unique=True)
    op.create_foreign_key("fk_listings_plant_id", "listings", "plants", ["plant_id"], ["id"], ondelete="SET NULL")

    op.add_column("plants", sa.Column("listing_id", sa.Integer(), nullable=True))
    op.create_index("ix_plants_listing_id", "plants", ["listing_id"], unique=True)
    op.create_foreign_key("fk_plants_listing_id", "plants", "listings", ["listing_id"], ["id"], ondelete="SET NULL")

    op.create_table(
        "plant_observations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("plant_id", sa.Integer(), nullable=False),
        sa.Column("photo_path", sa.String(length=512), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quality_ok", sa.Boolean(), nullable=False),
        sa.Column("quality_reason", sa.Text(), nullable=True),
        sa.Column("top_label", sa.String(length=200), nullable=True),
        sa.Column("top_confidence", sa.Float(), nullable=True),
        sa.Column("predictions", sa.JSON(), nullable=True),
        sa.Column("advice_summary", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["plant_id"], ["plants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plant_observations_plant_id", "plant_observations", ["plant_id"])


def downgrade() -> None:
    op.drop_index("ix_plant_observations_plant_id", table_name="plant_observations")
    op.drop_table("plant_observations")
    op.drop_constraint("fk_plants_listing_id", "plants", type_="foreignkey")
    op.drop_index("ix_plants_listing_id", table_name="plants")
    op.drop_column("plants", "listing_id")
    op.drop_constraint("fk_listings_plant_id", "listings", type_="foreignkey")
    op.drop_index("ix_listings_plant_id", table_name="listings")
    op.drop_column("listings", "plant_id")
    op.drop_index("ix_plants_farmer_id", table_name="plants")
    op.drop_table("plants")
