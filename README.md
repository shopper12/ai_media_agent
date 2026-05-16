# AI Media Agent

목표: 사용자는 매주 승인/보류/거절만 하고, AI agent가 고수익 콘텐츠 주제 선정·제작·검수·보고를 수행하는 자동화 골격.

현재 버전은 **mock mode**다. OpenAI API 키, YouTube API 키, Google Sheets 연결 없이 n8n workflow 구조와 승인 큐를 먼저 확인한다.

---

## 0. 전제

Docker `hello-world`가 성공한 상태여야 한다.

```powershell
docker run --rm hello-world
```

---

## 1. 로컬로 받기

```powershell
cd C:\codetest
git clone https://github.com/shopper12/ai_media_agent.git
cd C:\codetest\ai_media_agent
```

이미 폴더가 있으면:

```powershell
cd C:\codetest\ai_media_agent
git pull
```

---

## 2. n8n 실행

```powershell
cd C:\codetest\ai_media_agent
copy .env.example .env
docker compose up -d
docker ps
```

정상 실행 후 브라우저에서:

```text
http://localhost:5678
```

---

## 3. n8n workflow import

n8n 접속 후 아래 문서대로 workflow JSON을 import한다.

```text
docs/n8n_import.md
```

현재 업로드된 workflow:

```text
n8n/workflows/01_mock_ai_tools_topic_scoring.json
n8n/workflows/02_mock_content_approval_queue.json
n8n/workflows/03_mock_weekly_report.json
```

---

## 4. 승인 큐

기본 승인 큐 템플릿:

```text
data/approval_queue_template.csv
```

OwnerDecision 값은 아래 중 하나로만 쓴다.

```text
APPROVE
HOLD
REJECT
```

---

## 5. 로그 확인

```powershell
cd C:\codetest\ai_media_agent
docker compose ps
docker compose logs n8n --tail=150
```

---

## 6. 중지

```powershell
cd C:\codetest\ai_media_agent
docker compose down
```

---

## 7. 현재 범위

현재 mock mode는 다음만 수행한다.

- AI툴/SaaS 주제 mock scoring
- 콘텐츠 승인 큐 mock generation
- 주간 보고서 mock generation
- approval queue 템플릿 제공

실제 외부 API 연결은 다음 단계다.

- OpenAI API
- YouTube API
- Google Sheets API
- Telegram Bot
- 제휴 링크 데이터
