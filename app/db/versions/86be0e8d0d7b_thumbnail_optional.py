"""thumbnail-optional

Revision ID: 86be0e8d0d7b
Revises: 689e958b6177
Create Date: 2025-04-05 14:26:37.440367

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '86be0e8d0d7b'
down_revision: Union[str, None] = '689e958b6177'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
