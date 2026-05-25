import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
except Exception:
    service_account = None
    build = None

SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID", "").strip()
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def safe_name(value):
    return re.sub(r"[^0-9A-Za-z가-힣_-]+", "-", str(value or "post")).strip("-") or "post"


def load_posts(inbox):
    files = sorted(Path(inbox).glob("*.json"))
    posts = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            data["_path"] = str(path)
            posts.append(data)
        except Exception as exc:
            print(f"skip invalid json: {path} ({exc})")
    return posts


def compose_body(post):
    body = str(post.get("body", "")).strip()
    caption = str(post.get("caption", "")).strip()
    tags = str(post.get("tags", "")).strip()
    risk = str(post.get("risk_notice", "")).strip()
    checklist = str(post.get("checklist", "")).strip()
    parts = []
    if body:
        parts.append(body)
    elif caption:
        parts.append(caption)
    if risk:
        parts.append("[고지]\n" + risk)
    if tags:
        parts.append("[태그]\n" + tags)
    if checklist:
        parts.append("[발행 전 확인]\n" + checklist)
    return "\n\n".join(parts).strip()


def set_clipboard(text):
    if os.name == "nt":
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value ([Console]::In.ReadToEnd())"],
            input=text,
            text=True,
            encoding="utf-8",
            capture_output=True,
        )
        if completed.returncode == 0:
            return True
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()
        root.destroy()
        return True
    except Exception:
        return False


def sheets_service():
    if not SPREADSHEET_ID or not GOOGLE_SERVICE_ACCOUNT_JSON:
        return None
    if service_account is None or build is None:
        return None
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def sheet_values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def update_sheet(asset_id, target_url, post_id=""):
    service = sheets_service()
    if service is None:
        print("sheet update skipped: SPREADSHEET_ID/GOOGLE_SERVICE_ACCOUNT_JSON not available")
        return False
    values = sheet_values(service)
    if not values:
        print("sheet update skipped: empty sheet")
        return False
    headers = values[0]
    for row_number, row in enumerate(values[1:], start=2):
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        if record.get("AssetId") != asset_id:
            continue
        data = [record.get(h, "") for h in headers]
        updates = {
            "TargetUrl": target_url,
            "PublishedAt": now_kst(),
            "PlatformPostId": post_id or asset_id,
            "ChannelStatus": "PUBLISHED",
            "CredentialStatus": "LOCAL_SESSION_READY",
            "MediaStatus": "NOT_REQUIRED",
            "UploadError": "",
        }
        for key, value in updates.items():
            if key in headers:
                data[headers.index(key)] = value
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A{row_number}",
            valueInputOption="USER_ENTERED",
            body={"values": [data]},
        ).execute()
        print(f"sheet updated: {asset_id}")
        return True
    print(f"sheet update skipped: AssetId not found: {asset_id}")
    return False


def find_first(page, selectors):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=1000):
                return locator
        except Exception:
            continue
    return None


def try_fill_editor(page, title, body):
    title_selectors = [
        "textarea.se-title-text",
        "textarea[placeholder*='제목']",
        "input[placeholder*='제목']",
        "[contenteditable='true'][aria-label*='제목']",
    ]
    body_selectors = [
        "div.se-component-content [contenteditable='true']",
        "div.se-section-text [contenteditable='true']",
        "div[contenteditable='true']",
        "iframe",
    ]

    title_ok = False
    title_box = find_first(page, title_selectors)
    if title_box:
        try:
            title_box.fill(title)
            title_ok = True
        except Exception:
            try:
                title_box.click()
                page.keyboard.insert_text(title)
                title_ok = True
            except Exception:
                pass

    body_ok = False
    if set_clipboard(body):
        body_box = find_first(page, body_selectors)
        if body_box:
            try:
                body_box.click()
                shortcut = "Meta+V" if sys.platform == "darwin" else "Control+V"
                page.keyboard.press(shortcut)
                body_ok = True
            except Exception:
                pass
    return title_ok, body_ok


def post_write_url(blog_id):
    if blog_id:
        return f"https://blog.naver.com/{blog_id}?Redirect=Write"
    return "https://blog.naver.com/"


def publish_one(post, args):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise SystemExit("Missing playwright. Run: pip install -r requirements-local.txt && python -m playwright install chromium")

    title = str(post.get("title", "")).strip()
    body = compose_body(post)
    asset_id = str(post.get("asset_id") or post.get("AssetId") or safe_name(title))
    blog_id = args.blog_id or str(post.get("blog_id", "")).strip()
    url = args.write_url or post_write_url(blog_id)

    print(f"\n=== NAVER BLOG POST ===")
    print(f"asset_id: {asset_id}")
    print(f"title: {title}")
    print(f"url: {url}")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(Path(args.profile_dir).resolve()),
            headless=False,
            viewport={"width": 1440, "height": 1000},
        )
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        input("브라우저에서 네이버 로그인/글쓰기 화면을 확인한 뒤 Enter를 누르세요: ")
        title_ok, body_ok = try_fill_editor(page, title, body)
        if not title_ok:
            set_clipboard(title)
            print("title 자동 입력 실패: 제목이 클립보드에 복사됨. 제목칸에 붙여넣기 하세요.")
            input("제목 입력 후 Enter: ")
        if not body_ok:
            set_clipboard(body)
            print("본문 자동 입력 실패: 본문이 클립보드에 복사됨. 본문칸에 붙여넣기 하세요.")
            input("본문 입력 후 Enter: ")
        print("검토 후 네이버 에디터에서 직접 발행 버튼을 누르세요. 자동 발행 클릭은 기본 비활성화입니다.")
        published_url = input("발행 완료 후 최종 URL을 붙여넣으세요. 아직 발행하지 않았으면 빈값 Enter: ").strip()
        context.close()

    if published_url:
        post_id = published_url.rstrip("/").split("/")[-1]
        update_sheet(asset_id, published_url, post_id=post_id)
        src = Path(post.get("_path", ""))
        if src.exists():
            done_dir = src.parent / "published"
            done_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(done_dir / src.name))
        print(f"published recorded: {published_url}")
    else:
        print("not recorded. The inbox file remains for later retry.")


def main():
    parser = argparse.ArgumentParser(description="Local Naver Blog publisher using an existing browser session.")
    parser.add_argument("--inbox", default="bridge_inbox/naver_blog", help="Directory containing Naver bridge JSON files")
    parser.add_argument("--blog-id", default=os.environ.get("NAVER_BLOG_ID", ""), help="Naver blog ID")
    parser.add_argument("--profile-dir", default=".local/naver_chromium_profile", help="Persistent Chromium profile directory")
    parser.add_argument("--write-url", default="", help="Override Naver write URL")
    parser.add_argument("--asset-id", default="", help="Publish only one asset_id")
    args = parser.parse_args()

    posts = load_posts(args.inbox)
    if args.asset_id:
        posts = [p for p in posts if str(p.get("asset_id", "")) == args.asset_id]
    if not posts:
        print(f"no naver blog inbox json files: {args.inbox}")
        return
    for post in posts:
        publish_one(post, args)


if __name__ == "__main__":
    main()
