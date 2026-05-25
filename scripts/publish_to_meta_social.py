import json
import os
import time
from datetime import datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
META_ACCESS_TOKEN = os.environ.get("META_ACCESS_TOKEN", "").strip()
INSTAGRAM_ACCOUNT_ID = os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()
THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "").strip()
META_GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v21.0").strip()
THREADS_GRAPH_VERSION = os.environ.get("THREADS_GRAPH_VERSION", "v1.0").strip()
MEDIA_PUBLIC_BASE_URL = os.environ.get("MEDIA_PUBLIC_BASE_URL", "").strip()
META_PUBLISH_WAIT_SECONDS = int(os.environ.get("META_PUBLISH_WAIT_SECONDS", "12"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def values(svc):
    return svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def records(headers, rows):
    out = []
    for row_no, row in enumerate(rows[1:], start=2):
        rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rec["_row_number"] = row_no
        out.append(rec)
    return out


def update_row(svc, headers, rec, updates):
    row = [rec.get(h, "") for h in headers]
    for key, value in updates.items():
        if key in headers:
            row[headers.index(key)] = value
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{rec['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def norm(value):
    return str(value or "").strip().upper()


def selected(rec):
    return (
        norm(rec.get("PublishDecision")) == "APPROVE"
        and not str(rec.get("TargetUrl", "")).strip()
        and norm(rec.get("PublishChannel")) in {"INSTAGRAM_REELS", "THREADS"}
    )


def caption_of(rec, limit):
    text = str(rec.get("Caption") or rec.get("Body") or rec.get("Title") or "").strip()
    risk = str(rec.get("RiskNotice") or "").strip()
    if risk and len(text) + len(risk) + 6 <= limit:
        text = text + "\n\n" + risk
    if len(text) > limit:
        text = text[: limit - 3].rstrip() + "..."
    return text


def public_media_url(rec):
    explicit = str(rec.get("MediaPublicUrl") or rec.get("PublicVideoUrl") or "").strip()
    if explicit.startswith("http://") or explicit.startswith("https://"):
        return explicit
    media_path = str(rec.get("MediaFilePath") or "").strip().replace("\\", "/")
    if media_path.startswith("http://") or media_path.startswith("https://"):
        return media_path
    if not media_path or not MEDIA_PUBLIC_BASE_URL:
        return ""
    return MEDIA_PUBLIC_BASE_URL.rstrip("/") + "/" + quote(media_path.lstrip("/"), safe="/")


def post_json(url, payload):
    response = requests.post(url, data=payload, timeout=120)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:500]}
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {data}")
    return data


def get_json(url, params):
    response = requests.get(url, params=params, timeout=60)
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:500]}
    if response.status_code >= 400:
        raise RuntimeError(f"HTTP {response.status_code}: {data}")
    return data


def publish_instagram_reel(rec):
    if not META_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return {"status": "NEED_CREDENTIAL", "error": "missing META_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID"}
    video_url = public_media_url(rec)
    if not video_url:
        return {"status": "NEED_PUBLIC_MEDIA_URL", "error": "set MEDIA_PUBLIC_BASE_URL or MediaPublicUrl/PublicVideoUrl"}
    caption = caption_of(rec, 2200)
    base = f"https://graph.facebook.com/{META_GRAPH_VERSION}"
    container = post_json(f"{base}/{INSTAGRAM_ACCOUNT_ID}/media", {
        "media_type": "REELS",
        "video_url": video_url,
        "caption": caption,
        "share_to_feed": "true",
        "access_token": META_ACCESS_TOKEN,
    })
    creation_id = str(container.get("id", ""))
    if not creation_id:
        return {"status": "FAILED", "error": f"no creation id: {container}"}
    time.sleep(max(0, META_PUBLISH_WAIT_SECONDS))
    published = post_json(f"{base}/{INSTAGRAM_ACCOUNT_ID}/media_publish", {
        "creation_id": creation_id,
        "access_token": META_ACCESS_TOKEN,
    })
    media_id = str(published.get("id", ""))
    permalink = ""
    if media_id:
        try:
            info = get_json(f"{base}/{media_id}", {"fields": "permalink", "access_token": META_ACCESS_TOKEN})
            permalink = str(info.get("permalink", ""))
        except Exception:
            permalink = ""
    return {"status": "PUBLISHED", "post_id": media_id or creation_id, "target_url": permalink, "error": "" if permalink else "published but permalink not returned"}


def publish_threads_text(rec):
    if not META_ACCESS_TOKEN or not THREADS_USER_ID:
        return {"status": "NEED_CREDENTIAL", "error": "missing META_ACCESS_TOKEN or THREADS_USER_ID"}
    text = caption_of(rec, 500)
    base = f"https://graph.threads.net/{THREADS_GRAPH_VERSION}"
    container = post_json(f"{base}/{THREADS_USER_ID}/threads", {
        "media_type": "TEXT",
        "text": text,
        "access_token": META_ACCESS_TOKEN,
    })
    creation_id = str(container.get("id", ""))
    if not creation_id:
        return {"status": "FAILED", "error": f"no creation id: {container}"}
    published = post_json(f"{base}/{THREADS_USER_ID}/threads_publish", {
        "creation_id": creation_id,
        "access_token": META_ACCESS_TOKEN,
    })
    post_id = str(published.get("id", ""))
    permalink = ""
    if post_id:
        try:
            info = get_json(f"{base}/{post_id}", {"fields": "permalink", "access_token": META_ACCESS_TOKEN})
            permalink = str(info.get("permalink", ""))
        except Exception:
            permalink = ""
    return {"status": "PUBLISHED", "post_id": post_id or creation_id, "target_url": permalink, "error": "" if permalink else "published but permalink not returned"}


def apply_result(svc, headers, rec, result):
    status = result.get("status", "FAILED")
    updates = {
        "ChannelStatus": status,
        "CredentialStatus": "READY" if status == "PUBLISHED" else status,
        "PlatformPostId": result.get("post_id", ""),
        "UploadError": result.get("error", "")[:500],
    }
    if result.get("target_url"):
        updates["TargetUrl"] = result["target_url"]
        updates["PublishedAt"] = now_kst()
    elif status == "PUBLISHED":
        updates["PublishedAt"] = now_kst()
    update_row(svc, headers, rec, updates)


def main():
    svc = service()
    vals = values(svc)
    if not vals:
        raise RuntimeError(f"No rows found in {ASSETS_SHEET}")
    headers = vals[0]
    targets = [rec for rec in records(headers, vals) if selected(rec)]
    done = 0
    for rec in targets:
        channel = norm(rec.get("PublishChannel"))
        try:
            if channel == "INSTAGRAM_REELS":
                result = publish_instagram_reel(rec)
            elif channel == "THREADS":
                result = publish_threads_text(rec)
            else:
                continue
        except Exception as exc:
            result = {"status": "FAILED", "error": str(exc)[:500]}
        apply_result(svc, headers, rec, result)
        done += 1
    print(f"meta social publish processed: {done}")


if __name__ == "__main__":
    main()
