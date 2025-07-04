"""contentqueue

Revision ID: f27b17547c9a
Revises: c78c8dba82f6
Create Date: 2025-05-29 10:13:20.100931

"""
from typing import Sequence, Union
from sqlalchemy.dialects.postgresql import ENUM

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'f27b17547c9a'
down_revision: Union[str, None] = 'c78c8dba82f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('content',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('url', sa.Text(), nullable=False),
        sa.Column('duration', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_table('external_users',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('username', sa.String(length=600), nullable=False),
        sa.Column('external_account_id', sa.String(length=500), nullable=True),
        sa.Column('account_type', ENUM('Discord', 'Twitch', name='accountsource', create_type=False), nullable=False),
        sa.Column('disabled', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_account_id')
    )
    op.create_table('content_queue',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('channel_id', sa.Integer(), nullable=False),
        sa.Column('content_id', sa.Integer(), nullable=False),
        sa.Column('watched', sa.Boolean(), nullable=False),
        sa.Column('watched_at', sa.DateTime(), nullable=True),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'], ),
        sa.ForeignKeyConstraint(['content_id'], ['content.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('channel_id', 'content_id', name='uq_channel_content')
    )
    op.create_table('content_queue_submissions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('content_queue_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('submitted_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['content_queue_id'], ['content_queue.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['external_users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('content_queue_id', 'user_id', name='uq_user_submission')
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('content_queue_submissions')
    op.drop_table('content_queue')
    op.drop_table('external_users')
    op.drop_table('content')
    # ### end Alembic commands ###
