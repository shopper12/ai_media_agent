import html
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
SITE_DIR = Path(os.environ.get("SITE_DIR", "site"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

TRACKING_COLUMNS = ["PublishDecision", "TargetUrl", "PublishedAt", "AssetStatus"]


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def page_base_url() -> str:
    explicit = os.environ.get("PAGES_BASE_URL")
    if explicit:
        return explicit.rstrip("/")
    repo = os.environ.get("GITHUB_REPOSITORY", "shopper12/ai_media_agent")
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}"


def get_values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:Z5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service, values):
    headers = values[0] if values else []
    changed = False
    for column in TRACKING_COLUMNS:
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
        record["_raw_row"] = row
        records.append(record)
    return records


def normalize(value) -> str:
    return str(value or "").strip().upper()


def selected(record) -> bool:
    return (
        normalize(record.get("PublishDecision")) == "APPROVE"
        and normalize(record.get("AssetStatus")) == "ASSET_READY"
        and not str(record.get("TargetUrl", "")).strip()
    )


def slugify(record) -> str:
    raw = "-".join([
        str(record.get("ContentId", "asset")),
        str(record.get("AssetType", record.get("PublishChannel", "post"))),
    ])
    slug = re.sub(r"[^a-zA-Z0-9가-힣_-]+", "-", raw).strip("-").lower()
    return slug or "post"


def paragraphs(text: str) -> str:
    blocks = [b.strip() for b in str(text or "").split("\n\n") if b.strip()]
    if not blocks:
        return ""
    return "\n".join(f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>" for block in blocks)


def render_post(record, target_url: str) -> str:
    title = record.get("Title", "Untitled")
    body = record.get("Body", "")
    caption = record.get("Caption", "")
    tags = record.get("Tags", "")
    checklist = record.get("Checklist", "")
    notice = record.get("RiskNotice", "")
    generated = now_kst()
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif; max-width: 820px; margin: 40px auto; padding: 0 18px; line-height: 1.65; }}
    h1 {{ line-height: 1.25; }}
    .meta {{ color: #666; font-size: 14px; border-bottom: 1px solid #ddd; padding-bottom: 12px; }}
    .box {{ background: #f6f6f6; padding: 14px; border-radius: 10px; margin: 18px 0; }}
    a {{ color: inherit; }}
  </style>
</head>
<body>
  <p><a href="../index.html">← Index</a></p>
  <h1>{html.escape(title)}</h1>
  <div class="meta">ContentId: {html.escape(record.get('ContentId', ''))} · Type: {html.escape(record.get('AssetType', ''))} · Published: {html.escape(generated)}</div>
  <main>
    {paragraphs(body)}
    <section class="box"><h2>Caption</h2>{paragraphs(caption)}</section>
    <section class="box"><h2>Tags</h2><p>{html.escape(tags)}</p></section>
    <section class="box"><h2>Checklist</h2>{paragraphs(checklist)}</section>
    <section class="box"><h2>Notice</h2>{paragraphs(notice)}</section>
    <p class="meta">Canonical URL: {html.escape(target_url)}</p>
  </main>
</body>
</html>
"""


def render_index(posts) -> str:
    items = "\n".join(
        f"<li><a href='{html.escape(p['path'])}'>{html.escape(p['title'])}</a> <span>({html.escape(p['content_id'])})</span></li>"
        for p in posts
    )
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Media Agent</title>
  <style>body {{ font-family: system-ui, sans-serif; max-width: 820px; margin: 40px auto; padding: 0 18px; line-height: 1.65; }}</style>
</head>
<body>
  <h1>AI Media Agent Published Assets</h1>
  <p>Generated at {html.escape(now_kst())}</p>
  <ul>{items}</ul>
</body>
</html>
"""


def write_site(records):
    posts_dir = SITE_DIR / "posts"
    posts_dir.mkdir(parents=True, exist_ok=True)
    (SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")

    base = page_base_url()
    posts = []
    updates = []
    for record in records:
        slug = slugify(record)
        rel_path = f"posts/{slug}.html"
        target_url = f"{base}/{rel_path}"
        post_html = render_post(record, target_url)
        (SITE_DIR / rel_path).write_text(post_html, encoding="utf-8")
        posts.append({
            "path": rel_path,
            "title": record.get("Title", "Untitled"),
            "content_id": record.get("ContentId", ""),
        })
        updates.append((record, target_url))

    (SITE_DIR / "index.html").write_text(render_index(posts), encoding="utf-8")
    return updates


def update_rows(service, headers, updates):
    for record, target_url in updates:
        row = [record.get(header, "") for header in headers]
        row[headers.index("TargetUrl")] = target_url
        row[headers.index("PublishedAt")] = now_kst()
        row[headers.index("AssetStatus")] = "PUBLISHED"
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A{record['_row_number']}",
            valueInputOption="USER_ENTERED",
            body={"values": [row]},
        ).execute()


def main():
    service = sheets_service()
    values = get_values(service)
    if not values:
        raise RuntimeError(f"No rows found in sheet: {ASSETS_SHEET}")
    headers = ensure_headers(service, values)
    values = get_values(service)
    records = records_from_values(headers, values)
    targets = [record for record in records if selected(record)]
    updates = write_site(targets)
    update_rows(service, headers, updates)
    print(f"published assets: {len(updates)}")


if __name__ == "__main__":
    main()
