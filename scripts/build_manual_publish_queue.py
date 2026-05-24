import html
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
OUT_DIR = Path(os.environ.get("MANUAL_PUBLISH_QUEUE_DIR", "outbox/manual_publish"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def read_values(svc):
    return svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def records(values):
    if not values:
        return [], []
    headers = values[0]
    out = []
    for row_number, row in enumerate(values[1:], start=2):
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        item["_row_number"] = row_number
        out.append(item)
    return headers, out


def update_row(svc, headers, row, updates):
    data = [row.get(h, "") for h in headers]
    for key, value in updates.items():
        if key in headers:
            data[headers.index(key)] = value
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{row['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [data]},
    ).execute()


def norm(value):
    return str(value or "").strip().upper()


def selected(row):
    if norm(row.get("PublishDecision")) != "APPROVE":
        return False
    if str(row.get("TargetUrl", "")).strip():
        return False
    channel = norm(row.get("PublishChannel"))
    if channel == "YOUTUBE_SHORTS":
        return False
    return channel in {"NAVER_BLOG", "INSTAGRAM_REELS", "TIKTOK", "THREADS", "X"}


def platform_url(channel, blog_id=""):
    if channel == "NAVER_BLOG":
        return f"https://blog.naver.com/{blog_id}?Redirect=Write" if blog_id else "https://blog.naver.com/"
    if channel == "INSTAGRAM_REELS":
        return "https://www.instagram.com/"
    if channel == "TIKTOK":
        return "https://www.tiktok.com/upload"
    if channel == "THREADS":
        return "https://www.threads.net/"
    if channel == "X":
        return "https://x.com/compose/post"
    return ""


def build_payload(row):
    channel = norm(row.get("PublishChannel"))
    title = str(row.get("Title", "")).strip()
    body = str(row.get("Body", "") or row.get("Caption", "")).strip()
    caption = str(row.get("Caption", "") or body).strip()
    tags = str(row.get("Tags", "")).strip()
    risk = str(row.get("RiskNotice", "")).strip()
    if channel in {"X", "THREADS"}:
        text = body or caption or title
    elif channel in {"INSTAGRAM_REELS", "TIKTOK"}:
        text = caption or body or title
    else:
        text = body or caption
    if risk and channel in {"NAVER_BLOG", "THREADS", "X"}:
        text = text + "\n\n" + risk
    return {
        "asset_id": row.get("AssetId", ""),
        "content_id": row.get("ContentId", ""),
        "channel": channel,
        "title": title,
        "text": text,
        "caption": caption,
        "tags": tags,
        "media_file": row.get("MediaFilePath", ""),
        "url": platform_url(channel, os.environ.get("NAVER_BLOG_ID", "")),
    }


def safe_id(value):
    return "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in str(value or "asset")).strip("-") or "asset"


def render_html(items):
    cards = []
    for i, item in enumerate(items, start=1):
        text_id = f"text_{i}"
        title_id = f"title_{i}"
        tags_id = f"tags_{i}"
        cards.append(f"""
<section class="card">
  <h2>{html.escape(item['channel'])} · {html.escape(item['asset_id'])}</h2>
  <p><a href="{html.escape(item['url'])}" target="_blank">Open platform</a></p>
  <label>Title</label>
  <textarea id="{title_id}" rows="2">{html.escape(item['title'])}</textarea>
  <button onclick="copyField('{title_id}')">Copy title</button>
  <label>Body / caption</label>
  <textarea id="{text_id}" rows="14">{html.escape(item['text'])}</textarea>
  <button onclick="copyField('{text_id}')">Copy body</button>
  <label>Tags</label>
  <textarea id="{tags_id}" rows="3">{html.escape(item['tags'])}</textarea>
  <button onclick="copyField('{tags_id}')">Copy tags</button>
  <p>Media file: <code>{html.escape(item['media_file'])}</code></p>
</section>
""")
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Manual Publish Queue</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; background: #f6f6f6; }}
.card {{ background: white; border: 1px solid #ddd; border-radius: 12px; padding: 18px; margin-bottom: 18px; }}
textarea {{ width: 100%; box-sizing: border-box; margin: 6px 0 10px; font-size: 14px; }}
button {{ margin-right: 8px; padding: 8px 12px; cursor: pointer; }}
label {{ display: block; font-weight: bold; margin-top: 10px; }}
code {{ white-space: pre-wrap; }}
</style>
<script>
async function copyField(id) {{
  const el = document.getElementById(id);
  await navigator.clipboard.writeText(el.value);
  alert('copied');
}}
</script>
</head>
<body>
<h1>Manual Publish Queue</h1>
<p>Generated at {html.escape(now_kst())}. Use this for platforms that still require login/session or API credentials.</p>
{''.join(cards)}
</body>
</html>"""


def main():
    svc = service()
    vals = read_values(svc)
    if not vals:
        print("no publish assets")
        return
    headers, all_rows = records(vals)
    targets = [row for row in all_rows if selected(row)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = [build_payload(row) for row in targets]
    for item in items:
        path = OUT_DIR / f"{safe_id(item['asset_id'])}.json"
        path.write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT_DIR / "manual_publish_queue.html").write_text(render_html(items), encoding="utf-8")
    (OUT_DIR / "manifest.json").write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    for row in targets:
        update_row(svc, headers, row, {
            "ChannelStatus": "MANUAL_QUEUE_READY",
            "UploadError": "Manual/API credential publishing queue prepared.",
        })
    print(f"manual publish queue rows: {len(items)}")


if __name__ == "__main__":
    main()
