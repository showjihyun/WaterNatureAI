"""0005 company document fields (document_text/document_filename)

FR-004 회사소개서 PDF 파싱: 업로드 PDF에서 추출한 텍스트를 영속화 →
/company/brain 재실행 시 Company Brain LLM 추출 입력(document_text)으로 재사용.
모두 nullable(비파괴적 ADD COLUMN).

Revision ID: 0005_company_document
Revises: 0004_company_profile
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa

revision = '0005_company_document'
down_revision = '0004_company_profile'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('document_text', sa.Text(), nullable=True))
    op.add_column('companies', sa.Column('document_filename', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('companies', 'document_filename')
    op.drop_column('companies', 'document_text')
