"""Add optional connection plans and invitation notifications.

Revision ID: c8e4b2197a30
Revises: b7d3e91a4c25
"""

import sqlalchemy as sa
from alembic import op

revision = "c8e4b2197a30"
down_revision = "b7d3e91a4c25"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("conexiones") as batch_op:
        batch_op.add_column(sa.Column("plan_tipo", sa.String(16), nullable=True))
        batch_op.add_column(sa.Column("plan_tema", sa.String(120), nullable=True))
        batch_op.create_check_constraint(
            "ck_conexion_plan",
            "(plan_tipo IS NULL AND plan_tema IS NULL) OR "
            "(plan_tipo IS NOT NULL AND plan_tipo IN ('estudio', 'proyecto', 'social') "
            "AND plan_tema IS NOT NULL AND length(trim(plan_tema)) BETWEEN 1 AND 120)",
        )
    with op.batch_alter_table("notificaciones") as batch_op:
        batch_op.alter_column(
            "tipo", existing_type=sa.String(7),
            type_=sa.Enum("mensaje", "invitacion", "conexion", name="tipo_notificacion",
                          native_enum=False), existing_nullable=False,
        )


def downgrade():
    # Refuse a lossy downgrade while plan alerts still require the expanded type.
    count = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM notificaciones WHERE tipo != 'mensaje'"
    )).scalar()
    if count:
        raise RuntimeError("Cannot downgrade while invitation notifications exist")
    with op.batch_alter_table("notificaciones") as batch_op:
        batch_op.alter_column("tipo", existing_type=sa.String(10),
                              type_=sa.String(7), existing_nullable=False)
    with op.batch_alter_table("conexiones") as batch_op:
        batch_op.drop_constraint("ck_conexion_plan", type_="check")
        batch_op.drop_column("plan_tema")
        batch_op.drop_column("plan_tipo")
