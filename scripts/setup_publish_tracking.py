import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
LOG_SHEET = os.environ.get("PUBLISHED_LOG_SHEET_NAME", "published_log")
REPORT_SHEET = os.environ.get("PERFORMANCE_REPORT_SHEET_NAME", "performance_report")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

ASSET_TRACKING_COLUMNS = [
    "PublishDecision",
    "TargetUrl",
    "PublishedAt",
    "PerformanceCheckDate",
    "Views",
    "Clicks",
    "Revenue",
    "TrackingNotes",
]

LOG_HEADERS = [
    "LogId",
    "AssetId",
    "ContentId",
    "AssetType",
    "Title",
    "TargetUrl",
    "PublishedAt",
    "Views",
    "Clicks",
    "Revenue",
    "CTR",
    "RevenuePer1000Views",
    "LoggedAt",
    "Notes",
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


def ensure_sheet(service, sheet_name, headers=None):
    if get_sheet_id(service, sheet_name) is None:
        service.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute()
    if headers:
        current = service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!A1:Z1",
            valueRenderOption="FORMATTED_VALUE",
        ).execute().get("values", [])
        if not current or current[0][: len(headers)] != headers:
            service.spreadsheets().values().update(
                spreadsheetId=SPREADSHEET_ID,
                range=f"{sheet_name}!A1",
                valueInputOption="USER_ENTERED",
                body={"values": [headers]},
            ).execute()


def ensure_asset_tracking_columns(service):
    ensure_sheet(service, ASSETS_SHEET)
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:Z1",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    headers = values[0] if values else []
    changed = False
    for column in ASSET_TRACKING_COLUMNS:
        if column not in headers:
            headers.append(column)
            changed = True
    if changed:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
        print("asset tracking columns added")
    else:
        print("asset tracking columns already exist")


def main():
    service = sheets_service()
    ensure_asset_tracking_columns(service)
    ensure_sheet(service, LOG_SHEET, LOG_HEADERS)
    ensure_sheet(service, REPORT_SHEET)
    print(f"tracking setup complete: {now_kst()}")


if __name__ == "__main__":
    main()
