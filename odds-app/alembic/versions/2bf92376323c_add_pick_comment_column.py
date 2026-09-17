"""add pick comment column

Revision ID: 2bf92376323c
Revises: 3143d8da591f
Create Date: 2026-09-17 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2bf92376323c'
down_revision: Union[str, Sequence[str], None] = '3143d8da591f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('picks', sa.Column('comment', sa.String(length=500), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('picks', 'comment')
