"""Adding PA to skinfolds table and enabling CPF and Email to be nullable

Revision ID: 207009c1bb68
Revises: 0ebb27680b61
Create Date: 2025-04-02 09:55:10.547418

"""
import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "207009c1bb68"  # pragma: allowlist secret
down_revision = "0ebb27680b61"  # pragma: allowlist secret
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("anthropometric_evaluations", schema=None) as batch_op:
        batch_op.drop_column("pa")

    with op.batch_alter_table("skinfolds", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pa", sa.String(length=6), nullable=False))

    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("skinfolds", schema=None) as batch_op:
        batch_op.drop_column("pa")

    with op.batch_alter_table("anthropometric_evaluations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("pa", sa.VARCHAR(length=6), autoincrement=False, nullable=False))

    # ### end Alembic commands ###
