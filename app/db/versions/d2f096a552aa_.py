"""Partition ChatLog table by channel_id using hash partitioning

Revision ID: d2f096a552aa
Revises: 9bcb1b066d74
Create Date: 2025-09-03 23:18:47.061909

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file
import sqlalchemy_utils


# revision identifiers, used by Alembic.
revision: str = 'd2f096a552aa'
down_revision: Union[str, None] = '9bcb1b066d74'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Keep the existing video constraint
    # op.create_unique_constraint(None, 'video', ['platform_ref'])
    
    # Partition ChatLog table by channel_id
    # Step 1: Rename existing table
    op.rename_table('chatlogs', 'chatlogs_old')
    
    # Step 2: Create partitioned table
    op.execute('''
        CREATE TABLE chatlogs (
            id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            username VARCHAR(256) NOT NULL,
            message VARCHAR(600) NOT NULL,
            external_user_account_id INTEGER,
            import_id INTEGER,
            CONSTRAINT pk_chatlogs PRIMARY KEY (id, channel_id),
            CONSTRAINT fk_chatlogs_channel_id_channels FOREIGN KEY(channel_id) REFERENCES channels (id),
            CONSTRAINT fk_chatlogs_import_id_chatlog_imports FOREIGN KEY(import_id) REFERENCES chatlog_imports (id)
        ) PARTITION BY HASH (channel_id)
    ''')
    
    # Step 3: Create 8 hash partitions
    for i in range(8):
        op.execute(f'''
            CREATE TABLE chatlogs_p{i} PARTITION OF chatlogs 
            FOR VALUES WITH (modulus 8, remainder {i})
        ''')
    
    # Step 4: Copy data from old table to partitioned table
    op.execute('INSERT INTO chatlogs SELECT * FROM chatlogs_old')
    
    # Step 5: Recreate the index on the partitioned table (if not exists)
    op.execute('CREATE INDEX IF NOT EXISTS ix_chatlogs_channel_timestamp ON chatlogs (channel_id, timestamp)')
    
    # Step 6: Drop old table
    op.drop_table('chatlogs_old')


def downgrade() -> None:
    """Downgrade schema."""
    # Revert partitioning
    # Step 1: Create regular table
    op.execute('''
        CREATE TABLE chatlogs_restored (
            id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            timestamp TIMESTAMP WITHOUT TIME ZONE NOT NULL,
            username VARCHAR(256) NOT NULL,
            message VARCHAR(600) NOT NULL,
            external_user_account_id INTEGER,
            import_id INTEGER,
            CONSTRAINT pk_chatlogs_restored PRIMARY KEY (id),
            CONSTRAINT fk_chatlogs_restored_channel_id_channels FOREIGN KEY(channel_id) REFERENCES channels (id),
            CONSTRAINT fk_chatlogs_restored_import_id_chatlog_imports FOREIGN KEY(import_id) REFERENCES chatlog_imports (id)
        )
    ''')
    
    # Step 2: Copy data back
    op.execute('INSERT INTO chatlogs_restored SELECT * FROM chatlogs')
    
    # Step 3: Drop partitioned table (automatically drops partition tables)
    op.drop_table('chatlogs')
    
    # Step 4: Rename restored table back
    op.rename_table('chatlogs_restored', 'chatlogs')
    
    # Step 5: Recreate original index (if not exists)
    op.execute('CREATE INDEX IF NOT EXISTS ix_chatlogs_channel_timestamp ON chatlogs (channel_id, timestamp)')
    
    # Revert the video constraint
    # op.drop_constraint(None, 'video', type_='unique')
