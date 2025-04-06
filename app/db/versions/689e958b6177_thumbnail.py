"""thumbnail

Revision ID: 689e958b6177
Revises: dbfd73de2e1f
Create Date: 2025-04-05 14:15:38.863479

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '689e958b6177'
down_revision: Union[str, None] = 'dbfd73de2e1f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
