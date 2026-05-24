import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import credentials as oauth_credentials
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
YOUTUBE_OAUTH_CLIENT_JSON = os.environ["YOUTUBE_OAUTH_CLIENT_JSON"]
YOUTUBE_OAUTH_REFRESH_TOKEN = os.environ["YOUTUBE_OAUTH_REFRESH_TOKEN"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
SHEET_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
YOUTUBE_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.upload",
]

EXTRA_COLUMNS = [
    "Views",
    "Likes",
    "Comments",
    "YouTubePrivacyStatus",
    "MetricSyncedAt",
    "MetricSyncError",
]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SHEET_SCOPES)
    return build("sheets", "v4", credentials=creds)


def youtube_service():
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


def get_values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service, values):
    headers = values[0] if values else []
    changed = False
    for col in EXTRA_COLUMNS:
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


def records(headers, values):
    out = []
    for row_number, row in enumerate(values[1:], start=2):
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        item["_row_number"] = row_number
        out.append(item)
    return out


def update_row(service, headers, row, updates):
    data = [row.get(h, "") for h in headers]
    for key, value in updates.items():
        if key in headers:
            data[headers.index(key)] = value
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{row['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [data]},
    ).execute()


def norm(value):
    return str(value or "").strip().upper()


def youtube_rows(rows):
    out = []
    for row in rows:
        channel = norm(row.get("PublishChannel"))
        post_id = str(row.get("PlatformPostId", "")).strip()
        if post_id and channel in {"YOUTUBE_SHORTS", "YOUTUBE", "SHORTS"}:
            out.append(row)
    return out


def chunks(items, size=50):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def main():
    sheet = sheets_service()
    values = get_values(sheet)
    if not values:
        print("publish_assets is empty")
        return
    headers = ensure_headers(sheet, values)
    values = get_values(sheet)
    rows = records(headers, values)
    targets = youtube_rows(rows)
    if not targets:
        print("no YouTube rows to sync")
        return

    yt = youtube_service()
    synced = 0
    for group in chunks(targets):
        ids = [str(r.get("PlatformPostId", "")).strip() for r in group]
        try:
            response = yt.videos().list(
                part="statistics,status",
                id=",".join(ids),
                maxResults=len(ids),
            ).execute()
            by_id = {item["id"]: item for item in response.get("items", [])}
            for row in group:
                video_id = str(row.get("PlatformPostId", "")).strip()
                item = by_id.get(video_id)
                if not item:
                    update_row(sheet, headers, row, {
                        "MetricSyncError": "video not returned by YouTube API",
                        "MetricSyncedAt": now_kst(),
                    })
                    continue
                stats = item.get("statistics", {})
                status = item.get("status", {})
                update_row(sheet, headers, row, {
                    "Views": stats.get("viewCount", "0"),
                    "Likes": stats.get("likeCount", "0"),
                    "Comments": stats.get("commentCount", "0"),
                    "YouTubePrivacyStatus": status.get("privacyStatus", ""),
                    "MetricSyncedAt": now_kst(),
                    "MetricSyncError": "",
                })
                synced += 1
        except Exception as exc:
            message = str(exc)[:500]
            for row in group:
                update_row(sheet, headers, row, {
                    "MetricSyncError": message,
                    "MetricSyncedAt": now_kst(),
                })
    print(f"synced YouTube metrics: {synced}")


if __name__ == "__main__":
    main()
