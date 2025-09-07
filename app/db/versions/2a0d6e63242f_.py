"""fix auto-increment for partitioned chatlogs table

Revision ID: 2a0d6e63242f
Revises: d2f096a552aa
Create Date: 2025-09-06 22:23:51.697801

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '2a0d6e63242f'
down_revision: Union[str, None] = 'd2f096a552aa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create sequence for chatlogs id column
    op.execute('CREATE SEQUENCE IF NOT EXISTS chatlogs_id_seq')
    
    # Set the sequence to start from the current max id + 1
    op.execute('''
        SELECT setval('chatlogs_id_seq', 
            COALESCE((SELECT MAX(id) FROM chatlogs), 0) + 1, 
            false)
    ''')
    
    # Set default value for id column to use the sequence
    op.execute('ALTER TABLE chatlogs ALTER COLUMN id SET DEFAULT nextval(\'chatlogs_id_seq\')')
    
    # Associate the sequence with the column for proper ownership
    op.execute('ALTER SEQUENCE chatlogs_id_seq OWNED BY chatlogs.id')


def downgrade() -> None:
    """Downgrade schema."""
    # Remove default value from id column
    op.execute('ALTER TABLE chatlogs ALTER COLUMN id DROP DEFAULT')
    
    # Drop the sequence
    op.execute('DROP SEQUENCE IF EXISTS chatlogs_id_seq')
