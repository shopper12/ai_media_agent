import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build


SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
PUBLISH_ASSETS_SHEET_NAME = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
OVERWRITE_PUBLISH_ASSETS = os.environ.get("OVERWRITE_PUBLISH_ASSETS", "false").lower() == "true"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SOURCE_HEADERS = [
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
    "FinalOwnerDecision",
    "PublishChannel",
    "PublishStatus",
    "Notes",
]

ASSET_HEADERS = [
    "AssetId",
    "ContentId",
    "AssetType",
    "PublishChannel",
    "Title",
    "Body",
    "Caption",
    "Tags",
    "Checklist",
    "RiskNotice",
    "GeneratedAt",
    "AssetStatus",
]


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_sheet_id(service, sheet_name):
    meta = service.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("title") == sheet_name:
            return props.get("sheetId")
    return None


def ensure_sheet(service, sheet_name, headers):
    if get_sheet_id(service, sheet_name) is None:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute()
    current = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!A1:{chr(ord('A') + len(headers) - 1)}1",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if not current or current[0][: len(headers)] != headers:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()


def get_source_rows(service):
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1:X1000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if not values:
        return [], []
    headers = values[0]
    rows = []
    for index, row in enumerate(values[1:], start=2):
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        record["_row_number"] = index
        rows.append(record)
    return headers, rows


def get_existing_asset_keys(service):
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{PUBLISH_ASSETS_SHEET_NAME}!A1:L5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if len(values) <= 1:
        return set()
    headers = values[0]
    keys = set()
    for row in values[1:]:
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        if record.get("ContentId") and record.get("AssetType"):
            keys.add((record["ContentId"], record["AssetType"]))
    return keys


def normalize_decision(value):
    return str(value or "").strip().upper()


def split_channels(value):
    raw = str(value or "").replace("/", ",").replace(";", ",")
    channels = [part.strip() for part in raw.split(",") if part.strip()]
    return channels or ["Blog"]


def build_prompt(row, channel):
    return f"""너는 한국어 콘텐츠 발행 편집자다. 아래 초안을 {channel} 채널에 바로 올릴 수 있는 발행용 산출물로 재작성해라.

ContentId: {row.get('ContentId', '')}
Category: {row.get('Category', '')}
Original Title: {row.get('Title', '')}
DraftHook: {row.get('DraftHook', '')}
DraftBody: {row.get('DraftBody', '')}
DraftCTA: {row.get('DraftCTA', '')}
RiskFlag: {row.get('RiskFlag', '')}
RiskReviewStatus: {row.get('RiskReviewStatus', '')}
Notes: {row.get('Notes', '')}

반드시 JSON만 반환해라. 마크다운 코드블록은 쓰지 마라.
{{
  "Title": "...",
  "Body": "...",
  "Caption": "...",
  "Tags": "태그1, 태그2, 태그3",
  "Checklist": "발행 전 확인사항 3~5개",
  "RiskNotice": "필수 고지문 또는 주의문"
}}

규칙:
1. 한국어로 작성한다.
2. {channel} 채널에 맞게 길이와 형식을 조정한다.
3. 수익 보장, 치료 보장, 과장 표현은 금지한다.
4. 제휴 가능성이 있으면 제휴 고지를 유지한다.
5. 가격·도구명·최신 기능은 발행 전 확인 필요 문구를 넣는다.
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
            "Title": "",
            "Body": text,
            "Caption": "",
            "Tags": "",
            "Checklist": "JSON parsing failed. Review manually.",
            "RiskNotice": "REVIEW_REQUIRED",
        }


def append_assets(service, asset_rows):
    if not asset_rows:
        print("no publish assets to append")
        return
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{PUBLISH_ASSETS_SHEET_NAME}!A:L",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": asset_rows},
    ).execute()
    print(f"appended publish assets: {len(asset_rows)}")


def update_source_publish_status(service, source_rows):
    for row in source_rows:
        row_number = row["_row_number"]
        merged = {header: row.get(header, "") for header in SOURCE_HEADERS}
        merged["PublishStatus"] = "ASSETS_READY"
        values = [[merged.get(header, "") for header in SOURCE_HEADERS]]
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A{row_number}:X{row_number}",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()


def main():
    service = sheets_service()
    ensure_sheet(service, PUBLISH_ASSETS_SHEET_NAME, ASSET_HEADERS)
    _, source_rows = get_source_rows(service)
    existing_keys = get_existing_asset_keys(service)

    ready_rows = [
        r for r in source_rows
        if normalize_decision(r.get("FinalOwnerDecision")) == "APPROVE"
        and str(r.get("PublishStatus", "")).strip().upper() in {"READY_TO_PUBLISH", "ASSETS_READY"}
        and str(r.get("FinalStatus", "")).strip().upper() == "DRAFT_READY"
    ]

    asset_rows = []
    updated_source_rows = []
    generated_at = now_kst()

    for row in ready_rows:
        channels = split_channels(row.get("PublishChannel"))
        row_generated = False
        for channel in channels:
            asset_type = channel.strip()
            key = (row.get("ContentId", ""), asset_type)
            if key in existing_keys and not OVERWRITE_PUBLISH_ASSETS:
                print(f"skip existing asset: {key[0]} / {key[1]}")
                continue
            prompt = build_prompt(row, channel)
            asset = call_gemini(prompt)
            asset_id = f"ASSET-{row.get('ContentId', '')}-{asset_type}".replace(" ", "_")
            asset_rows.append([
                asset_id,
                row.get("ContentId", ""),
                asset_type,
                channel,
                asset.get("Title", ""),
                asset.get("Body", ""),
                asset.get("Caption", ""),
                asset.get("Tags", ""),
                asset.get("Checklist", ""),
                asset.get("RiskNotice", ""),
                generated_at,
                "ASSET_READY",
            ])
            row_generated = True
            print(f"generated asset: {row.get('ContentId')} / {channel}")
        if row_generated:
            updated_source_rows.append(row)

    append_assets(service, asset_rows)
    update_source_publish_status(service, updated_source_rows)
    print("publish asset generation complete")


if __name__ == "__main__":
    main()
