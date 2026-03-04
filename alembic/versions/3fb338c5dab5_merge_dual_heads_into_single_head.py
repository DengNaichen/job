"""merge dual heads into single head

Revision ID: 3fb338c5dab5
Revises: 5a7b8c9d0e1f, e3f4a5b6c7d8
Create Date: 2026-03-03 14:50:19.527352

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = '3fb338c5dab5'
down_revision: Union[str, Sequence[str], None] = ('5a7b8c9d0e1f', 'e3f4a5b6c7d8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
