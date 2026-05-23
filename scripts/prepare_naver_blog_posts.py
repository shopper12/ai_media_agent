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
OUTBOX_DIR = Path(os.environ.get("NAVER_BLOG_OUTBOX_DIR", "outbox/naver_blog"))
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


def is_naver_blog(record) -> bool:
    channel = norm(record.get("PublishChannel"))
    asset_type = norm(record.get("AssetType"))
    return channel in {"NAVER_BLOG", "BLOG", "NAVER", "NAVER BLOG"} or asset_type == "BLOG"


def selected(record) -> bool:
    if norm(record.get("PublishDecision")) != "APPROVE":
        return False
    if not is_naver_blog(record):
        return False
    if str(record.get("TargetUrl", "")).strip():
        return False
    return True


def slugify(value: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "-", str(value or "")).strip("-").lower()
    return slug or "naver-blog-post"


def as_html_paragraphs(text: str) -> str:
    blocks = [block.strip() for block in str(text or "").split("\n\n") if block.strip()]
    return "\n".join(f"<p>{html.escape(block).replace(chr(10), '<br>')}</p>" for block in blocks)


def build_post_package(record):
    title = record.get("Title", "")
    body = record.get("Body", "")
    caption = record.get("Caption", "")
    tags = record.get("Tags", "")
    checklist = record.get("Checklist", "")
    risk_notice = record.get("RiskNotice", "")
    asset_id = record.get("AssetId", "")
    content_id = record.get("ContentId", "")

    markdown = f"""# {title}

{body}

---

## 발행 전 체크리스트

{checklist}

## 고지문

{risk_notice}

## 태그

{tags}

## 캡션/요약

{caption}
"""

    html_body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  {as_html_paragraphs(body)}
  <hr>
  <h2>발행 전 체크리스트</h2>
  {as_html_paragraphs(checklist)}
  <h2>고지문</h2>
  {as_html_paragraphs(risk_notice)}
  <h2>태그</h2>
  <p>{html.escape(tags)}</p>
  <h2>캡션/요약</h2>
  {as_html_paragraphs(caption)}
</body>
</html>
"""

    return {
        "asset_id": asset_id,
        "content_id": content_id,
        "title": title,
        "body": body,
        "caption": caption,
        "tags": tags,
        "checklist": checklist,
        "risk_notice": risk_notice,
        "markdown": markdown,
        "html": html_body,
        "prepared_at": now_kst(),
    }


def write_outbox(packages):
    OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for package in packages:
        base = slugify(package["asset_id"] or package["title"])
        json_path = OUTBOX_DIR / f"{base}.json"
        md_path = OUTBOX_DIR / f"{base}.md"
        html_path = OUTBOX_DIR / f"{base}.html"
        json_path.write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")
        md_path.write_text(package["markdown"], encoding="utf-8")
        html_path.write_text(package["html"], encoding="utf-8")
        manifest.append({
            "asset_id": package["asset_id"],
            "content_id": package["content_id"],
            "title": package["title"],
            "json": str(json_path),
            "markdown": str(md_path),
            "html": str(html_path),
            "prepared_at": package["prepared_at"],
        })
    (OUTBOX_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main():
    service = sheets_service()
    values = get_values(service)
    if not values:
        raise RuntimeError(f"No rows found in sheet: {ASSETS_SHEET}")
    headers = ensure_headers(service, values)
    values = get_values(service)
    records = records_from_values(headers, values)
    targets = [record for record in records if selected(record)]
    packages = [build_post_package(record) for record in targets]
    manifest = write_outbox(packages)

    for record in targets:
        update_row(service, headers, record, {
            "PublishChannel": "NAVER_BLOG",
            "CredentialStatus": "LOCAL_SESSION_REQUIRED",
            "MediaStatus": "NOT_REQUIRED",
            "ChannelStatus": "READY_FOR_LOCAL_PUBLISH",
            "UploadError": "",
        })

    print(f"prepared naver blog packages: {len(manifest)}")
    for item in manifest:
        print(f"- {item['asset_id']} -> {item['markdown']}")


if __name__ == "__main__":
    main()
