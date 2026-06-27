"""0002 company capability fields

companies 테이블에 수행 역량 3컬럼 추가 (수행 가능성 판단 엔진용).
모두 nullable — 기존 데이터 무손상(비파괴적 ADD COLUMN).

Revision ID: 0002_company_capability
Revises: cf4a09a21225
Create Date: 2026-06-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0002_company_capability'
down_revision = 'cf4a09a21225'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('tech_level', sa.SmallInteger(), nullable=True))
    op.add_column('companies', sa.Column('max_project_budget', sa.BigInteger(), nullable=True))
    op.add_column('companies', sa.Column('capable_categories', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'capable_categories')
    op.drop_column('companies', 'max_project_budget')
    op.drop_column('companies', 'tech_level')
