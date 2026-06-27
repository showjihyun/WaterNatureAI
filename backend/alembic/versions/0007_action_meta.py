"""0007 user_opportunity_actions.meta (JSONB)

추천 피드백: hidden(관심없음) 사유 등 액션 메타를 저장({"reason": ...}).
비파괴적 ADD COLUMN, nullable.

Revision ID: 0007_action_meta
Revises: 0006_pursuits
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0007_action_meta'
down_revision = '0006_pursuits'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'user_opportunity_actions',
        sa.Column('meta', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('user_opportunity_actions', 'meta')
