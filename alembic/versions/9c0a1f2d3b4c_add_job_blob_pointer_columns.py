"""add job blob pointer columns

Revision ID: 9c0a1f2d3b4c
Revises: e1f2a3b4c5d6
Create Date: 2026-02-28 16:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c0a1f2d3b4c"
down_revision: str | Sequence[str] | None = "e1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job", sa.Column("description_html_key", sa.String(length=255), nullable=True))
    op.add_column("job", sa.Column("description_html_hash", sa.String(length=64), nullable=True))
    op.add_column("job", sa.Column("raw_payload_key", sa.String(length=255), nullable=True))
    op.add_column("job", sa.Column("raw_payload_hash", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("job", "raw_payload_hash")
    op.drop_column("job", "raw_payload_key")
    op.drop_column("job", "description_html_hash")
    op.drop_column("job", "description_html_key")
