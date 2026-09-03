"""widen avatar URL

Revision ID: 9f8c2f0a64d1
Revises: 25a14c8b7795
Create Date: 2026-09-03 00:08:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "9f8c2f0a64d1"
down_revision = "25a14c8b7795"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.alter_column(
            "foto_archivo",
            existing_type=sa.String(length=160),
            type_=sa.String(length=500),
            existing_nullable=True,
        )


def downgrade():
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.alter_column(
            "foto_archivo",
            existing_type=sa.String(length=500),
            type_=sa.String(length=160),
            existing_nullable=True,
        )
