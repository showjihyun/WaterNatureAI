"""0006 pursuits (진행 관리 파이프라인)

회사가 추적 중인 공고 + 단계(reviewing/preparing/submitted/done). (company, opp) 유니크.
saved(관심)와 별개 테이블. 비파괴적 CREATE TABLE.

Revision ID: 0006_pursuits
Revises: 0005_company_document
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0006_pursuits'
down_revision = '0005_company_document'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pursuits',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('opportunity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('stage', sa.String(length=20), nullable=False, server_default='reviewing'),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['opportunity_id'], ['opportunities.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'opportunity_id', name='uq_pursuit_company_opp'),
    )
    op.create_index('ix_pursuits_company', 'pursuits', ['company_id'])


def downgrade() -> None:
    op.drop_index('ix_pursuits_company', table_name='pursuits')
    op.drop_table('pursuits')
