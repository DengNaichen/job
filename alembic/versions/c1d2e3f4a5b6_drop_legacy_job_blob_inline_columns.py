"""drop legacy inline job blob columns

Revision ID: c1d2e3f4a5b6
Revises: f7a8b9c0d1e2
Create Date: 2026-03-02 19:30:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: Union[str, Sequence[str], None] = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("job"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("job")}
    if "description_html" in existing_columns:
        op.drop_column("job", "description_html")
    if "raw_payload" in existing_columns:
        op.drop_column("job", "raw_payload")


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("job"):
        return

    existing_columns = {col["name"] for col in inspector.get_columns("job")}
    if "description_html" not in existing_columns:
        op.add_column("job", sa.Column("description_html", sa.Text(), nullable=True))
    if "raw_payload" not in existing_columns:
        op.add_column("job", sa.Column("raw_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
