import json
import os
from collections import Counter, defaultdict
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
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()


def get_records(service, sheet_name, cell_range="A1:Z5000"):
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{sheet_name}!{cell_range}",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if not values:
        return [], []
    headers = values[0]
    records = []
    for index, row in enumerate(values[1:], start=2):
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        record["_row_number"] = index
        records.append(record)
    return headers, records


def to_float(value):
    try:
        return float(str(value or "0").replace(",", ""))
    except ValueError:
        return 0.0


def build_log_row(asset, existing_log_ids):
    asset_id = asset.get("AssetId", "") or f"ASSET-{asset.get('ContentId', '')}-{asset.get('AssetType', '')}"
    log_id = f"LOG-{asset_id}"
    if log_id in existing_log_ids:
        return None
    views = to_float(asset.get("Views"))
    clicks = to_float(asset.get("Clicks"))
    revenue = to_float(asset.get("Revenue"))
    ctr = clicks / views if views else 0
    rpm = revenue / views * 1000 if views else 0
    return [
        log_id,
        asset_id,
        asset.get("ContentId", ""),
        asset.get("AssetType", ""),
        asset.get("Title", ""),
        asset.get("TargetUrl", ""),
        asset.get("PublishedAt", ""),
        views,
        clicks,
        revenue,
        round(ctr, 4),
        round(rpm, 2),
        now_kst(),
        asset.get("TrackingNotes", ""),
    ]


def append_logs(service, rows):
    ensure_sheet(service, LOG_SHEET, LOG_HEADERS)
    if not rows:
        print("no new log rows")
        return
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{LOG_SHEET}!A:N",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    print(f"logged rows: {len(rows)}")


def build_report(log_records):
    total = len(log_records)
    views = sum(to_float(r.get("Views")) for r in log_records)
    clicks = sum(to_float(r.get("Clicks")) for r in log_records)
    revenue = sum(to_float(r.get("Revenue")) for r in log_records)
    ctr = clicks / views if views else 0
    rpm = revenue / views * 1000 if views else 0
    by_type = Counter(r.get("AssetType", "UNKNOWN") or "UNKNOWN" for r in log_records)
    revenue_by_type = defaultdict(float)
    for r in log_records:
        revenue_by_type[r.get("AssetType", "UNKNOWN") or "UNKNOWN"] += to_float(r.get("Revenue"))

    rows = [
        ["GeneratedAt", now_kst()],
        ["Published asset count", total],
        ["Total views", views],
        ["Total clicks", clicks],
        ["Total revenue", revenue],
        ["CTR", round(ctr, 4)],
        ["Revenue per 1000 views", round(rpm, 2)],
        [],
        ["AssetType", "Count", "Revenue"],
    ]
    for asset_type, count in by_type.most_common():
        rows.append([asset_type, count, round(revenue_by_type[asset_type], 2)])
    rows.extend([
        [],
        ["Top revenue assets", "Title", "Revenue", "Views", "Clicks", "TargetUrl"],
    ])
    top = sorted(log_records, key=lambda r: to_float(r.get("Revenue")), reverse=True)[:20]
    for r in top:
        rows.append([
            r.get("AssetId", ""),
            r.get("Title", ""),
            r.get("Revenue", ""),
            r.get("Views", ""),
            r.get("Clicks", ""),
            r.get("TargetUrl", ""),
        ])
    return rows


def write_report(service, report):
    ensure_sheet(service, REPORT_SHEET)
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{REPORT_SHEET}!A:Z",
        body={},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{REPORT_SHEET}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": report},
    ).execute()
    print("performance report updated")


def main():
    service = sheets_service()
    ensure_sheet(service, LOG_SHEET, LOG_HEADERS)
    _, assets = get_records(service, ASSETS_SHEET)
    _, logs = get_records(service, LOG_SHEET)
    existing_log_ids = {r.get("LogId", "") for r in logs if r.get("LogId")}

    new_logs = []
    for asset in assets:
        if str(asset.get("PublishDecision", "")).strip().upper() != "APPROVE":
            continue
        if not asset.get("TargetUrl"):
            continue
        row = build_log_row(asset, existing_log_ids)
        if row:
            new_logs.append(row)
            existing_log_ids.add(row[0])

    append_logs(service, new_logs)
    _, refreshed_logs = get_records(service, LOG_SHEET)
    write_report(service, build_report(refreshed_logs))
    print("publish log sync complete")


if __name__ == "__main__":
    main()
