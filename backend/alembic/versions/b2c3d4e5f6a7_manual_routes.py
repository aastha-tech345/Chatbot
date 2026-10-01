"""manual_routes

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-09-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("application_routes", schema=None) as batch_op:
        batch_op.add_column(sa.Column("full_url", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("name", sa.String(length=200), nullable=True))
        batch_op.add_column(sa.Column("source", sa.String(length=20), nullable=False, server_default="openapi"))
        batch_op.add_column(sa.Column("auth_type", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("headers_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("query_params_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("path_params_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("request_body_json", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("content_type", sa.String(length=100), nullable=True))

    with op.batch_alter_table("application_routes", schema=None) as batch_op:
        batch_op.alter_column("source", server_default=None)


def downgrade() -> None:
    with op.batch_alter_table("application_routes", schema=None) as batch_op:
        batch_op.drop_column("content_type")
        batch_op.drop_column("request_body_json")
        batch_op.drop_column("path_params_json")
        batch_op.drop_column("query_params_json")
        batch_op.drop_column("headers_json")
        batch_op.drop_column("auth_type")
        batch_op.drop_column("source")
        batch_op.drop_column("name")
        batch_op.drop_column("full_url")
