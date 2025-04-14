"""oauth

Revision ID: 8197cf48587e
Revises: 50da5760d226
Create Date: 2025-04-14 16:30:11.645807

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file


# revision identifiers, used by Alembic.
revision: str = '8197cf48587e'
down_revision: Union[str, None] = '50da5760d226'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('flask_dance_oauth',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('provider', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('token', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_flask_dance_oauth_user_id'), 'flask_dance_oauth', ['user_id'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_flask_dance_oauth_user_id'), table_name='flask_dance_oauth')
    op.drop_table('flask_dance_oauth')
    # ### end Alembic commands ###
