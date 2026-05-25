import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
MIN_SCORE = int(os.environ.get("MIN_CONTENT_QUALITY_SCORE", "75"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
EXTRA = ["ContentQualityScore", "ContentQualityIssues", "ContentQualityDecision", "ContentRewriteNotes"]


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


def ensure_headers(svc, values):
    headers = values[0] if values else []
    changed = False
    for h in EXTRA:
        if h not in headers:
            headers.append(h)
            changed = True
    if changed:
        svc.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    return headers


def records(headers, values):
    out = []
    for row_no, row in enumerate(values[1:], start=2):
        rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rec["_row_number"] = row_no
        out.append(rec)
    return out


def update_row(svc, headers, rec, updates):
    data = [rec.get(h, "") for h in headers]
    for key, value in updates.items():
        if key in headers:
            data[headers.index(key)] = value
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{rec['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [data]},
    ).execute()


def norm(v):
    return str(v or "").strip().upper()


def selected(rec):
    if norm(rec.get("PublishDecision")) != "APPROVE":
        return False
    if str(rec.get("TargetUrl", "")).strip():
        return False
    if norm(rec.get("ContentQualityDecision")) == "QUALITY_APPROVED":
        return False
    return bool(str(rec.get("Title") or rec.get("Body") or rec.get("Caption") or "").strip())


def score_asset(rec):
    title = str(rec.get("Title", "")).strip()
    body = str(rec.get("Body", "")).strip()
    caption = str(rec.get("Caption", "")).strip()
    checklist = str(rec.get("Checklist", "")).strip()
    text = " ".join([title, body, caption, checklist])
    channel = norm(rec.get("PublishChannel"))
    issues = []
    score = 100
    if len(title) > 45:
        score -= 12; issues.append("title_too_long")
    if any(x in title[:20] or x in body[:25] for x in ["안녕하세요", "오늘은", "소개합니다", "알아볼게요"]):
        score -= 20; issues.append("generic_opening")
    if re.search(r"5가지|추천|전격 비교|업무 효율", text) and not re.search(r"선택 기준|비교표|체크리스트|상황별", text):
        score -= 25; issues.append("list_without_decision_rule")
    if not re.search(r"손해|착각|실수|비교|기준|체크리스트|표|상황별|저장", text):
        score -= 18; issues.append("weak_hook_or_save_reason")
    if channel in {"YOUTUBE_SHORTS", "INSTAGRAM_REELS", "TIKTOK"} and len(caption) > 1500:
        score -= 10; issues.append("caption_too_long_for_short_video")
    if channel in {"THREADS", "X"} and len(body or caption) > 500:
        score -= 20; issues.append("social_text_too_long")
    if len(issues) == 0:
        issues.append("passed")
    return max(0, min(100, score)), issues


def main():
    svc = service()
    values = read_values(svc)
    if not values:
        raise RuntimeError(f"No rows found in {ASSETS_SHEET}")
    headers = ensure_headers(svc, values)
    values = read_values(svc)
    processed = 0
    held = 0
    for rec in [r for r in records(headers, values) if selected(r)]:
        score, issues = score_asset(rec)
        ok = score >= MIN_SCORE
        updates = {
            "ContentQualityScore": str(score),
            "ContentQualityIssues": ",".join(issues),
            "ContentQualityDecision": "QUALITY_APPROVED" if ok else "QUALITY_REVIEW_REQUIRED",
            "ContentRewriteNotes": f"{now_kst()} quality gate checked",
            "ChannelStatus": "QUALITY_APPROVED" if ok else "QUALITY_REVIEW_REQUIRED",
            "UploadError": "" if ok else "quality gate failed; rewrite before publishing",
        }
        if not ok:
            updates["PublishDecision"] = "HOLD"
            held += 1
        update_row(svc, headers, rec, updates)
        processed += 1
    print(f"quality gate processed={processed}, held={held}")


if __name__ == "__main__":
    main()
