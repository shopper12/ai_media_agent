import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
MEDIA_REPO_TOKEN = os.environ.get("MEDIA_REPO_TOKEN", "").strip()
MEDIA_REPO = os.environ.get("MEDIA_REPO", "").strip()
MEDIA_BRANCH = os.environ.get("MEDIA_BRANCH", "main").strip() or "main"
MEDIA_OBJECT_PREFIX = os.environ.get("MEDIA_OBJECT_PREFIX", "media").strip().strip("/")
MEDIA_PUBLIC_BASE_URL = os.environ.get("MEDIA_PUBLIC_BASE_URL", "").strip()
MEDIA_UPLOAD_FORCE = os.environ.get("MEDIA_UPLOAD_FORCE", "").strip().lower() in {"1", "true", "yes"}

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MEDIA_CHANNELS = {"INSTAGRAM_REELS", "TIKTOK"}
REQUIRED_COLUMNS = [
    "MediaPublicUrl",
    "MediaUploadStatus",
    "MediaUploadError",
    "MediaUploadedAt",
]


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
    if str(rec.get("MediaPublicUrl", "")).strip() and not MEDIA_UPLOAD_FORCE:
        return False
    return True


def slug(value):
    text = re.sub(r"[^0-9a-zA-Z가-힣._-]+", "-", str(value or "")).strip("-")
    return text or "media"


def media_repo_path(local_path, rec):
    local = Path(local_path)
    name = slug(local.name)
    asset_id = slug(rec.get("AssetId") or rec.get("ContentId") or local.stem)
    path = f"{asset_id}-{name}"
    return f"{MEDIA_OBJECT_PREFIX}/{path}" if MEDIA_OBJECT_PREFIX else path


def public_url(path):
    return MEDIA_PUBLIC_BASE_URL.rstrip("/") + "/" + quote(path, safe="/")


def github_headers():
    return {
        "Authorization": f"Bearer {MEDIA_REPO_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def existing_sha(repo_path):
    url = f"https://api.github.com/repos/{MEDIA_REPO}/contents/{quote(repo_path, safe='/')}"
    response = requests.get(url, headers=github_headers(), params={"ref": MEDIA_BRANCH}, timeout=60)
    if response.status_code == 404:
        return ""
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub content lookup failed {response.status_code}: {response.text[:500]}")
    data = response.json()
    return str(data.get("sha", ""))


def upload_to_repo(local_path, repo_path):
    content = base64.b64encode(Path(local_path).read_bytes()).decode("ascii")
    payload = {
        "message": f"Publish media asset {repo_path}",
        "content": content,
        "branch": MEDIA_BRANCH,
    }
    sha = existing_sha(repo_path)
    if sha:
        payload["sha"] = sha
    url = f"https://api.github.com/repos/{MEDIA_REPO}/contents/{quote(repo_path, safe='/')}"
    response = requests.put(url, headers=github_headers(), json=payload, timeout=180)
    if response.status_code >= 400:
        raise RuntimeError(f"GitHub media upload failed {response.status_code}: {response.text[:500]}")
    return response.json()


def missing_config():
    missing = []
    for name, value in {
        "MEDIA_REPO_TOKEN": MEDIA_REPO_TOKEN,
        "MEDIA_REPO": MEDIA_REPO,
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
        message = "Missing GitHub Pages media config: " + ", ".join(missing)
        for rec in targets:
            update_row(service, headers, rec, {
                "MediaUploadStatus": "NEED_GITHUB_PAGES_CONFIG",
                "MediaUploadError": message[:500],
                "MediaUploadedAt": now_kst(),
            })
        print(message)
        print(f"media upload skipped: {len(targets)}")
        return

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
        repo_path = media_repo_path(media_path, rec)
        try:
            upload_to_repo(media_path, repo_path)
            update_row(service, headers, rec, {
                "MediaPublicUrl": public_url(repo_path),
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
    print(f"media uploaded to GitHub Pages repo: {uploaded}; failed: {failed}; targets: {len(targets)}")


if __name__ == "__main__":
    main()
