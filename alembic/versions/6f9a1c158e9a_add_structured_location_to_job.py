"""add structured location to job

Revision ID: 6f9a1c158e9a
Revises: 0dfac58c9441
Create Date: 2026-03-01 23:22:47.355594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6f9a1c158e9a'
down_revision: Union[str, Sequence[str], None] = '0dfac58c9441'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    workplace_type = sa.Enum('remote', 'hybrid', 'onsite', 'unknown', name='workplacetype')
    workplace_type.create(op.get_bind(), checkfirst=True)
    
    op.add_column('job', sa.Column('location_city', sa.String(), nullable=True))
    op.add_column('job', sa.Column('location_region', sa.String(), nullable=True))
    op.add_column('job', sa.Column('location_country_code', sa.String(), nullable=True))
    op.add_column(
        'job', 
        sa.Column('location_workplace_type', workplace_type, server_default='unknown', nullable=False)
    )
    op.add_column('job', sa.Column('location_remote_scope', sa.String(), nullable=True))
    
    op.create_index(op.f('ix_job_location_country_code'), 'job', ['location_country_code'], unique=False)
    op.create_index(op.f('ix_job_location_workplace_type'), 'job', ['location_workplace_type'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_job_location_workplace_type'), table_name='job')
    op.drop_index(op.f('ix_job_location_country_code'), table_name='job')
    
    op.drop_column('job', 'location_remote_scope')
    op.drop_column('job', 'location_workplace_type')
    op.drop_column('job', 'location_country_code')
    op.drop_column('job', 'location_region')
    op.drop_column('job', 'location_city')
    
    workplace_type = sa.Enum('remote', 'hybrid', 'onsite', 'unknown', name='workplacetype')
    workplace_type.drop(op.get_bind(), checkfirst=True)
