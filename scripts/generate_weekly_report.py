import json
import os
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build


SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
REPORT_SHEET_NAME = os.environ.get("REPORT_SHEET_NAME", "weekly_report")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


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


def ensure_report_sheet(service):
    if get_sheet_id(service, REPORT_SHEET_NAME) is not None:
        return
    service.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": [{"addSheet": {"properties": {"title": REPORT_SHEET_NAME}}}]},
    ).execute()


def get_rows(service):
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


def build_report(rows):
    total = len(rows)
    owner = Counter(r.get("OwnerDecision", "") or "BLANK" for r in rows)
    final = Counter(r.get("FinalStatus", "") or "BLANK" for r in rows)
    categories = Counter(r.get("Category", "") or "UNKNOWN" for r in rows)
    drafts_ready = sum(1 for r in rows if r.get("FinalStatus") == "DRAFT_READY")
    approved_waiting = [r for r in rows if r.get("OwnerDecision") == "APPROVE" and r.get("FinalStatus") != "DRAFT_READY"]
    final_review_ready = [r for r in rows if r.get("FinalStatus") == "DRAFT_READY" and not r.get("FinalOwnerDecision")]

    lines = []
    lines.append(["GeneratedAt", now_kst()])
    lines.append(["Total candidates", total])
    lines.append(["OwnerDecision APPROVE", owner.get("APPROVE", 0)])
    lines.append(["OwnerDecision HOLD", owner.get("HOLD", 0)])
    lines.append(["OwnerDecision REJECT", owner.get("REJECT", 0)])
    lines.append(["OwnerDecision BLANK", owner.get("BLANK", 0)])
    lines.append(["Draft ready", drafts_ready])
    lines.append(["Approved but not drafted", len(approved_waiting)])
    lines.append(["Draft ready and waiting final review", len(final_review_ready)])
    lines.append([])
    lines.append(["Category", "Count"])
    for category, count in categories.most_common():
        lines.append([category, count])
    lines.append([])
    lines.append(["Ready for final review", "Title", "Score", "DraftHook"])
    for r in final_review_ready[:20]:
        lines.append([r.get("ContentId", ""), r.get("Title", ""), r.get("ExpectedProfitScore", ""), r.get("DraftHook", "")])
    lines.append([])
    lines.append(["Approved but not drafted", "Title", "Score"])
    for r in approved_waiting[:20]:
        lines.append([r.get("ContentId", ""), r.get("Title", ""), r.get("ExpectedProfitScore", "")])
    return lines


def write_report(service, report):
    service.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{REPORT_SHEET_NAME}!A:Z",
        body={},
    ).execute()
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{REPORT_SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": report},
    ).execute()


def main():
    service = sheets_service()
    ensure_report_sheet(service)
    _, rows = get_rows(service)
    report = build_report(rows)
    write_report(service, report)
    print("weekly report updated")


if __name__ == "__main__":
    main()
