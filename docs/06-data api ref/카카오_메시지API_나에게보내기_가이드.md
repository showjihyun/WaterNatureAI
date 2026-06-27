# 카카오톡 "나에게 보내기" 테스트 가이드 (사업자등록 불필요)

> 목적: **사업자등록 없이** WaterNature 추천을 **본인 카카오톡으로 실제 발송**해 보는 테스트 경로.
> 프로덕션 일일 발송(알림톡, SOLAPI)과는 **별개 채널**입니다(아래 §0 비교).

---

## 0. 왜 이 방법인가 — 알림톡 vs 메시지 API

| 구분 | **알림톡** (프로덕션, SOLAPI) | **메시지 API "나에게 보내기"** (테스트) |
|---|---|---|
| 사업자등록 | **필수** (비즈채널·발신프로필·템플릿 심사) | **불필요** ✅ |
| 수신 대상 | 모든 고객(전화번호) | **본인(나)** + 앱 팀원으로 등록한 테스트 친구 |
| 준비물 | SOLAPI 키 · pfId · 승인 템플릿 | **Kakao Developers 앱 REST 키 + 카카오 로그인(OAuth)** |
| 심사 | 템플릿 심사 필요 | 나에게 보내기는 **무심사** |
| 용도 | 실제 서비스 발송 | 데모·내부 검증 |

핵심: **"나에게 보내기"는 검수 없이 본인에게 즉시 발송**되므로, 알림톡 심사를 기다리지 않고 실제 카카오톡 푸시 UX를 확인할 수 있습니다.

---

## 1. Kakao Developers 앱 만들기

1. <https://developers.kakao.com> 로그인(개인 카카오계정, 무료) → **내 애플리케이션 → 애플리케이션 추가하기**
   - 앱 이름: `WaterNature`(예) / 사업자명: 개인 이름으로 가능
2. 생성 후 **앱 키** 확인 → **REST API 키**를 사용합니다(아래 `{REST_API_KEY}`).
3. **앱 설정 → 플랫폼 → Web 플랫폼 등록**
   - 사이트 도메인: `http://localhost:3002` (로컬 테스트 기준)
4. **제품 설정 → 카카오 로그인 → 활성화 ON**
   - **Redirect URI 등록**: `http://localhost:3002/oauth/kakao/callback`
     (콜백 페이지가 없어도 됩니다 — 리다이렉트된 URL의 `code` 파라미터만 쓰면 됨)
5. **제품 설정 → 카카오 로그인 → 동의항목**
   - **"카카오톡 메시지 전송"(`talk_message`)** → **사용**으로 설정(선택 동의 권장)
   - ⚠️ 이 항목이 있어야 메모 API가 동작합니다.
6. (선택) **카카오 로그인 → 보안 → Client Secret**: 테스트는 **사용 안 함(OFF)** 권장.
   ON으로 켰다면 토큰 교환(§2-B)에 `client_secret` 파라미터를 추가해야 합니다.

---

## 2. 액세스 토큰 발급 (`talk_message` 권한 포함)

메모 API는 **사용자 액세스 토큰**(scope=`talk_message`)이 필요합니다.

### 2-A. 인가 코드 받기 (브라우저)

아래 URL을 브라우저 주소창에 입력 → 카카오 로그인·동의 →
`Redirect URI`로 `?code=...` 가 붙어 돌아옵니다. 그 **`code` 값**을 복사하세요.

```
https://kauth.kakao.com/oauth/authorize?client_id={REST_API_KEY}&redirect_uri=http://localhost:3002/oauth/kakao/callback&response_type=code&scope=talk_message
```

> 콜백 페이지가 404여도 무방 — 주소창의 `...callback?code=XXXX` 에서 `XXXX`만 쓰면 됩니다.

### 2-B. 인가 코드 → 액세스 토큰 교환

```bash
curl -X POST "https://kauth.kakao.com/oauth/token" \
  -H "Content-Type: application/x-www-form-urlencoded;charset=utf-8" \
  -d "grant_type=authorization_code" \
  -d "client_id={REST_API_KEY}" \
  -d "redirect_uri=http://localhost:3002/oauth/kakao/callback" \
  -d "code={위에서_받은_CODE}"
```

응답:

```json
{
  "token_type": "bearer",
  "access_token": "XXXXX",        // ← 이걸로 메시지 발송
  "expires_in": 21599,            // 약 6시간
  "refresh_token": "YYYYY",       // 약 2개월 (만료 시 재발급용)
  "scope": "talk_message"
}
```

- **access_token 수명 ≈ 6시간** → 만료되면 refresh로 재발급:
  ```bash
  curl -X POST "https://kauth.kakao.com/oauth/token" \
    -d "grant_type=refresh_token" -d "client_id={REST_API_KEY}" \
    -d "refresh_token={REFRESH_TOKEN}"
  ```

---

## 3. 나에게 보내기 호출

**Endpoint**: `POST https://kapi.kakao.com/v2/api/talk/memo/default/send`
**Header**: `Authorization: Bearer {ACCESS_TOKEN}`
**Body(form)**: `template_object={JSON}` (URL 인코딩)
**성공 응답**: `{ "result_code": 0 }` → **"나와의 채팅"에 메시지 도착**

### 3-A. 텍스트 템플릿 (가장 간단, text ≤ 200자)

