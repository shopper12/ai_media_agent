import os
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(os.environ.get("BROWSER_SESSION_STATE_FILE", "browser_session_state.json"))
START_URL = os.environ.get("BROWSER_SESSION_START_URL", "https://blog.naver.com")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(START_URL, wait_until="domcontentloaded")
        print("Log in in the opened browser window, then press Enter here.")
        input()
        context.storage_state(path=str(OUT))
        browser.close()
    print(f"saved: {OUT}")


if __name__ == "__main__":
    main()
