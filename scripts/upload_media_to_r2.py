import json
import mimetypes
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import boto3
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "").strip()
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET = os.environ.get("R2_BUCKET", "").strip()
R2_OBJECT_PREFIX = os.environ.get("R2_OBJECT_PREFIX", "media").strip().strip("/")
MEDIA_PUBLIC_BASE_URL = (
    os.environ.get("MEDIA_PUBLIC_BASE_URL", "").strip()
    or os.environ.get("R2_PUBLIC_BASE_URL", "").strip()
)
FORCE_UPLOAD = os.environ.get("MEDIA_UPLOAD_FORCE", "").strip().lower() in {"1", "true", "yes"}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
REQUIRED_COLUMNS = [
    "MediaPublicUrl",
    "MediaUploadStatus",
    "MediaUploadError",
    "MediaUploadedAt",
]
MEDIA_CHANNELS = {"INSTAGRAM_REELS", "TIKTOK"}


def now_kst():
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


def records(headers, values):
    out = []
    for row_number, row in enumerate(values[1:], start=2):
        rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rec["_row_number"] = row_number
        out.append(rec)
    return out


def update_row(service, headers, rec, updates):
    row = [rec.get(header, "") for header in headers]
    for key, value in updates.items():
        if key in headers:
            row[headers.index(key)] = value
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{rec['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def norm(value):
    return str(value or "").strip().upper()


def selected(rec):
    if norm(rec.get("PublishDecision")) != "APPROVE":
        return False
    if norm(rec.get("PublishChannel")) not in MEDIA_CHANNELS:
        return False
    if str(rec.get("TargetUrl", "")).strip():
        return False
    if not str(rec.get("MediaFilePath", "")).strip():
        return False
    if str(rec.get("MediaPublicUrl", "")).strip() and not FORCE_UPLOAD:
        return False
    return True


def r2_client():
    endpoint = f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        region_name="auto",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
    )


def object_key_for(path):
    local = Path(path)
    safe_name = local.name
    if not safe_name:
        safe_name = "media.mp4"
    return f"{R2_OBJECT_PREFIX}/{safe_name}" if R2_OBJECT_PREFIX else safe_name


def public_url_for(key):
    return MEDIA_PUBLIC_BASE_URL.rstrip("/") + "/" + quote(key, safe="/")


def upload_file(client, local_path, key):
    content_type = mimetypes.guess_type(str(local_path))[0] or "application/octet-stream"
    extra = {
        "ContentType": content_type,
        "CacheControl": "public, max-age=31536000, immutable",
    }
    client.upload_file(str(local_path), R2_BUCKET, key, ExtraArgs=extra)


def missing_config():
    missing = []
    for name, value in {
        "R2_ACCOUNT_ID": R2_ACCOUNT_ID,
        "R2_ACCESS_KEY_ID": R2_ACCESS_KEY_ID,
        "R2_SECRET_ACCESS_KEY": R2_SECRET_ACCESS_KEY,
        "R2_BUCKET": R2_BUCKET,
        "MEDIA_PUBLIC_BASE_URL": MEDIA_PUBLIC_BASE_URL,
    }.items():
        if not value:
            missing.append(name)
    return missing


def main():
    service = sheets_service()
    values = get_values(service)
    if not values:
        raise RuntimeError(f"No rows found in {ASSETS_SHEET}")
    headers = ensure_headers(service, values)
    values = get_values(service)
    rows = records(headers, values)
    targets = [rec for rec in rows if selected(rec)]

    missing = missing_config()
    if missing:
        message = "Missing R2 public media config: " + ", ".join(missing)
        for rec in targets:
            update_row(service, headers, rec, {
                "MediaUploadStatus": "NEED_R2_CONFIG",
                "MediaUploadError": message[:500],
                "MediaUploadedAt": now_kst(),
            })
        print(message)
        print(f"media upload skipped: {len(targets)}")
        return

    client = r2_client()
    uploaded = 0
    failed = 0
    for rec in targets:
        media_path = Path(str(rec.get("MediaFilePath", "")).strip())
        if not media_path.exists() or not media_path.is_file():
            failed += 1
            update_row(service, headers, rec, {
                "MediaUploadStatus": "LOCAL_FILE_MISSING",
                "MediaUploadError": f"MediaFilePath not found in workflow checkout: {media_path}",
                "MediaUploadedAt": now_kst(),
            })
            continue
        key = object_key_for(media_path)
        try:
            upload_file(client, media_path, key)
            update_row(service, headers, rec, {
                "MediaPublicUrl": public_url_for(key),
                "MediaUploadStatus": "UPLOADED",
                "MediaUploadError": "",
                "MediaUploadedAt": now_kst(),
            })
            uploaded += 1
        except Exception as exc:
            failed += 1
            update_row(service, headers, rec, {
                "MediaUploadStatus": "FAILED",
                "MediaUploadError": str(exc)[:500],
                "MediaUploadedAt": now_kst(),
            })
    print(f"media uploaded to R2: {uploaded}; failed: {failed}; targets: {len(targets)}")


if __name__ == "__main__":
    main()
