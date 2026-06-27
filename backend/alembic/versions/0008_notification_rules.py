"""0008 notification_settings 알림 규칙(min_score, excluded_sources)

맞춤 알림 규칙: 적합도 임계값 + 브리핑 제외 소스. 모두 nullable(비파괴적).

Revision ID: 0008_notification_rules
Revises: 0007_action_meta
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0008_notification_rules'
down_revision = '0007_action_meta'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('notification_settings', sa.Column('min_score', sa.SmallInteger(), nullable=True))
    op.add_column(
        'notification_settings',
        sa.Column('excluded_sources', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('notification_settings', 'excluded_sources')
    op.drop_column('notification_settings', 'min_score')
