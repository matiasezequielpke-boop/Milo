"""custom agents

Agents a family member makes for one job (read-only, optional schedule).

Revision ID: e3c8f5a2b711
Revises: d2b7e41c9a10
Create Date: 2026-10-17 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'e3c8f5a2b711'
down_revision: Union[str, None] = 'd2b7e41c9a10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('custom_agents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('name', sa.String(length=40), nullable=False),
    sa.Column('instructions', sa.Text(), nullable=False),
    sa.Column('kind', sa.String(length=20), nullable=False),
    sa.Column('schedule', sa.String(length=10), nullable=False),
    sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_run_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], name='fk_custom_agents_household_id', ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], name='fk_custom_agents_created_by_user_id', ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_custom_agents_household_id'), 'custom_agents', ['household_id'], unique=False)
    op.create_index(op.f('ix_custom_agents_next_run_at'), 'custom_agents', ['next_run_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_custom_agents_next_run_at'), table_name='custom_agents')
    op.drop_index(op.f('ix_custom_agents_household_id'), table_name='custom_agents')
    op.drop_table('custom_agents')
