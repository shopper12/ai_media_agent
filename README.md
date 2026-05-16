# AI Media Agent

목표: 사용자는 매주 승인/보류/삭제만 하고, AI agent가 고수익 콘텐츠 주제 선정·제작·검수·보고를 수행하는 자동화 골격.

현재 버전은 **mock mode**다. OpenAI API 키, YouTube API 키, Google Sheets 연결 없이 n8n workflow 구조와 승인 큐를 먼저 확인한다.

---

## 0. 전제

Docker `hello-world`가 성공한 상태여야 한다.

```powershell
docker run --rm hello-world
```

---

## 1. 설치 위치

이 패키지 내용을 아래 폴더에 복사한다.

```powershell
C:\codetest\ai_media_agent
```

이미 같은 폴더가 있으면 기존 파일 백업 후 덮어쓴다.

---

## 2. n8n 실행

PowerShell에서:

```powershell
cd C:\codetest\ai_media_agent
.\scripts\start.ps1
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

---

## 4. mock 승인 큐 대시보드 생성

PowerShell:

```powershell
cd C:\codetest\ai_media_agent
.\scripts\generate-mock-dashboard.ps1
```

생성 파일:

```text
data/approval_queue.csv
data/approval_queue.json
data/dashboard.html
data/weekly_report.md
```

브라우저에서 `data/dashboard.html`을 열어 승인 큐를 확인한다.

---

## 5. 네가 할 일

승인 큐의 `OwnerDecision`에 아래 중 하나만 입력한다.

```text
APPROVE
HOLD
DELETE
```

---

## 6. 오류 로그

```powershell
cd C:\codetest\ai_media_agent
.\scripts\logs.ps1
```

---

## 7. 중지

```powershell
cd C:\codetest\ai_media_agent
.\scripts\stop.ps1
```

---

## 8. 현재 범위

현재 mock mode는 다음만 수행한다.

- 고수익 주제 mock scoring
- 콘텐츠 초안 mock generation
- AI 검수 mock flagging
- 승인 큐 생성
- 주간 보고서 생성

실제 외부 API 연결은 다음 단계다.

- OpenAI API
- YouTube API
- Google Sheets API
- Telegram Bot
- 제휴 링크 데이터
