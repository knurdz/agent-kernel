"""Add route_refreshed_at to deliveries for live leg OSRM refresh."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("deliveries", sa.Column("route_refreshed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("deliveries", "route_refreshed_at")
