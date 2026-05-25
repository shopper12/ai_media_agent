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
X_BEARER_TOKEN = os.environ.get("X_BEARER_TOKEN", "").strip()
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


def records(headers, vals):
    out = []
    for row_no, row in enumerate(vals[1:], start=2):
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
    return norm(rec.get("PublishDecision")) == "APPROVE" and norm(rec.get("PublishChannel")) == "X" and not str(rec.get("TargetUrl", "")).strip()


def text_of(rec):
    text = str(rec.get("Body") or rec.get("Caption") or rec.get("Title") or "").strip()
    tags = str(rec.get("Tags") or "").strip()
    if tags:
        hash_tags = " ".join("#" + t.strip().lstrip("#") for t in tags.replace("#", "").split(",")[:5] if t.strip())
        if hash_tags and len(text) + 1 + len(hash_tags) <= 280:
            text = text + "\n" + hash_tags
    if len(text) > 280:
        text = text[:277].rstrip() + "..."
    return text


def publish_x(rec):
    if not X_BEARER_TOKEN:
        return {"status": "NEED_CREDENTIAL", "error": "missing X_BEARER_TOKEN"}
    response = requests.post(
        "https://api.x.com/2/tweets",
        headers={"Authorization": f"Bearer {X_BEARER_TOKEN}", "Content-Type": "application/json"},
        json={"text": text_of(rec)},
        timeout=60,
    )
    try:
        data = response.json()
    except Exception:
        data = {"raw": response.text[:500]}
    if response.status_code >= 400:
        return {"status": "FAILED", "error": f"HTTP {response.status_code}: {data}"[:500]}
    tweet_id = str(data.get("data", {}).get("id", ""))
    return {
        "status": "PUBLISHED",
        "post_id": tweet_id,
        "target_url": f"https://x.com/i/web/status/{tweet_id}" if tweet_id else "",
        "error": "" if tweet_id else f"published but no id: {data}",
    }


def main():
    svc = service()
    vals = values(svc)
    if not vals:
        raise RuntimeError(f"No rows found in {ASSETS_SHEET}")
    headers = vals[0]
    done = 0
    for rec in records(headers, vals):
        if not selected(rec):
            continue
        try:
            result = publish_x(rec)
        except Exception as exc:
            result = {"status": "FAILED", "error": str(exc)[:500]}
        updates = {
            "ChannelStatus": result.get("status", "FAILED"),
            "CredentialStatus": "READY" if result.get("status") == "PUBLISHED" else result.get("status", "FAILED"),
            "PlatformPostId": result.get("post_id", ""),
            "UploadError": result.get("error", "")[:500],
        }
        if result.get("target_url"):
            updates["TargetUrl"] = result["target_url"]
            updates["PublishedAt"] = now_kst()
        update_row(svc, headers, rec, updates)
        done += 1
    print(f"x text publish processed: {done}")


if __name__ == "__main__":
    main()
