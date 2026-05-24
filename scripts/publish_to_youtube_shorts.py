import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
YOUTUBE_OAUTH_CLIENT_JSON = os.environ["YOUTUBE_OAUTH_CLIENT_JSON"]
YOUTUBE_OAUTH_REFRESH_TOKEN = os.environ["YOUTUBE_OAUTH_REFRESH_TOKEN"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
PRIVACY_STATUS = os.environ.get("YOUTUBE_PRIVACY_STATUS", "private")
CATEGORY_ID = os.environ.get("YOUTUBE_CATEGORY_ID", "28")
SHEET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

COLUMNS = [
    "PublishDecision",
    "PublishChannel",
    "ChannelStatus",
    "CredentialStatus",
    "MediaStatus",
    "MediaFilePath",
    "TargetUrl",
    "PlatformPostId",
    "PublishedAt",
    "UploadError",
]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheet_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SHEET_SCOPES)
    return build("sheets", "v4", credentials=creds)


def yt_service():
    data = json.loads(YOUTUBE_OAUTH_CLIENT_JSON)
    client = data.get("installed") or data.get("web") or data
    creds = oauth_credentials.Credentials(
        token=None,
        refresh_token=YOUTUBE_OAUTH_REFRESH_TOKEN,
        token_uri=client["token_uri"],
        client_id=client["client_id"],
        client_secret=client["client_secret"],
        scopes=YOUTUBE_SCOPES,
    )
    return build("youtube", "v3", credentials=creds)


def values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service, vals):
    headers = vals[0] if vals else []
    changed = False
    for col in COLUMNS:
        if col not in headers:
            headers.append(col)
            changed = True
    if changed:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    return headers


def records(headers, vals):
    out = []
    for row_number, row in enumerate(vals[1:], start=2):
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        item["_row_number"] = row_number
        out.append(item)
    return out


def update_row(service, headers, row, updates):
    vals = [row.get(h, "") for h in headers]
    for key, value in updates.items():
        if key in headers:
            vals[headers.index(key)] = value
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{row['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [vals]},
    ).execute()


def norm(value):
    return str(value or "").strip().upper()


def is_target(row):
    if norm(row.get("PublishDecision")) != "APPROVE":
        return False
    if str(row.get("TargetUrl", "")).strip():
        return False
    ch = norm(row.get("PublishChannel"))
    typ = norm(row.get("AssetType"))
    return ch in {"YOUTUBE_SHORTS", "SHORTS", "YOUTUBE"} or typ == "SHORTS"


def split_tags(text):
    tags = [t.strip().lstrip("#") for t in re.split(r"[,#]\s*", str(text or "")) if t.strip()]
    return tags[:15]


def description(row):
    return (str(row.get("Caption", "")) + "\n\n" + str(row.get("RiskNotice", "")))[:4900]


def send_video(youtube, row):
    media_path = str(row.get("MediaFilePath", "")).strip()
    if not media_path or not os.path.exists(media_path):
        raise FileNotFoundError(f"MediaFilePath not found: {media_path}")
    title = str(row.get("Title") or "AI Media Agent Short")[:100]
    body = {
        "snippet": {
            "title": title,
            "description": description(row),
            "tags": split_tags(row.get("Tags")),
            "categoryId": CATEGORY_ID,
        },
        "status": {"privacyStatus": PRIVACY_STATUS, "selfDeclaredMadeForKids": False},
    }
    media = MediaFileUpload(media_path, mimetype="video/*", resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        _, response = request.next_chunk()
    return response["id"]


def main():
    sheet = sheet_service()
    vals = values(sheet)
    if not vals:
        raise RuntimeError("publish_assets sheet is empty")
    headers = ensure_headers(sheet, vals)
    vals = values(sheet)
    rows = records(headers, vals)
    targets = [r for r in rows if is_target(r)]
    if not targets:
        print("no approved YouTube Shorts rows")
        return
    youtube = yt_service()
    count = 0
    for row in targets:
        try:
            video_id = send_video(youtube, row)
            update_row(sheet, headers, row, {
                "PublishChannel": "YOUTUBE_SHORTS",
                "CredentialStatus": "READY",
                "MediaStatus": "READY",
                "ChannelStatus": "PUBLISHED",
                "TargetUrl": f"https://www.youtube.com/watch?v={video_id}",
                "PlatformPostId": video_id,
                "PublishedAt": now_kst(),
                "UploadError": "",
            })
            count += 1
        except Exception as exc:
            update_row(sheet, headers, row, {
                "PublishChannel": "YOUTUBE_SHORTS",
                "ChannelStatus": "FAILED",
                "UploadError": str(exc)[:500],
            })
    print(f"published YouTube Shorts rows: {count}")


if __name__ == "__main__":
    main()
