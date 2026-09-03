"""add privacy compliance tables

Registra consentimiento versionado, solicitudes de eliminacion y el
audit log de accesos a datos personales (Ley N. 29733).

Revision ID: b7d3e91a4c25
Revises: 9f8c2f0a64d1
Create Date: 2026-09-03 12:00:00

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7d3e91a4c25"
down_revision = "9f8c2f0a64d1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "consentimientos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("version_politica", sa.String(length=32), nullable=False),
        sa.Column("aceptado_en", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "usuario_id", "version_politica", name="uq_consentimiento_usuario_version"
        ),
    )
    with op.batch_alter_table("consentimientos", schema=None) as batch_op:
        batch_op.create_index(
            "ix_consentimientos_usuario_id", ["usuario_id"], unique=False
        )

    op.create_table(
        "solicitudes_eliminacion",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("solicitado_en", sa.DateTime(timezone=True), nullable=False),
        sa.Column("purgar_desde", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelado_en", sa.DateTime(timezone=True), nullable=True),
        sa.Column("bitacora", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("solicitudes_eliminacion", schema=None) as batch_op:
        batch_op.create_index(
            "ix_solicitudes_eliminacion_usuario_id", ["usuario_id"], unique=False
        )
        batch_op.create_index(
            "ix_solicitudes_eliminacion_purgar_desde", ["purgar_desde"], unique=False
        )

    op.create_table(
        "accesos_datos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("titular_id", sa.Integer(), nullable=True),
        sa.Column("recurso", sa.String(length=64), nullable=False),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["titular_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("accesos_datos", schema=None) as batch_op:
        batch_op.create_index(
            "ix_accesos_datos_titular_momento", ["titular_id", "momento"], unique=False
        )


def downgrade():
    with op.batch_alter_table("accesos_datos", schema=None) as batch_op:
        batch_op.drop_index("ix_accesos_datos_titular_momento")
    op.drop_table("accesos_datos")

    with op.batch_alter_table("solicitudes_eliminacion", schema=None) as batch_op:
        batch_op.drop_index("ix_solicitudes_eliminacion_purgar_desde")
        batch_op.drop_index("ix_solicitudes_eliminacion_usuario_id")
    op.drop_table("solicitudes_eliminacion")

    with op.batch_alter_table("consentimientos", schema=None) as batch_op:
        batch_op.drop_index("ix_consentimientos_usuario_id")
    op.drop_table("consentimientos")
