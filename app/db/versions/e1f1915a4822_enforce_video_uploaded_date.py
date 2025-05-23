"""enforce video uploaded date

Revision ID: e1f1915a4822
Revises: 28f74a2de022
Create Date: 2025-04-08 18:23:26.565936

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlalchemy_file
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e1f1915a4822"
down_revision: Union[str, None] = "28f74a2de022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        UPDATE video SET uploaded = '1970-01-01' WHERE uploaded IS NULL;
    """
    )
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "video", "uploaded", existing_type=postgresql.TIMESTAMP(), nullable=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column(
        "video", "uploaded", existing_type=postgresql.TIMESTAMP(), nullable=True
    )
    # ### end Alembic commands ###
