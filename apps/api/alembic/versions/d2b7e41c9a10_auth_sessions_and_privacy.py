"""auth sessions and privacy

Two-step login (verified Supabase sessions + login challenges), the
consent record on users (terms version, age confirmation, email opt-out),
and approval requests that survive the requester deleting their account.

Revision ID: d2b7e41c9a10
Revises: c4a0ab7479dd
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd2b7e41c9a10'
down_revision: Union[str, None] = 'c4a0ab7479dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('terms_version', sa.String(length=40), nullable=True))
    op.add_column('users', sa.Column('terms_accepted_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('age_confirmed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('email_opt_out_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table('auth_sessions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=False),
    sa.Column('method', sa.String(length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name='fk_auth_sessions_user_id', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_auth_sessions_user_id'), 'auth_sessions', ['user_id'], unique=False)

    op.create_table('login_challenges',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('password_ok', sa.Boolean(), nullable=False),
    sa.Column('codes_sent', sa.Integer(), nullable=False),
    sa.Column('code_attempts', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('consumed_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_login_challenges_email'), 'login_challenges', ['email'], unique=False)

    op.alter_column('approval_requests', 'user_id', existing_type=sa.UUID(), nullable=True)
    op.drop_constraint('approval_requests_user_id_fkey', 'approval_requests', type_='foreignkey')
    op.create_foreign_key(
        'fk_approval_requests_user_id', 'approval_requests', 'users', ['user_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_approval_requests_user_id', 'approval_requests', type_='foreignkey')
    op.execute("DELETE FROM approval_requests WHERE user_id IS NULL")
    op.create_foreign_key(
        'approval_requests_user_id_fkey', 'approval_requests', 'users', ['user_id'], ['id'], ondelete='CASCADE'
    )
    op.alter_column('approval_requests', 'user_id', existing_type=sa.UUID(), nullable=False)

    op.drop_index(op.f('ix_login_challenges_email'), table_name='login_challenges')
    op.drop_table('login_challenges')
    op.drop_index(op.f('ix_auth_sessions_user_id'), table_name='auth_sessions')
    op.drop_table('auth_sessions')

    op.drop_column('users', 'email_opt_out_at')
    op.drop_column('users', 'age_confirmed_at')
    op.drop_column('users', 'terms_accepted_at')
    op.drop_column('users', 'terms_version')
