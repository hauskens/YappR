"""add avatar url to user

Revision ID: 663ea34e3293
Revises: 46ea97a05a39
Create Date: 2025-04-14 21:05:04.593594

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file


# revision identifiers, used by Alembic.
revision: str = '663ea34e3293'
down_revision: Union[str, None] = '46ea97a05a39'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('users', sa.Column('avatar_url', sa.String(length=500), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('users', 'avatar_url')
    # ### end Alembic commands ###
