import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
MIN_SCORE = int(os.environ.get("MIN_CONTENT_QUALITY_SCORE", "82"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

EXTRA = ["ContentQualityScore", "ContentQualityIssues", "ContentQualityDecision", "ContentRewriteNotes"]
BAD_OPENINGS = ["안녕하세요", "오늘은", "소개합니다", "알아볼게요"]
CRITICAL = {"generic_opening", "plain_list", "no_decision_rule", "social_too_long", "caption_too_long"}


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def svc():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def read_values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service, values):
    headers = values[0] if values else []
    changed = False
    for h in EXTRA:
        if h not in headers:
            headers.append(h); changed = True
    if changed:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    return headers


def rows(headers, values):
    out = []
    for row_no, row in enumerate(values[1:], start=2):
        rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rec["_row_number"] = row_no
        out.append(rec)
    return out


def update_row(service, headers, rec, updates):
    data = [rec.get(h, "") for h in headers]
    for k, v in updates.items():
        if k in headers:
            data[headers.index(k)] = v
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{rec['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [data]},
    ).execute()


def norm(v):
    return str(v or "").strip().upper()


def target(rec):
    if str(rec.get("TargetUrl", "")).strip():
        return False
    if norm(rec.get("PublishDecision")) == "REJECT":
        return False
    return norm(rec.get("ContentQualityDecision")) == "QUALITY_REVIEW_REQUIRED" or norm(rec.get("PublishDecision")) == "HOLD"


def score(rec):
    title = str(rec.get("Title", "")).strip()
    body = str(rec.get("Body", "")).strip()
    caption = str(rec.get("Caption", "")).strip()
    checklist = str(rec.get("Checklist", "")).strip()
    channel = norm(rec.get("PublishChannel"))
    text = " ".join([title, body, caption, checklist])
    issues = []
    s = 100
    if len(title) > 45:
        s -= 12; issues.append("title_too_long")
    if any(title.startswith(x) or body.startswith(x) or caption.startswith(x) for x in BAD_OPENINGS):
        s -= 30; issues.append("generic_opening")
    if re.search(r"5가지|추천|전격 비교|업무 효율", text) and not re.search(r"선택 기준|비교표|체크리스트|상황별", text):
        s -= 35; issues.append("plain_list")
    if not re.search(r"비교|기준|체크리스트|상황별|저장|표|실수|착각", text):
        s -= 25; issues.append("no_decision_rule")
    if channel in {"INSTAGRAM_REELS", "TIKTOK", "YOUTUBE_SHORTS"} and len(caption) > 1200:
        s -= 20; issues.append("caption_too_long")
    if channel in {"THREADS", "X"} and len(body or caption) > 360:
        s -= 25; issues.append("social_too_long")
    if not issues:
        issues = ["passed"]
    return max(0, min(100, s)), issues


def ok(score_value, issues):
    return score_value >= MIN_SCORE and not any(x in CRITICAL for x in issues)


def compact_prompt(rec):
    channel = rec.get("PublishChannel", "")
    return f"""다음 한국어 발행 자산을 더 좋은 버전으로 다시 써라.
채널: {channel}
기존 제목: {rec.get('Title','')}
기존 본문: {rec.get('Body','')}
기존 캡션: {rec.get('Caption','')}
기존 태그: {rec.get('Tags','')}
고지문: {rec.get('RiskNotice','')}

요구사항:
1. 인사말로 시작하지 말 것.
2. 단순 도구 나열 대신 '상황별 선택 기준'으로 쓸 것.
3. Blog는 비교표와 체크리스트를 포함할 것.
4. Reels/TikTok/Shorts는 첫 문장부터 강하게, 짧게 쓸 것.
5. Threads/X는 360자 안팎의 짧은 주장과 기준으로 쓸 것.
6. 과장 보장 표현은 쓰지 말 것. 고지문은 유지할 것.

JSON만 반환:
{{"Title":"","Body":"","Caption":"","Tags":"","Checklist":"","RiskNotice":"","RewriteNotes":""}}
"""


def parse_json(text):
    s = text.strip()
    if s.startswith("```json"):
        s = s[7:].strip()
    if s.startswith("```"):
        s = s[3:].strip()
    if s.endswith("```"):
        s = s[:-3].strip()
    return json.loads(s)


def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    res = requests.post(
        url,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=90,
    )
    res.raise_for_status()
    return parse_json(res.json()["candidates"][0]["content"]["parts"][0]["text"])


def main():
    service = svc()
    values = read_values(service)
    if not values:
        raise RuntimeError(f"No rows found in {ASSETS_SHEET}")
    headers = ensure_headers(service, values)
    values = read_values(service)
    count = 0
    approved = 0
    for rec in [r for r in rows(headers, values) if target(r)]:
        try:
            new_asset = call_gemini(compact_prompt(rec))
            candidate = dict(rec)
            for src, dst in [("Title", "Title"), ("Body", "Body"), ("Caption", "Caption"), ("Tags", "Tags"), ("Checklist", "Checklist"), ("RiskNotice", "RiskNotice")]:
                candidate[dst] = new_asset.get(src, rec.get(dst, ""))
            sc, issues = score(candidate)
            passed = ok(sc, issues)
            updates = {
                "Title": candidate.get("Title", ""),
                "Body": candidate.get("Body", ""),
                "Caption": candidate.get("Caption", ""),
                "Tags": candidate.get("Tags", ""),
                "Checklist": candidate.get("Checklist", ""),
                "RiskNotice": candidate.get("RiskNotice", ""),
                "ContentQualityScore": str(sc),
                "ContentQualityIssues": ",".join(issues),
                "ContentQualityDecision": "QUALITY_APPROVED" if passed else "QUALITY_REVIEW_REQUIRED",
                "ContentRewriteNotes": f"{now_kst()} {new_asset.get('RewriteNotes','rewritten')}",
                "ChannelStatus": "QUALITY_APPROVED" if passed else "QUALITY_REVIEW_REQUIRED",
                "UploadError": "" if passed else "rewrite done but quality gate still failed",
                "PublishDecision": "APPROVE" if passed else "HOLD",
            }
            update_row(service, headers, rec, updates)
            approved += 1 if passed else 0
            count += 1
        except Exception as exc:
            update_row(service, headers, rec, {
                "ContentRewriteNotes": f"{now_kst()} rewrite failed",
                "UploadError": str(exc)[:500],
                "ChannelStatus": "QUALITY_REWRITE_FAILED",
            })
    print(f"rewrite processed={count}, approved={approved}")


if __name__ == "__main__":
    main()
