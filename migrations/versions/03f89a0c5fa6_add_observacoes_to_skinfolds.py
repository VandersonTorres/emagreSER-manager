"""add observacoes to skinfolds

Revision ID: 03f89a0c5fa6
Revises: fb739ba57804
Create Date: 2026-11-27 14:43:53.327475

"""
import sqlalchemy as sa
from alembic import op

revision = "03f89a0c5fa6"  # pragma: allowlist secret
down_revision = "fb739ba57804"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add the optional observation of a bioimpedance measurement; the measurements already stored get NULL."""
    with op.batch_alter_table("skinfolds", schema=None) as batch_op:
        batch_op.add_column(sa.Column("observacoes", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove the observation of the bioimpedance measurements."""
    with op.batch_alter_table("skinfolds", schema=None) as batch_op:
        batch_op.drop_column("observacoes")
