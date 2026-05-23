import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
NAVER_BLOG_WEBHOOK_URL = os.environ.get("NAVER_BLOG_WEBHOOK_URL", "").strip()
NAVER_BLOG_ID = os.environ.get("NAVER_BLOG_ID", "").strip()
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

REQUIRED_COLUMNS = [
    "PublishDecision",
    "PublishChannel",
    "ChannelStatus",
    "CredentialStatus",
    "MediaStatus",
    "TargetUrl",
    "PlatformPostId",
    "PublishedAt",
    "UploadError",
]


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service, values):
    headers = values[0] if values else []
    changed = False
    for column in REQUIRED_COLUMNS:
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
    return headers


def records_from_values(headers, values):
    records = []
    for row_number, row in enumerate(values[1:], start=2):
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        record["_row_number"] = row_number
        records.append(record)
    return records


def update_row(service, headers, record, updates):
    row = [record.get(header, "") for header in headers]
    for key, value in updates.items():
        if key in headers:
            row[headers.index(key)] = value
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{record['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def norm(value) -> str:
    return str(value or "").strip().upper()


def is_target(record):
    if norm(record.get("PublishDecision")) != "APPROVE":
        return False
    if str(record.get("TargetUrl", "")).strip():
        return False
    channel = norm(record.get("PublishChannel"))
    asset_type = norm(record.get("AssetType"))
    return channel in {"NAVER_BLOG", "BLOG", "NAVER", "NAVER BLOG"} or asset_type == "BLOG"


def build_payload(record):
    return {
        "platform": "NAVER_BLOG",
        "blog_id": NAVER_BLOG_ID,
        "asset_id": record.get("AssetId", ""),
        "content_id": record.get("ContentId", ""),
        "title": record.get("Title", ""),
        "body": record.get("Body", ""),
        "caption": record.get("Caption", ""),
        "tags": record.get("Tags", ""),
        "checklist": record.get("Checklist", ""),
        "risk_notice": record.get("RiskNotice", ""),
        "requested_at": now_kst(),
    }


def send_to_bridge(payload):
    response = requests.post(NAVER_BLOG_WEBHOOK_URL, json=payload, timeout=60)
    response.raise_for_status()
    if response.text.strip():
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"raw_response": response.text[:500]}
    return {}


def main():
    service = sheets_service()
    values = get_values(service)
    if not values:
        raise RuntimeError(f"No rows found in sheet: {ASSETS_SHEET}")
    headers = ensure_headers(service, values)
    values = get_values(service)
    records = records_from_values(headers, values)
    targets = [record for record in records if is_target(record)]

    if not NAVER_BLOG_WEBHOOK_URL:
        for record in targets:
            update_row(service, headers, record, {
                "PublishChannel": "NAVER_BLOG",
                "CredentialStatus": "NEED_SECRET:NAVER_BLOG_WEBHOOK_URL",
                "MediaStatus": "NOT_REQUIRED",
                "ChannelStatus": "NEED_CREDENTIAL",
                "UploadError": f"missing NAVER_BLOG_WEBHOOK_URL at {now_kst()}",
            })
        print(f"naver bridge missing; marked rows: {len(targets)}")
        return

    sent = 0
    for record in targets:
        payload = build_payload(record)
        try:
            result = send_to_bridge(payload)
            target_url = str(result.get("target_url") or result.get("url") or "").strip()
            post_id = str(result.get("post_id") or result.get("id") or "").strip()
            if target_url:
                update_row(service, headers, record, {
                    "PublishChannel": "NAVER_BLOG",
                    "CredentialStatus": "WEBHOOK_READY",
                    "MediaStatus": "NOT_REQUIRED",
                    "TargetUrl": target_url,
                    "PlatformPostId": post_id,
                    "PublishedAt": now_kst(),
                    "ChannelStatus": "PUBLISHED",
                    "UploadError": "",
                })
            else:
                update_row(service, headers, record, {
                    "PublishChannel": "NAVER_BLOG",
                    "CredentialStatus": "WEBHOOK_READY",
                    "MediaStatus": "NOT_REQUIRED",
                    "PlatformPostId": post_id,
                    "ChannelStatus": "SENT_TO_NAVER_BRIDGE",
                    "UploadError": "bridge accepted but did not return target_url",
                })
            sent += 1
        except Exception as exc:
            update_row(service, headers, record, {
                "PublishChannel": "NAVER_BLOG",
                "CredentialStatus": "WEBHOOK_READY",
                "MediaStatus": "NOT_REQUIRED",
                "ChannelStatus": "FAILED",
                "UploadError": str(exc)[:500],
            })
    print(f"sent naver blog rows to bridge: {sent}")


if __name__ == "__main__":
    main()
