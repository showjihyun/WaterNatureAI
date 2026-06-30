"""0011 표준 업종(KSIC) 축 — opportunities.industry + companies.capable_industries

공고를 한국표준산업분류(KSIC) 대분류로 분류한 표준 업종 코드(예: 'J','F','ETC').
회사는 수행 가능 업종(코드 리스트). 둘 다 비파괴적(nullable). 기존 데이터 분류는
별도 백필 스크립트(scripts/backfill_industry.py)로 채운다.

Revision ID: 0011_ksic_industry
Revises: 0010_deadline_reminder
Create Date: 2026-06-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0011_ksic_industry'
down_revision = '0010_deadline_reminder'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('opportunities', sa.Column('industry', sa.String(length=8), nullable=True))
    op.create_index('ix_opportunities_industry', 'opportunities', ['industry'])
    op.add_column(
        'companies',
        sa.Column('capable_industries', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('companies', 'capable_industries')
    op.drop_index('ix_opportunities_industry', table_name='opportunities')
    op.drop_column('opportunities', 'industry')
