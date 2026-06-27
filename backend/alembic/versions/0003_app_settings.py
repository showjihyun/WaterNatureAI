"""0003 app_settings (시스템 전역 key→JSONB)

멀티 LLM 공급자 런타임 선택 보관용. key='llm' 시드 1행 생성
(provider/model 기본값 = config). 제3자 API 키는 저장하지 않음(.env 전용).
비파괴적: 신규 테이블 추가만.

Revision ID: 0003_app_settings
Revises: 0002_company_capability
Create Date: 2026-06-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003_app_settings'
down_revision = '0002_company_capability'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'app_settings',
        sa.Column('key', sa.String(length=64), primary_key=True, nullable=False),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()'), nullable=False),
    )
    # 기본 LLM 설정 시드 (Anthropic Claude Opus 4.8). 키는 .env에서 읽음.
    app_settings = sa.table(
        'app_settings',
        sa.column('key', sa.String),
        sa.column('value', postgresql.JSONB(astext_type=sa.Text())),
    )
    op.bulk_insert(app_settings, [
        {'key': 'llm', 'value': {'provider': 'anthropic', 'model': 'claude-opus-4-8'}},
    ])


def downgrade() -> None:
    op.drop_table('app_settings')
