"""warden family mvp

Households (elder + approvers), consent, Plaid-backed accounts and
transactions, detector alerts and subscriptions, payees/bills/payments,
and the household scope + replay columns on the existing tables.

Revision ID: c4a0ab7479dd
Revises: b687bd82be0c
Create Date: 2026-10-16 15:44:27.274940

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c4a0ab7479dd'
down_revision: Union[str, None] = 'b687bd82be0c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('households',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('household_members',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('user_id', sa.UUID(), nullable=True),
    sa.Column('email', sa.String(length=320), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('role', sa.Enum('elder', 'approver', name='member_role', native_enum=False, length=20), nullable=False),
    sa.Column('status', sa.Enum('invited', 'active', 'removed', name='member_status', native_enum=False, length=20), nullable=False),
    sa.Column('invite_token_hash', sa.String(length=64), nullable=True),
    sa.Column('invited_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('joined_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('household_id', 'email', name='uq_member_email_per_household'),
    sa.UniqueConstraint('invite_token_hash')
    )
    op.create_index(op.f('ix_household_members_household_id'), 'household_members', ['household_id'], unique=False)
    op.create_index(op.f('ix_household_members_user_id'), 'household_members', ['user_id'], unique=False)
    op.create_table('payees',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('category', sa.String(length=60), nullable=True),
    sa.Column('stripe_account_id', sa.String(length=100), nullable=True),
    sa.Column('blocked', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('household_id', 'name', name='uq_payee_name_per_household')
    )
    op.create_index(op.f('ix_payees_household_id'), 'payees', ['household_id'], unique=False)
    op.create_table('subscriptions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('merchant_key', sa.String(length=200), nullable=False),
    sa.Column('merchant_name', sa.String(length=200), nullable=False),
    sa.Column('average_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('last_amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('cadence_days', sa.Integer(), nullable=False),
    sa.Column('charge_count', sa.Integer(), nullable=False),
    sa.Column('first_charged_on', sa.Date(), nullable=False),
    sa.Column('last_charged_on', sa.Date(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('household_id', 'merchant_key', name='uq_subscription_merchant')
    )
    op.create_index(op.f('ix_subscriptions_household_id'), 'subscriptions', ['household_id'], unique=False)
    op.create_table('bank_connections',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('owner_member_id', sa.UUID(), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_item_id', sa.String(length=100), nullable=False),
    sa.Column('credential_id', sa.UUID(), nullable=False),
    sa.Column('institution_name', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('sync_cursor', sa.Text(), nullable=True),
    sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['credential_id'], ['credentials.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['owner_member_id'], ['household_members.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_item_id')
    )
    op.create_index(op.f('ix_bank_connections_household_id'), 'bank_connections', ['household_id'], unique=False)
    op.create_table('bills',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('payee_id', sa.UUID(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('due_date', sa.Date(), nullable=True),
    sa.Column('reference', sa.String(length=200), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by_user_id', sa.UUID(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['payee_id'], ['payees.id'], ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_bills_household_id'), 'bills', ['household_id'], unique=False)
    op.create_table('consents',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('elder_member_id', sa.UUID(), nullable=False),
    sa.Column('approver_member_id', sa.UUID(), nullable=False),
    sa.Column('scopes', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('text_version', sa.String(length=20), nullable=False),
    sa.Column('granted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['approver_member_id'], ['household_members.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['elder_member_id'], ['household_members.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_consents_household_id'), 'consents', ['household_id'], unique=False)
    op.create_table('bank_accounts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('connection_id', sa.UUID(), nullable=False),
    sa.Column('provider_account_id', sa.String(length=100), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('mask', sa.String(length=10), nullable=True),
    sa.Column('type', sa.String(length=40), nullable=True),
    sa.Column('subtype', sa.String(length=40), nullable=True),
    sa.Column('current_balance', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('available_balance', sa.Numeric(precision=14, scale=2), nullable=True),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['connection_id'], ['bank_connections.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_account_id')
    )
    op.create_index(op.f('ix_bank_accounts_household_id'), 'bank_accounts', ['household_id'], unique=False)
    op.create_table('payments',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('bill_id', sa.UUID(), nullable=False),
    sa.Column('approval_id', sa.UUID(), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('provider', sa.String(length=20), nullable=False),
    sa.Column('provider_payment_id', sa.String(length=100), nullable=True),
    sa.Column('livemode', sa.Boolean(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['approval_id'], ['approval_requests.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['bill_id'], ['bills.id'], ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('approval_id')
    )
    op.create_index(op.f('ix_payments_household_id'), 'payments', ['household_id'], unique=False)
    op.create_table('bank_transactions',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('account_id', sa.UUID(), nullable=False),
    sa.Column('provider_transaction_id', sa.String(length=100), nullable=False),
    sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
    sa.Column('currency', sa.String(length=3), nullable=False),
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('name', sa.String(length=300), nullable=False),
    sa.Column('merchant_name', sa.String(length=200), nullable=True),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('payment_channel', sa.String(length=20), nullable=True),
    sa.Column('pending', sa.Boolean(), nullable=False),
    sa.Column('removed', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['account_id'], ['bank_accounts.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('provider_transaction_id')
    )
    op.create_index('ix_bank_transactions_household_date', 'bank_transactions', ['household_id', 'date'], unique=False)
    op.create_table('alerts',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('household_id', sa.UUID(), nullable=False),
    sa.Column('transaction_id', sa.UUID(), nullable=True),
    sa.Column('kind', sa.String(length=40), nullable=False),
    sa.Column('dedupe_key', sa.String(length=200), nullable=False),
    sa.Column('severity', sa.String(length=10), nullable=False),
    sa.Column('title', sa.String(length=300), nullable=False),
    sa.Column('reasons', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('status', sa.Enum('open', 'confirmed_legit', 'confirmed_fraud', 'dismissed', name='alert_status', native_enum=False, length=20), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('resolved_by_user_id', sa.UUID(), nullable=True),
    sa.ForeignKeyConstraint(['household_id'], ['households.id'], ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['resolved_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['transaction_id'], ['bank_transactions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('household_id', 'kind', 'dedupe_key', name='uq_alert_dedupe')
    )
    op.create_index(op.f('ix_alerts_household_id'), 'alerts', ['household_id'], unique=False)
    op.add_column('approval_requests', sa.Column('household_id', sa.UUID(), nullable=True))
    op.add_column('approval_requests', sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('approval_requests', sa.Column('resolved_by_user_id', sa.UUID(), nullable=True))
    op.add_column('approval_requests', sa.Column('resolution_note', sa.Text(), nullable=True))
    op.add_column('approval_requests', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('approval_requests', sa.Column('execution_result', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index(op.f('ix_approval_requests_household_id'), 'approval_requests', ['household_id'], unique=False)
    op.create_foreign_key('fk_approval_requests_resolved_by_user_id', 'approval_requests', 'users', ['resolved_by_user_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('fk_approval_requests_household_id', 'approval_requests', 'households', ['household_id'], ['id'], ondelete='CASCADE')
    op.add_column('audit_log', sa.Column('household_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_audit_log_household_id'), 'audit_log', ['household_id'], unique=False)
    op.create_foreign_key('fk_audit_log_household_id', 'audit_log', 'households', ['household_id'], ['id'], ondelete='SET NULL')
    op.add_column('conversations', sa.Column('household_id', sa.UUID(), nullable=True))
    op.add_column('conversations', sa.Column('agent_busy_until', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_conversations_household_id'), 'conversations', ['household_id'], unique=False)
    op.create_foreign_key('fk_conversations_household_id', 'conversations', 'households', ['household_id'], ['id'], ondelete='CASCADE')
    op.add_column('messages', sa.Column('seq', sa.BigInteger(), sa.Identity(always=False), nullable=False))
    op.create_unique_constraint('uq_messages_seq', 'messages', ['seq'])
    op.add_column('messages', sa.Column('api_content', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('messages', sa.Column('author_user_id', sa.UUID(), nullable=True))
    op.create_foreign_key('fk_messages_author_user_id', 'messages', 'users', ['author_user_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_messages_author_user_id', 'messages', type_='foreignkey')
    op.drop_column('messages', 'author_user_id')
    op.drop_column('messages', 'api_content')
    op.drop_constraint('uq_messages_seq', 'messages', type_='unique')
    op.drop_column('messages', 'seq')
    op.drop_constraint('fk_conversations_household_id', 'conversations', type_='foreignkey')
    op.drop_index(op.f('ix_conversations_household_id'), table_name='conversations')
    op.drop_column('conversations', 'agent_busy_until')
    op.drop_column('conversations', 'household_id')
    op.drop_constraint('fk_audit_log_household_id', 'audit_log', type_='foreignkey')
    op.drop_index(op.f('ix_audit_log_household_id'), table_name='audit_log')
    op.drop_column('audit_log', 'household_id')
    op.drop_constraint('fk_approval_requests_household_id', 'approval_requests', type_='foreignkey')
    op.drop_constraint('fk_approval_requests_resolved_by_user_id', 'approval_requests', type_='foreignkey')
    op.drop_index(op.f('ix_approval_requests_household_id'), table_name='approval_requests')
    op.drop_column('approval_requests', 'execution_result')
    op.drop_column('approval_requests', 'expires_at')
    op.drop_column('approval_requests', 'resolution_note')
    op.drop_column('approval_requests', 'resolved_by_user_id')
    op.drop_column('approval_requests', 'summary')
    op.drop_column('approval_requests', 'household_id')
    op.drop_index(op.f('ix_alerts_household_id'), table_name='alerts')
    op.drop_table('alerts')
    op.drop_index('ix_bank_transactions_household_date', table_name='bank_transactions')
    op.drop_table('bank_transactions')
    op.drop_index(op.f('ix_payments_household_id'), table_name='payments')
    op.drop_table('payments')
    op.drop_index(op.f('ix_bank_accounts_household_id'), table_name='bank_accounts')
    op.drop_table('bank_accounts')
    op.drop_index(op.f('ix_consents_household_id'), table_name='consents')
    op.drop_table('consents')
    op.drop_index(op.f('ix_bills_household_id'), table_name='bills')
    op.drop_table('bills')
    op.drop_index(op.f('ix_bank_connections_household_id'), table_name='bank_connections')
    op.drop_table('bank_connections')
    op.drop_index(op.f('ix_subscriptions_household_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_index(op.f('ix_payees_household_id'), table_name='payees')
    op.drop_table('payees')
    op.drop_index(op.f('ix_household_members_user_id'), table_name='household_members')
    op.drop_index(op.f('ix_household_members_household_id'), table_name='household_members')
    op.drop_table('household_members')
    op.drop_table('households')
