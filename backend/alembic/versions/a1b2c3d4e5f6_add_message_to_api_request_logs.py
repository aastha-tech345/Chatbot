"""add message column to api_request_logs

Revision ID: a1b2c3d4e5f6
Revises: 0b9fe6b37450
Create Date: 2026-09-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0b9fe6b37450'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The 'message' column is already created in the initial schema (0b9fe6b37450).
    # This migration is a no-op to maintain migration history.
    pass


def downgrade() -> None:
    # No-op (column is part of initial schema)
    pass
