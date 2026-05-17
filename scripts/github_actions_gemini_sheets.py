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
HEADERS = [
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


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_rows(service):
    rng = f"{SHEET_NAME}!A1:T1000"
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=rng,
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if not values:
        return []
    headers = values[0]
    rows = []
    for index, row in enumerate(values[1:], start=2):
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        record["_row_number"] = index
        rows.append(record)
    return rows


def build_prompt(row):
    return f"""너는 한국어 콘텐츠 초안 작성자다. 아래 승인된 콘텐츠 후보를 바탕으로 쇼츠와 블로그에 모두 쓸 수 있는 초안을 작성해라.

ContentId: {row.get('ContentId', '')}
Category: {row.get('Category', '')}
Title: {row.get('Title', '')}
Format: {row.get('Format', '')}
RiskFlag: {row.get('RiskFlag', '')}
CTA: {row.get('CTA', '')}

출력 형식은 반드시 아래 JSON만 반환해라. 마크다운 코드블록은 쓰지 마라.
{{
  "DraftHook": "...",
  "DraftBody": "...",
  "DraftCTA": "...",
  "RiskReviewStatus": "LOW_RISK 또는 DISCLOSURE_REQUIRED",
  "FinalStatus": "DRAFT_READY"
}}

요구사항:
1. 한국어로 작성한다.
2. 과장 수익 보장 표현은 금지한다.
3. 제휴 가능성이 있으면 고지 문구를 포함한다.
4. 실무자가 바로 읽고 쓸 수 있게 구체적으로 작성한다.
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
    data = response.json()
    text = data["candidates"][0]["content"]["parts"][0]["text"]
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
            "RiskReviewStatus": "REVIEW_REQUIRED",
            "FinalStatus": "DRAFT_READY_PARSE_FAILED",
        }


def update_row(service, row, draft):
    row_number = row["_row_number"]
    merged = {header: row.get(header, "") for header in HEADERS}
    merged["DraftHook"] = draft.get("DraftHook", "")
    merged["DraftBody"] = draft.get("DraftBody", "")
    merged["DraftCTA"] = draft.get("DraftCTA", "")
    merged["RiskReviewStatus"] = draft.get("RiskReviewStatus", "REVIEW_REQUIRED")
    merged["GeneratedAt"] = now_kst()
    merged["FinalStatus"] = draft.get("FinalStatus", "DRAFT_READY")
    values = [[merged.get(header, "") for header in HEADERS]]
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A{row_number}:T{row_number}",
        valueInputOption="USER_ENTERED",
        body={"values": values},
    ).execute()


def main():
    service = sheets_service()
    rows = get_rows(service)
    approved = [r for r in rows if r.get("OwnerDecision") == "APPROVE"]
    print(f"approved rows: {len(approved)}")
    for row in approved:
        if row.get("FinalStatus") == "DRAFT_READY":
            print(f"skip already ready: {row.get('ContentId')}")
            continue
        prompt = build_prompt(row)
        draft = call_gemini(prompt)
        update_row(service, row, draft)
        print(f"updated: {row.get('ContentId')}")


if __name__ == "__main__":
    main()
