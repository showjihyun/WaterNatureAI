"""0009 keyword_watches (키워드 워치 = 저장 검색)

회사별 키워드. 공고 제목에 포함되면 워치 피드 대상. (company, lower(keyword)) 유니크.

Revision ID: 0009_keyword_watches
Revises: 0008_notification_rules
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0009_keyword_watches'
down_revision = '0008_notification_rules'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'keyword_watches',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('keyword', sa.String(length=80), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_keyword_watches_company_id', 'keyword_watches', ['company_id'])
    # (company, lower(keyword)) 유니크 — 대소문자 무시 중복 방지(함수 기반).
    op.create_index(
        'uq_keyword_watch_company_lower',
        'keyword_watches',
        ['company_id', sa.text('lower(keyword)')],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_keyword_watch_company_lower', table_name='keyword_watches')
    op.drop_index('ix_keyword_watches_company_id', table_name='keyword_watches')
    op.drop_table('keyword_watches')
