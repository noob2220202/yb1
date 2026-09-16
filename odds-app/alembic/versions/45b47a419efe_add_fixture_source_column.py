"""add fixture source column

Revision ID: 45b47a419efe
Revises: 97cd275e5b3c
Create Date: 2026-09-16 23:43:44.893270

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '45b47a419efe'
down_revision: Union[str, Sequence[str], None] = '97cd275e5b3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('fixtures', sa.Column('source', sa.String(length=10), server_default='api', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fixtures', 'source')
