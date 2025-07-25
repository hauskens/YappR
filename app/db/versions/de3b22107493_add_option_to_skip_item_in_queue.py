"""add option to skip item in queue

Revision ID: de3b22107493
Revises: 1ba987b9aa33
Create Date: 2025-05-31 01:09:09.789246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'de3b22107493'
down_revision: Union[str, None] = '1ba987b9aa33'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('broadcaster_settings', sa.Column('linked_discord_disable_voting', sa.Boolean(), nullable=False))
    op.add_column('content_queue', sa.Column('skipped', sa.Boolean(), nullable=True))
    op.execute("UPDATE content_queue SET skipped = False")
    op.alter_column('content_queue', 'skipped', nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('content_queue', 'skipped')
    op.drop_column('broadcaster_settings', 'linked_discord_disable_voting')
    # ### end Alembic commands ###
