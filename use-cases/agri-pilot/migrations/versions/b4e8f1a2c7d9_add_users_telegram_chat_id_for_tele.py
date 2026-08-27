"""add users.telegram_chat_id for Telegram linking

Revision ID: b4e8f1a2c7d9
Revises: e18509a42d04
Create Date: 2026-08-25 00:00:00.000000

Nullable unique column backing the contact-share linking flow: the Telegram
bot writes the farmer's chat_id here after a verified contact share, and the
webhook gate looks users up by it on every subsequent message.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "b4e8f1a2c7d9"
down_revision: Union[str, None] = "e18509a42d04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.create_index(op.f("ix_users_telegram_chat_id"), "users", ["telegram_chat_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_users_telegram_chat_id"), table_name="users")
    op.drop_column("users", "telegram_chat_id")
