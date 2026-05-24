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
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
AUDIT_SHEET = os.environ.get("PIPELINE_AUDIT_SHEET_NAME", "pipeline_audit")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def sheet_id(svc, name):
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sh in meta.get("sheets", []):
        if sh.get("properties", {}).get("title") == name:
            return sh.get("properties", {}).get("sheetId")
    return None


def ensure_sheet(svc, name):
    if sheet_id(svc, name) is None:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": name}}}]},
        ).execute()


def read_records(svc, name):
    values = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{name}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if not values:
        return [], []
    headers = values[0]
    rows = []
    for idx, row in enumerate(values[1:], start=2):
        rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rec["_row_number"] = idx
        rows.append(rec)
    return headers, rows


def norm(value):
    return str(value or "").strip().upper()


def build_report(candidates, assets):
    owner = Counter(norm(r.get("OwnerDecision")) or "BLANK" for r in candidates)
    final = Counter(norm(r.get("FinalStatus")) or "BLANK" for r in candidates)
    channel = Counter(norm(r.get("PublishChannel")) or "BLANK" for r in assets)
    status = Counter(norm(r.get("ChannelStatus")) or "BLANK" for r in assets)
    media = Counter(norm(r.get("MediaStatus")) or "BLANK" for r in assets)
    script = Counter(norm(r.get("ScriptApprovalStatus")) or "BLANK" for r in assets)
    issues = []

    for r in assets:
        aid = r.get("AssetId", "")
        if norm(r.get("PublishDecision")) == "APPROVE" and norm(r.get("AssetType")) == "SHORTS":
            if norm(r.get("ScriptApprovalStatus")) != "SCRIPT_APPROVED" and not r.get("TargetUrl"):
                issues.append(["BLOCKER", aid, "Shorts row approved but script is not approved", r.get("UploadError", "")])
            if norm(r.get("ScriptApprovalStatus")) == "SCRIPT_APPROVED" and not r.get("MediaFilePath") and not r.get("TargetUrl"):
                issues.append(["BLOCKER", aid, "Script approved but media file is missing", r.get("UploadError", "")])
            if r.get("MediaFilePath") and norm(r.get("MediaStatus")) != "READY" and not r.get("TargetUrl"):
                issues.append(["WARN", aid, "MediaFilePath exists but MediaStatus is not READY", r.get("MediaStatus", "")])
        if norm(r.get("ChannelStatus")) == "PUBLISHED" and not r.get("TargetUrl"):
            issues.append(["BLOCKER", aid, "Marked PUBLISHED but TargetUrl is empty", ""])

    rows = [
        ["GeneratedAt", now_kst()],
        [],
        ["Candidate queue"],
        ["OwnerDecision APPROVE", owner.get("APPROVE", 0)],
        ["OwnerDecision HOLD", owner.get("HOLD", 0)],
        ["OwnerDecision REJECT", owner.get("REJECT", 0)],
        ["OwnerDecision BLANK", owner.get("BLANK", 0)],
        ["FinalStatus DRAFT_READY", final.get("DRAFT_READY", 0)],
        [],
        ["Publish assets"],
        ["ChannelStatus PUBLISHED", status.get("PUBLISHED", 0)],
        ["ChannelStatus MEDIA_READY", status.get("MEDIA_READY", 0)],
        ["ChannelStatus SCRIPT_READY", status.get("SCRIPT_READY", 0)],
        ["ChannelStatus BLOCKED/FAILED", status.get("PUBLISH_BLOCKED", 0) + status.get("FAILED", 0) + status.get("SCRIPT_FAILED", 0)],
        ["MediaStatus READY", media.get("READY", 0)],
        ["ScriptApprovalStatus SCRIPT_APPROVED", script.get("SCRIPT_APPROVED", 0)],
        [],
        ["PublishChannel", "Count"],
    ]
    for k, v in channel.most_common():
        rows.append([k, v])
    rows.extend([[], ["Severity", "AssetId", "Issue", "Detail"]])
    rows.extend(issues[:50])
    if not issues:
        rows.append(["OK", "", "No blocking issues detected", ""])
    return rows


def write_report(svc, rows):
    ensure_sheet(svc, AUDIT_SHEET)
    svc.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{AUDIT_SHEET}!A:Z",
        body={},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{AUDIT_SHEET}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()


def main():
    svc = service()
    _, candidates = read_records(svc, SHEET_NAME)
    _, assets = read_records(svc, ASSETS_SHEET)
    write_report(svc, build_report(candidates, assets))
    print("pipeline audit updated")


if __name__ == "__main__":
    main()
