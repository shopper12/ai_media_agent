import json
import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
CHANNEL_CONFIG_PATH = os.environ.get("REAL_PUBLISH_CHANNELS_CONFIG", "config/real_publish_channels.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

ROUTING_COLUMNS = [
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


def load_config():
    return json.loads(Path(CHANNEL_CONFIG_PATH).read_text(encoding="utf-8"))


def get_values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service, values):
    headers = values[0] if values else []
    changed = False
    for column in ROUTING_COLUMNS:
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


def normalize_channel(raw, config):
    value = str(raw or "").strip()
    if not value:
        return config.get("default_blog_channel", "NAVER_BLOG")
    if value in config["channels"]:
        return value
    mapped = config.get("legacy_channel_map", {}).get(value)
    if mapped:
        return mapped
    upper = value.upper().replace(" ", "_").replace("-", "_")
    return config.get("legacy_channel_map", {}).get(upper, upper)


def credential_status(channel, config):
    channel_config = config["channels"].get(channel)
    if not channel_config:
        return "UNKNOWN_CHANNEL"
    required = channel_config.get("required_secrets", [])
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        return "NEED_CREDENTIAL:" + ",".join(missing)
    if channel_config.get("requires_local_session"):
        return "NEED_LOCAL_SESSION"
    return "READY"


def media_status(record, channel, config):
    channel_config = config["channels"].get(channel, {})
    if not channel_config.get("requires_media_file"):
        return "NOT_REQUIRED"
    media_path = str(record.get("MediaFilePath", "")).strip()
    if not media_path:
        return "NEED_MEDIA_FILE"
    return "READY"


def route_status(decision, credential, media):
    if decision != "APPROVE":
        return "WAITING_APPROVAL"
    if credential == "READY" and media in {"READY", "NOT_REQUIRED"}:
        return "READY_TO_PUBLISH"
    if credential.startswith("NEED_CREDENTIAL"):
        return "NEED_CREDENTIAL"
    if credential == "NEED_LOCAL_SESSION":
        return "NEED_LOCAL_SESSION"
    if media == "NEED_MEDIA_FILE":
        return "NEED_MEDIA_FILE"
    return "BLOCKED"


def upload_error(status):
    if status in {"READY_TO_PUBLISH", "WAITING_APPROVAL"}:
        return ""
    return f"{status} at {now_kst()}"


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


def should_route(record):
    return bool(str(record.get("AssetId") or record.get("ContentId") or record.get("Title") or "").strip())


def main():
    config = load_config()
    service = sheets_service()
    values = get_values(service)
    if not values:
        raise RuntimeError(f"No rows found in sheet: {ASSETS_SHEET}")
    headers = ensure_headers(service, values)
    values = get_values(service)
    records = records_from_values(headers, values)

    routed = 0
    for record in records:
        if not should_route(record):
            continue
        decision = str(record.get("PublishDecision", "")).strip().upper()
        channel = normalize_channel(record.get("PublishChannel"), config)
        credential = credential_status(channel, config)
        media = media_status(record, channel, config)
        status = route_status(decision, credential, media)
        update_row(service, headers, record, {
            "PublishChannel": channel,
            "CredentialStatus": credential,
            "MediaStatus": media,
            "ChannelStatus": status,
            "UploadError": upload_error(status),
        })
        routed += 1
    print(f"routed assets: {routed}")


if __name__ == "__main__":
    main()
