import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
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


def configure_console_encoding():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


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


def set_clipboard_tk(text):
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(str(text))
    root.update()
    root.destroy()
    return True


def set_clipboard_powershell_utf8(text):
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".txt", delete=False) as f:
            f.write(str(text))
            temp_path = f.name
        literal = json.dumps(temp_path)
        command = f"$v = Get-Content -LiteralPath {literal} -Raw -Encoding UTF8; Set-Clipboard -Value $v"
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.returncode == 0
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass


def set_clipboard(text):
    text = str(text or "")
    try:
        return set_clipboard_tk(text)
    except Exception:
        pass
    if os.name == "nt":
        return set_clipboard_powershell_utf8(text)
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


def find_first(page, selectors, timeout_ms=1000):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=timeout_ms):
                return locator
        except Exception:
            continue
    return None


def paste_text(page, text):
    if set_clipboard(text):
        shortcut = "Meta+V" if sys.platform == "darwin" else "Control+V"
        page.keyboard.press(shortcut)
        return True
    page.keyboard.insert_text(str(text))
    return True


def try_fill_title(page, title):
    selectors = [
        "textarea.se-title-text",
        "textarea[placeholder*='제목']",
        "input[placeholder*='제목']",
        "[contenteditable='true'][aria-label*='제목']",
        "[contenteditable='true']:near(:text('제목'))",
    ]
    box = find_first(page, selectors)
    if not box:
        return False
    try:
        box.fill(title)
        return True
    except Exception:
        try:
            box.click()
            page.keyboard.press("Control+A")
            page.keyboard.press("Backspace")
            return paste_text(page, title)
        except Exception:
            return False


def try_fill_body(page, body):
    selectors = [
        "div.se-component-content [contenteditable='true']",
        "div.se-section-text [contenteditable='true']",
        "div[contenteditable='true']",
    ]
    box = find_first(page, selectors, timeout_ms=2000)
    if not box:
        return False
    try:
        box.click()
        return paste_text(page, body)
    except Exception:
        return False


def try_fill_editor(page, title, body):
    title_ok = try_fill_title(page, title)
    body_ok = try_fill_body(page, body)
    return title_ok, body_ok


def click_first_visible(page, selectors, timeout_ms=1200):
    for selector in selectors:
        try:
            locator = page.locator(selector).first
            if locator.count() > 0 and locator.is_visible(timeout=timeout_ms):
                locator.click(timeout=timeout_ms)
                return selector
        except Exception:
            continue
    return ""


def try_auto_publish(page, wait_seconds):
    first_selectors = [
        "button:has-text('발행')",
        "a:has-text('발행')",
        "text=발행",
        "button:has-text('등록')",
        "a:has-text('등록')",
        "text=등록",
    ]
    confirm_selectors = [
        "button:has-text('확인')",
        "button:has-text('발행')",
        "a:has-text('발행')",
        "button:has-text('등록')",
        "text=확인",
    ]
    clicked = click_first_visible(page, first_selectors)
    if not clicked:
        print("auto publish: no publish button found")
        return ""
    print(f"auto publish: clicked {clicked}")
    page.wait_for_timeout(1500)
    clicked2 = click_first_visible(page, confirm_selectors)
    if clicked2:
        print(f"auto publish: clicked confirm {clicked2}")
    for _ in range(max(1, wait_seconds)):
        page.wait_for_timeout(1000)
        current = page.url
        if "blog.naver.com" in current and "Redirect=Write" not in current and "PostWrite" not in current:
            return current
    return ""


def post_write_url(blog_id):
    if blog_id:
        return f"https://blog.naver.com/{blog_id}?Redirect=Write"
    return "https://blog.naver.com/"


def publish_one(post, args):
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        raise SystemExit("Missing playwright. Run: pip install -r local_requirements.txt && python -m playwright install chromium")

    title = str(post.get("title", "")).strip()
    body = compose_body(post)
    asset_id = str(post.get("asset_id") or post.get("AssetId") or safe_name(title))
    blog_id = args.blog_id or str(post.get("blog_id", "")).strip()
    url = args.write_url or post_write_url(blog_id)

    print("\n=== NAVER BLOG POST ===")
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
        if not args.no_initial_pause:
            input("브라우저에서 네이버 로그인/글쓰기 화면을 확인한 뒤 Enter를 누르세요: ")
        title_ok, body_ok = try_fill_editor(page, title, body)
        if not title_ok:
            set_clipboard(title)
            print("제목 자동 입력 실패: 제목이 유니코드 클립보드에 복사됨. 제목칸에 붙여넣기 하세요.")
            input("제목 입력 후 Enter: ")
        if not body_ok:
            set_clipboard(body)
            print("본문 자동 입력 실패: 본문이 유니코드 클립보드에 복사됨. 본문칸에 붙여넣기 하세요.")
            input("본문 입력 후 Enter: ")

        published_url = ""
        if args.auto_publish:
            print("auto publish mode: 발행 버튼 자동 클릭을 시도합니다. 캡차/보안확인/팝업은 수동 처리해야 합니다.")
            published_url = try_auto_publish(page, args.auto_publish_wait)
            if not published_url:
                print("auto publish mode: 최종 URL 자동 확인 실패")
        else:
            print("검토 후 네이버 에디터에서 직접 발행 버튼을 누르세요. 자동 발행 클릭은 기본 비활성화입니다.")

        if not published_url:
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
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="Local Naver Blog publisher using an existing browser session.")
    parser.add_argument("--inbox", default="bridge_inbox/naver_blog", help="Directory containing Naver bridge JSON files")
    parser.add_argument("--blog-id", default=os.environ.get("NAVER_BLOG_ID", ""), help="Naver blog ID")
    parser.add_argument("--profile-dir", default=".local/naver_chromium_profile", help="Persistent Chromium profile directory")
    parser.add_argument("--write-url", default="", help="Override Naver write URL")
    parser.add_argument("--asset-id", default="", help="Publish only one asset_id")
    parser.add_argument("--no-initial-pause", action="store_true", help="Do not pause after opening the editor. Use only after login session is stable.")
    parser.add_argument("--auto-publish", action="store_true", help="Try to click publish/confirm buttons automatically after filling content.")
    parser.add_argument("--auto-publish-wait", type=int, default=20, help="Seconds to wait for final URL after auto publish click.")
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
