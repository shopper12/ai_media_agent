import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE_HEADERS = [
    "ContentId",
    "TopicId",
    "Category",
    "ExpectedProfitScore",
    "Title",
    "Format",
    "RiskFlag",
    "AIReviewScore",
    "ApprovalStatus",
    "OwnerDecision",
    "CTA",
    "CreatedAt",
    "PublishedAt",
    "ResultUrl",
    "DraftHook",
    "DraftBody",
    "DraftCTA",
    "RiskReviewStatus",
    "GeneratedAt",
    "FinalStatus",
]
EXTRA_HEADERS = [
    "DraftFormat",
    "ThumbnailText",
    "OnScreenOverlays",
    "SEOKeywords",
]
HEADERS = BASE_HEADERS + EXTRA_HEADERS


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1:AZ1000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service):
    values = get_values(service)
    headers = values[0] if values else []
    for header in HEADERS:
        if header not in headers:
            headers.append(header)
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()
    return headers


def get_rows(service, headers):
    values = get_values(service)
    if len(values) <= 1:
        return []
    rows = []
    for index, row in enumerate(values[1:], start=2):
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        record["_row_number"] = index
        rows.append(record)
    return rows


def draft_kind(row):
    fmt = str(row.get("Format", "")).lower()
    cta = str(row.get("CTA", "")).lower()
    is_shorts = "short" in fmt or "youtube_shorts" in cta or "youtube shorts" in cta
    is_blog = "blog" in fmt or "naver_blog" in cta or "naver blog" in cta
    if is_shorts and not is_blog:
        return "shorts"
    if is_blog and not is_shorts:
        return "blog"
    return "both"


def build_prompt(row):
    kind = draft_kind(row)
    base = f"""ContentId: {row.get('ContentId', '')}
Category: {row.get('Category', '')}
Title: {row.get('Title', '')}
RiskFlag: {row.get('RiskFlag', '')}
CTA: {row.get('CTA', '')}
"""
    common_rules = """공통 품질 규칙:
- '안녕하세요', '오늘은 알아볼게요', 도구명 단순 나열로 시작하지 않는다.
- 제목과 첫 문단에는 독자가 바로 판단할 수 있는 선택 기준, 금액, 시간, 체크리스트 중 하나를 넣는다.
- 한국 독자 기준의 현실 맥락을 넣는다. 예: 직장인, 월급, 전세, 청약, 통신비, 카드, 이직, 면접.
- 과장어와 보장 표현을 피한다. 예: 폭발, 200%, 완벽, 무조건, 보장.
- 단순 추천이 아니라 '누구에게 맞고, 누구에게 안 맞는지'를 나눈다.
- 정보가 시점에 따라 바뀌는 주제는 최신 확인 필요 문장을 넣는다.
"""
    if kind == "shorts":
        return f"""너는 한국어 YouTube Shorts 대본 편집자다. 아래 승인 주제를 60초 이내 쇼츠 대본으로 만든다.

{base}
{common_rules}
쇼츠 규칙:
1. 첫 2초는 문제 또는 착각을 바로 찌른다.
2. 흐름은 문제 → 반전 → 선택 기준 2~3개 → 저장할 이유 → CTA 순서다.
3. 각 대사는 짧은 구어체로 쓴다.
4. 자막은 화면에 한 번에 읽히도록 짧게 쓴다.
5. 수익, 건강, 금융, 부동산 주제는 개인차와 최신 확인 필요 문장을 포함한다.

반드시 JSON만 반환해라. 마크다운 코드블록은 금지한다.
{{
  "DraftHook": "0-2초 대사",
  "DraftBody": "3-50초 전체 스크립트. 타임스탬프 포함",
  "DraftCTA": "50-60초 가치 제안형 CTA",
  "ThumbnailText": "썸네일 메인 텍스트 3-5단어",
  "OnScreenOverlays": ["자막1", "자막2", "자막3"],
  "SEOKeywords": [],
  "RiskReviewStatus": "LOW_RISK 또는 DISCLOSURE_REQUIRED",
  "FinalStatus": "DRAFT_READY"
}}
"""
    if kind == "blog":
        return f"""너는 한국어 네이버 블로그 SEO 편집자다. 아래 승인 주제로 검색 유입과 저장 가치를 모두 갖춘 블로그 초안을 작성한다.

{base}
{common_rules}
블로그 규칙:
1. 제목은 핵심 키워드를 앞에 배치하고 30자 이내로 쓴다.
2. 구조는 공감형 서론 → 핵심 비교표 → 상황별 선택 기준 → 추천 결론 → CTA → 면책고지 순서다.
3. 본문은 1,800자 이상으로 쓴다.
4. 비교표에는 최소 4개 항목과 '추천 대상/비추천 대상'을 넣는다.
5. 제휴 링크 플레이스홀더 [AFFILIATE_LINK]를 1회 넣는다.
6. 가격, 금리, 제도, 기능은 발행 전 최신 확인 필요 문장을 넣는다.

반드시 JSON만 반환해라. 마크다운 코드블록은 금지한다.
{{
  "DraftHook": "제목 + 첫 문단",
  "DraftBody": "본문 전체. 비교표 포함",
  "DraftCTA": "CTA 문구 + 면책고지",
  "ThumbnailText": "",
  "OnScreenOverlays": [],
  "SEOKeywords": ["키워드1", "키워드2", "키워드3"],
  "RiskReviewStatus": "LOW_RISK 또는 DISCLOSURE_REQUIRED",
  "FinalStatus": "DRAFT_READY"
}}
"""
    return f"""너는 한국어 멀티포맷 콘텐츠 편집자다. 아래 승인 주제로 Shorts와 Blog 양쪽에 쓸 수 있는 초안을 만든다.

{base}
{common_rules}
멀티포맷 규칙:
1. DraftHook은 Shorts 첫 2초 훅으로도 작동해야 한다.
2. DraftBody 앞부분에는 60초 이하 쇼츠 대본을 타임스탬프로 넣고, 뒤에는 블로그용 본문 초안을 넣는다.
3. 블로그 파트에는 비교표, 상황별 선택 기준, 추천 결론, CTA, 면책고지를 포함한다.
4. 제휴형 콘텐츠면 [AFFILIATE_LINK]를 1회 넣는다.
5. 정보가 바뀌는 주제는 최신 확인 필요 문장을 포함한다.

반드시 JSON만 반환해라. 마크다운 코드블록은 금지한다.
{{
  "DraftHook": "0-2초 쇼츠 훅 겸 블로그 첫 문단",
  "DraftBody": "ShortsScript 섹션 + BlogDraft 섹션",
  "DraftCTA": "저장/링크/비교표 유도 CTA + 면책고지",
  "ThumbnailText": "썸네일 메인 텍스트 3-5단어",
  "OnScreenOverlays": ["자막1", "자막2", "자막3"],
  "SEOKeywords": ["키워드1", "키워드2", "키워드3"],
  "RiskReviewStatus": "LOW_RISK 또는 DISCLOSURE_REQUIRED",
  "FinalStatus": "DRAFT_READY"
}}
"""


