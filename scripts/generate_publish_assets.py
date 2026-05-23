import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build


SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
PUBLISH_SHEET_NAME = os.environ.get("PUBLISH_SHEET_NAME", "publish_assets")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = [
    "ContentId",
    "Title",
    "Category",
    "PublishChannel",
    "BlogTitle",
    "BlogPost",
    "ShortsHook",
    "ShortsScript",
    "Caption",
    "Tags",
    "Disclosure",
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


def ensure_publish_sheet(service):
    if get_sheet_id(service, PUBLISH_SHEET_NAME) is not None:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": PUBLISH_SHEET_NAME}}}]},
    ).execute()


def get_rows(service):
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1:X1000",
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


def needs_disclosure(row):
    text = f"{row.get('RiskFlag', '')} {row.get('RiskReviewStatus', '')}".lower()
    return "affiliate" in text or "disclosure" in text


def disclosure_for(row):
    if not needs_disclosure(row):
        return ""
    return "Disclosure: This content may include affiliate or sponsored references. Review before publishing."


def select_rows(rows):
    selected = []
    for row in rows:
        final_owner = row.get("FinalOwnerDecision", "").strip().upper()
        publish_status = row.get("PublishStatus", "").strip().upper()
        final_status = row.get("FinalStatus", "").strip().upper()
        if final_owner != "APPROVE":
            continue
        if publish_status not in ("", "READY_TO_PUBLISH"):
            continue
        if final_status != "DRAFT_READY":
            continue
        selected.append(row)
    return selected


def build_blog_post(row, disclosure):
    parts = [
        row.get("DraftHook", "").strip(),
        row.get("DraftBody", "").strip(),
        row.get("DraftCTA", "").strip(),
        disclosure.strip(),
    ]
    return "\n\n".join(part for part in parts if part)


def build_shorts_script(row):
    title = row.get("Title", "").strip()
    hook = row.get("DraftHook", "").strip()
    cta = row.get("DraftCTA", "").strip() or row.get("CTA", "").strip()
    lines = [
        f"0:00-0:03 Hook: {hook or title}",
        f"0:03-0:12 Context: {title}",
        "0:12-0:25 Value: Show the main problem, the simple decision point, and the practical next step.",
        f"0:25-0:30 CTA: {cta}",
    ]
    return "\n".join(line for line in lines if not line.endswith(": "))


def build_caption(row):
    hook = row.get("DraftHook", "").strip()
    cta = row.get("DraftCTA", "").strip() or row.get("CTA", "").strip()
    return " ".join(part for part in [hook, cta] if part)


def build_tags(row):
    category = row.get("Category", "").strip()
    tags = [category, "productivity", "AI", "automation", "workflow"]
    return ", ".join(tag for tag in tags if tag)


def build_asset_rows(rows):
    generated_at = now_kst()
    assets = []
    for row in rows:
        disclosure = disclosure_for(row)
        assets.append([
            row.get("ContentId", ""),
            row.get("Title", ""),
            row.get("Category", ""),
            row.get("PublishChannel", ""),
            row.get("Title", ""),
            build_blog_post(row, disclosure),
            row.get("DraftHook", ""),
            build_shorts_script(row),
            build_caption(row),
            build_tags(row),
            disclosure,
            generated_at,
            "ASSET_READY",
        ])
    return assets


def write_assets(service, rows):
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{PUBLISH_SHEET_NAME}!A1:M1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS]},
    ).execute()
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{PUBLISH_SHEET_NAME}!A2:M1000",
        body={},
    ).execute()
    if not rows:
        print("no publish assets to write")
        return
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{PUBLISH_SHEET_NAME}!A2",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()
    print(f"publish assets updated: {len(rows)}")
    for row in rows:
        print(f"asset: {row[0]} | {row[3]} | {row[12]}")


def main():
    service = sheets_service()
    ensure_publish_sheet(service)
    rows = get_rows(service)
    approved = select_rows(rows)
    print(f"approved publish rows: {len(approved)}")
    assets = build_asset_rows(approved)
    write_assets(service, assets)


if __name__ == "__main__":
    main()
