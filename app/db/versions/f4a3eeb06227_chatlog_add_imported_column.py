"""chatlog add imported column

Revision ID: f4a3eeb06227
Revises: bc541bcf1b53
Create Date: 2025-05-29 13:31:49.763557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'f4a3eeb06227'
down_revision: Union[str, None] = 'bc541bcf1b53'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('chatlogs', sa.Column('imported', sa.Boolean(), nullable=True))
    op.execute("UPDATE chatlogs SET imported = True")
    op.alter_column('chatlogs', 'imported', nullable=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('chatlogs', 'imported')
    # ### end Alembic commands ###
