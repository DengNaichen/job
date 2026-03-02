"""merge blob_pointers + company_api_platforms + source_id_enforcement

Revision ID: 0dfac58c9441
Revises: 9c0a1f2d3b4c, a91d4c7e2b11, b2c3d4e5f6a7
Create Date: 2026-03-01 23:00:14.517091

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "0dfac58c9441"
down_revision: Union[str, Sequence[str], None] = ("9c0a1f2d3b4c", "a91d4c7e2b11", "b2c3d4e5f6a7")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
