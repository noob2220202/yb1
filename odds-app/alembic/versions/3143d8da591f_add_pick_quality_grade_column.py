"""add pick quality_grade column

Revision ID: 3143d8da591f
Revises: 2899bca7341d
Create Date: 2026-09-17 10:06:19.914868

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3143d8da591f'
down_revision: Union[str, Sequence[str], None] = '2899bca7341d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('picks', sa.Column('quality_grade', sa.String(length=2), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('picks', 'quality_grade')
