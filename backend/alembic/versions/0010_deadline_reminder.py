"""0010 notification_settings.deadline_reminder_days (마감 리마인더)

관심/진행 공고 마감 N일 전 알림. null=기본 3(D-3), 0=끄기. 비파괴적(nullable).

Revision ID: 0010_deadline_reminder
Revises: 0009_keyword_watches
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = '0010_deadline_reminder'
down_revision = '0009_keyword_watches'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'notification_settings',
        sa.Column('deadline_reminder_days', sa.SmallInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('notification_settings', 'deadline_reminder_days')
