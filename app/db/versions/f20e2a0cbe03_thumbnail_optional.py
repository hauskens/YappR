"""thumbnail-optional

Revision ID: f20e2a0cbe03
Revises: 86be0e8d0d7b
Create Date: 2025-04-05 14:29:57.903037

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f20e2a0cbe03'
down_revision: Union[str, None] = '86be0e8d0d7b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
