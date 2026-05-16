# n8n Workflow JSON Import 방법

이 JSON 파일들은 PowerShell에서 실행하는 파일이 아니다. 브라우저로 열린 n8n 화면 안에서 불러오는 workflow 파일이다.

## 1. 먼저 n8n 실행

PowerShell:

```powershell
cd C:\codetest\ai_media_agent
copy .env.example .env
docker compose up -d
```

브라우저에서 접속:

```text
http://localhost:5678
```

## 2. n8n에서 import 위치

1. `http://localhost:5678` 접속
2. 최초 접속이면 n8n 계정 생성
3. 왼쪽 메뉴에서 `Workflows` 클릭
4. 우측 상단 또는 메뉴에서 `Import from File` / `Import workflow` 선택
5. 아래 JSON 파일을 하나씩 선택해서 import

```text
C:\codetest\ai_media_agent\n8n\workflows\01_mock_ai_tools_topic_scoring.json
C:\codetest\ai_media_agent\n8n\workflows\02_mock_content_approval_queue.json
C:\codetest\ai_media_agent\n8n\workflows\03_mock_weekly_report.json
```

## 3. import 후 실행

각 workflow를 열고:

```text
Execute workflow
```

버튼을 누른다.

## 4. 정상 결과

- `01_mock_ai_tools_topic_scoring`은 AI툴 주제 후보 3개를 출력한다.
- `02_mock_content_approval_queue`는 승인 큐 mock 데이터를 출력한다.
- `03_mock_weekly_report`는 주간보고 mock 데이터를 출력한다.

## 5. 현재 상태

- API 키 없이 돌아가는 mock mode다.
- 실제 OpenAI API, YouTube API, Google Sheets API는 다음 단계에서 credentials를 붙인다.
