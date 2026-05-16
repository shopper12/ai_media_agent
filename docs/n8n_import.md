# n8n Workflow JSON Import 방법

1. 브라우저에서 `http://localhost:5678` 접속
2. 최초 접속이면 n8n 계정 생성
3. 왼쪽 메뉴에서 `Workflows` 선택
4. `Import from File` 또는 `Import workflow` 선택
5. 아래 파일을 하나씩 import
   - `n8n/workflows/01_mock_market_research.json`
   - `n8n/workflows/02_mock_content_generation.json`
   - `n8n/workflows/03_mock_weekly_report.json`
6. 각 workflow를 열고 `Execute workflow` 실행
7. 실행 결과에서 mock topic, content draft, weekly report가 나오면 정상

## 현재 상태

- API 키 없이 돌아가는 mock mode다.
- 실제 OpenAI API, YouTube API, Google Sheets API는 다음 단계에서 credentials를 붙인다.
