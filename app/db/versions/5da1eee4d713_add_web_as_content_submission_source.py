"""add web as content submission source

Revision ID: 5da1eee4d713
Revises: 0a63df7fd2db
Create Date: 2025-07-07 17:22:24.932277

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file
import sqlalchemy_utils
from sqlalchemy.dialects import postgresql
from bot.platform_handlers import PlatformRegistry

# revision identifiers, used by Alembic.
revision: str = '5da1eee4d713'
down_revision: Union[str, None] = '0a63df7fd2db'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add 'Web' to the existing ENUM only if it doesn't exist
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_enum 
                WHERE enumlabel = 'Web' 
                AND enumtypid = (SELECT oid FROM pg_type WHERE typname = 'contentqueuesubmissionsource')
            ) THEN
                ALTER TYPE contentqueuesubmissionsource ADD VALUE 'Web';
            END IF;
        END
        $$;
    """)
    
    # Import needed modules for URL sanitization
    import sys
    from pathlib import Path
    import os
    
    # Add the project root to the path so we can import the bot modules
    project_root = Path(op.get_context().script.dir).parent.parent.parent
    sys.path.append(str(project_root))
    
    # Get connection and execute Python logic
    connection = op.get_bind()
    
    # Get all content rows with URLs
    result = connection.execute(sa.sql.text("SELECT id, url FROM content WHERE url IS NOT NULL"))
    
    for row in result:
        try:
            row_id = row[0]
            url = row[1]
            
            # Get the appropriate handler for the URL and sanitize it
            try:
                handler = PlatformRegistry.get_handler_for_url(url)
                sanitized_url = handler.sanitize_url(url)
                
                # Update the sanitized_url field for this row
                connection.execute(
                    sa.sql.text("UPDATE content SET stripped_url = :sanitized_url WHERE id = :id"),
                    {"sanitized_url": sanitized_url, "id": row_id}
                )
            except ValueError as e:
                print(f"Warning: Could not sanitize URL {url}: {e}")
                
        except Exception as e:
            print(f"Error processing row {row[0]}: {e}")
            # Continue with other rows instead of failing the migration
            continue
    
    # Drop the unique constraint that was preventing multiple submissions per user
    op.drop_constraint('uq_user_submission', 'content_queue_submissions', type_='unique')


def downgrade() -> None:
    """Downgrade schema."""
    
    # PostgreSQL doesn't support removing ENUM values directly
    # You would need to recreate the ENUM and update the column
    # For now, we'll leave the enum value in place
    pass
