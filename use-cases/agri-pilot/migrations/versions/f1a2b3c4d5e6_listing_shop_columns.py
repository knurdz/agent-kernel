"""Listing shop: image, category, description, view_count."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "e8f2a1b3c4d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("listings", sa.Column("image_path", sa.String(length=512), nullable=True))
    op.add_column(
        "listings",
        sa.Column("category", sa.String(length=32), nullable=False, server_default="vegetable"),
    )
    op.add_column("listings", sa.Column("description", sa.String(length=500), nullable=True))
    op.add_column(
        "listings",
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_listings_status_category", "listings", ["status", "category"])


def downgrade() -> None:
    op.drop_index("ix_listings_status_category", table_name="listings")
    op.drop_column("listings", "view_count")
    op.drop_column("listings", "description")
    op.drop_column("listings", "category")
    op.drop_column("listings", "image_path")
