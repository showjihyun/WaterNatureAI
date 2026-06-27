"""FastAPI TestClient로 /recommendations/today 응답 확인."""
import os, sys, json
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

os.environ["EMBEDDING_PROVIDER"] = "bge"
os.environ["MATCH_THRESHOLD"] = "5"

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=True)

# 이메일 도메인을 유효한 것으로 변경
TEST_EMAIL = "e2e@example.com"
TEST_PW = "TestPass123!"
COMPANY_NAME = "(주)테스트공간정보"

# 기존 계정으로 로그인 (이미 create됨)
# 실제 저장된 이메일 사용
from app.db.base import SessionLocal
from app.db.models.accounts import User, Company
from app.core.security import create_access_token
from sqlalchemy import select

db = SessionLocal()
company = db.scalar(select(Company).where(Company.name == COMPANY_NAME))
user = db.scalar(select(User).where(User.company_id == company.id))
db.close()

print(f"Company: {company.name}, id={company.id}")
print(f"User: {user.email}, id={user.id}")

# 직접 access token 발급 (이메일 검증 우회)
access_token = create_access_token(
    user_id=user.id, company_id=user.company_id, role=user.role
)
headers = {"Authorization": f"Bearer {access_token}"}

print("\n=== GET /api/v1/recommendations/today ===")
resp = client.get("/api/v1/recommendations/today", headers=headers)
print(f"Status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"Items: {len(data)}")
    print(json.dumps(data, ensure_ascii=False, indent=2))
else:
    print(f"Error: {resp.text}")

print("\n=== Schema Analysis ===")
if resp.status_code == 200 and data:
    item = data[0]
    fields = list(item.keys())
    print(f"Response fields: {fields}")
    has_url = "detail_url" in fields
    print(f"detail_url in response: {has_url}")
    print(f"reasons field: {item.get('reasons')}")
    print(f"d_day field: {item.get('d_day')}")
    print(f"score field: {item.get('score')}")
print("Done.")