```bash
curl -X POST "https://kapi.kakao.com/v2/api/talk/memo/default/send" \
  -H "Authorization: Bearer {ACCESS_TOKEN}" \
  --data-urlencode 'template_object={
    "object_type": "text",
    "text": "[WaterNature] 오늘의 맞춤 공고 3건이 도착했어요.\n1. AI허브 학습용데이터 (적합도 51·NTIS)\n2. 임상시험 Private LLM (적합도 48·7,272만원)\n3. 벤치마크 AI 모델 평가 (적합도 46·3.2억원)",
    "link": {
      "web_url": "http://localhost:3002/dashboard",
      "mobile_web_url": "http://localhost:3002/dashboard"
    },
    "button_title": "추천 보러가기"
  }'
```

### 3-B. 리스트 템플릿 (일일 추천 목록에 적합)

```json
{
  "object_type": "list",
  "header_title": "오늘의 맞춤 공고 3건",
  "header_link": { "web_url": "http://localhost:3002/dashboard", "mobile_web_url": "http://localhost:3002/dashboard" },
  "contents": [
    { "title": "AI허브 학습용데이터(추론용) 사업 재공고", "description": "적합도 51 · 과기정통부 · NTIS",
      "link": { "web_url": "http://localhost:3002/dashboard", "mobile_web_url": "http://localhost:3002/dashboard" } },
    { "title": "임상시험 통합플랫폼 Private LLM 고도화", "description": "적합도 48 · 7,272만원 · D+2",
      "link": { "web_url": "http://localhost:3002/dashboard", "mobile_web_url": "http://localhost:3002/dashboard" } }
  ],
  "buttons": [
    { "title": "전체 보기", "link": { "web_url": "http://localhost:3002/dashboard", "mobile_web_url": "http://localhost:3002/dashboard" } }
  ]
}
```

### 3-C. Python (httpx) 예시

```python
import json, httpx

ACCESS_TOKEN = "..."  # §2에서 발급
template = {
    "object_type": "text",
    "text": "[WaterNature] 오늘의 맞춤 공고 3건이 도착했어요 📡",
    "link": {"web_url": "http://localhost:3002/dashboard",
             "mobile_web_url": "http://localhost:3002/dashboard"},
    "button_title": "추천 보러가기",
}
resp = httpx.post(
    "https://kapi.kakao.com/v2/api/talk/memo/default/send",
    headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
    data={"template_object": json.dumps(template, ensure_ascii=False)},
    timeout=10,
)
print(resp.status_code, resp.json())  # 기대: 200 {'result_code': 0}
```

---

## 4. WaterNature 추천을 카카오로 (연동 스케치 — 선택)

지금 만들어 둔 미리보기 데이터(`GET /settings/notification/preview`)를 그대로 메모 API로 쏘면 됩니다.

```
[프론트] "카카오 연결" 버튼
   → kauth.../authorize?scope=talk_message       (OAuth 시작)
   → /oauth/kakao/callback?code=...              (콜백)
[백엔드] POST /notifications/kakao/connect {code}
   → token 교환 → users.kakao_access/refresh_token 저장(crypto.py 암호화)
[백엔드] POST /notifications/kakao/test-send
   → build_briefing_preview(company) → list 템플릿 변환
   → memo/default/send (만료 시 refresh 후 재시도)
   → "나와의 채팅"에 도착
```

- 토큰은 **암호화 저장**(`app/core/crypto.py` Fernet 재사용 — LLM 키·빌링키와 동일 패턴).
- 만료(6h) 대비 **refresh_token으로 자동 재발급** 래퍼 필요.
- 이건 **개발/데모용 채널**입니다. 실제 고객 일일 발송은 그대로 **알림톡(SOLAPI)** 경로 유지.

> 진행 원하시면 위 3개 엔드포인트 + "카카오 연결" 버튼을 붙여 드립니다. 필요한 건 **REST API 키 하나**뿐입니다.

---

## 5. 한계 · 주의

- **나에게 보내기만 무심사.** 타인(실고객)에게 보내려면 친구 메시지 API(`/v1/api/talk/friends/message/...`) + **친구 동의 + 앱 검수**가 필요하고, 사실상 사업자/비즈앱이 요구됩니다.
- **친구에게 테스트**: 앱 설정의 **팀원**으로 등록한 카카오 계정에게는 검수 전에도 발송 가능(소수 테스트용).
- **토큰 만료**: access_token 약 6시간 → refresh_token으로 재발급.
- **발송 쿼터**: 앱 단위 일일 호출 한도 존재(개발 단계는 소량).
- **템플릿 제약**: text 템플릿 `text` ≤ 200자, list `contents` 최대 개수 제한 등 — 공식 문서의 기본 템플릿 스펙 참고.
- **채널 차이**: 메모 API = 개인 "나와의 채팅" 메시지. 알림톡(비즈 채널 발신)과 디자인·발신주체가 다릅니다.

---

## 참고 링크

- 카카오 메시지(기본 템플릿) — 나에게 보내기: <https://developers.kakao.com/docs/latest/ko/message/rest-api#default-template-msg-me>
- 카카오 로그인(REST API) 토큰 받기: <https://developers.kakao.com/docs/latest/ko/kakaologin/rest-api>
- 기본 템플릿(피드/리스트/텍스트 등) 오브젝트: <https://developers.kakao.com/docs/latest/ko/message/message-template>
