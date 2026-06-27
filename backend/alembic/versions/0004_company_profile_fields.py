"""0004 company profile fields (services/technologies/customers/certifications)

온보딩 2·3단계 입력(주요 서비스·기술스택·고객·인증)을 영속화 → Company Brain
LLM 추출 입력으로 사용. 모두 JSONB·nullable(비파괴적 ADD COLUMN).

Revision ID: 0004_company_profile
Revises: 0003_app_settings
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0004_company_profile'
down_revision = '0003_app_settings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('services', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('companies', sa.Column('technologies', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('companies', sa.Column('customers', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('companies', sa.Column('certifications', postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'certifications')
    op.drop_column('companies', 'customers')
    op.drop_column('companies', 'technologies')
    op.drop_column('companies', 'services')
