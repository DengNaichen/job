"""add structured_jd fields to job

Revision ID: 2f0e2e312c15
Revises: 003
Create Date: 2026-02-27 12:12:31.873685

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2f0e2e312c15'
down_revision: Union[str, Sequence[str], None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add structured_jd and structured_jd_updated_at columns to job table."""
    op.add_column(
        'job',
        sa.Column('structured_jd', postgresql.JSONB(), nullable=True)
    )
    op.add_column(
        'job',
        sa.Column('structured_jd_updated_at', sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    """Remove structured_jd columns from job table."""
    op.drop_column('job', 'structured_jd_updated_at')
    op.drop_column('job', 'structured_jd')