def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    response = requests.post(
        url,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    response.raise_for_status()
    text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
    cleaned = text.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned.removeprefix("```json").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").strip()
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3].strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "DraftHook": "",
            "DraftBody": text,
            "DraftCTA": "",
            "ThumbnailText": "",
            "OnScreenOverlays": [],
            "SEOKeywords": [],
            "RiskReviewStatus": "REVIEW_REQUIRED",
            "FinalStatus": "DRAFT_READY_PARSE_FAILED",
        }


def update_row(service, headers, row, draft):
    row_number = row["_row_number"]
    merged = {header: row.get(header, "") for header in headers}
    merged["DraftFormat"] = draft_kind(row).upper()
    merged["DraftHook"] = draft.get("DraftHook", "")
    merged["DraftBody"] = draft.get("DraftBody", "")
    merged["DraftCTA"] = draft.get("DraftCTA", "")
    merged["ThumbnailText"] = draft.get("ThumbnailText", "")
    merged["OnScreenOverlays"] = json.dumps(draft.get("OnScreenOverlays", []), ensure_ascii=False)
    merged["SEOKeywords"] = json.dumps(draft.get("SEOKeywords", []), ensure_ascii=False)
    merged["RiskReviewStatus"] = draft.get("RiskReviewStatus", "REVIEW_REQUIRED")
    merged["GeneratedAt"] = now_kst()
    merged["FinalStatus"] = draft.get("FinalStatus", "DRAFT_READY")
    values = [[merged.get(header, "") for header in headers]]
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A{row_number}",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def main():
    service = sheets_service()
    headers = ensure_headers(service)
    rows = get_rows(service, headers)
    approved = [r for r in rows if str(r.get("OwnerDecision", "")).strip().upper() == "APPROVE"]
    print(f"approved rows: {len(approved)}")
    for row in approved:
        if str(row.get("FinalStatus", "")).strip().upper() == "DRAFT_READY":
            print(f"skip already ready: {row.get('ContentId')}")
            continue
        draft = call_gemini(build_prompt(row))
        update_row(service, headers, row, draft)
        print(f"updated: {row.get('ContentId')} | {draft_kind(row)}")


if __name__ == "__main__":
    main()
