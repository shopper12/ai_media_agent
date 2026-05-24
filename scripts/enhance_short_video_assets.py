import json
import os
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
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

EXTRA_COLUMNS = [
    "ResearchBenchmark",
    "ChosenEmotionalTrigger",
    "ChosenHookPattern",
    "ThumbnailMainText",
    "ThumbnailSubText",
    "ShortsTitle",
    "ShortsScriptJson",
    "OnScreenTextOverlays",
    "EstimatedCompletionRate",
    "CompletionRateReason",
    "ScriptApprovalStatus",
    "QualityChecklist",
]

BANNED = ["안녕하세요", "오늘은", "알아볼게요", "도움이 되셨길"]


def now_kst():
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
    for col in EXTRA_COLUMNS:
        if col not in headers:
            headers.append(col)
            changed = True
    if changed:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    return headers


def records(headers, values):
    rows = []
    for row_number, row in enumerate(values[1:], start=2):
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        item["_row_number"] = row_number
        rows.append(item)
    return rows


def update_row(service, headers, row, updates):
    data = [row.get(h, "") for h in headers]
    for key, value in updates.items():
        if key in headers:
            data[headers.index(key)] = value
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{row['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [data]},
    ).execute()


def norm(value):
    return str(value or "").strip().upper()


def is_short(row):
    channel = norm(row.get("PublishChannel"))
    kind = norm(row.get("AssetType"))
    return channel in {"YOUTUBE_SHORTS", "SHORTS", "YOUTUBE", "YOUTUBE SHORTS"} or kind in {"SHORTS", "YOUTUBE SHORTS"}


def selected(row):
    return norm(row.get("PublishDecision")) == "APPROVE" and is_short(row) and not row.get("TargetUrl") and norm(row.get("ScriptApprovalStatus")) != "SCRIPT_APPROVED"


def parse_json(text):
    s = text.strip()
    if s.startswith("```json"):
        s = s[7:].strip()
    if s.startswith("```"):
        s = s[3:].strip()
    if s.endswith("```"):
        s = s[:-3].strip()
    return json.loads(s)


def build_prompt(row):
    return f"""한국어 쇼츠 대본을 만든다. 목적은 끝까지 보기 쉬운 영상 대본이다.

입력:
제목: {row.get('Title', '')}
본문: {row.get('Body', '')}
캡션: {row.get('Caption', '')}
태그: {row.get('Tags', '')}
주의문: {row.get('RiskNotice', '')}

규칙:
1. 첫 문장은 2초 안에 볼 이유가 보여야 한다.
2. '안녕하세요', '오늘은 알아볼게요'로 시작하지 않는다.
3. 리스트를 읽는 느낌보다 문제-반전-해결 흐름으로 쓴다.
4. CTA는 구걸하지 말고 저장/다음 영상/링크의 실익을 말한다.
5. 수익, 건강, 효과 보장 표현은 쓰지 않는다.
6. 썸네일 메인 문구는 3~5단어로 쓴다.

반드시 JSON만 반환한다.
{{
  "research_benchmark": {{
    "representative_hook": "경쟁 영상에서 흔한 첫 문장 패턴",
    "thumbnail_text_pattern": "흔한 썸네일 문구 패턴",
    "weakness_to_improve": "우리 영상이 이겨야 할 약점"
  }},
  "chosen_emotional_trigger": "모르면 손해|공감|반전|똑똑해 보임",
  "chosen_hook_pattern": "선택한 훅 패턴",
  "shorts_title": "40자 이내 제목",
  "thumbnail_main_text": "3~5단어",
  "thumbnail_sub_text": "보조 문구",
  "script": [
    {{"second":"0-2","line":"훅","visual_note":"화면"}},
    {{"second":"2-8","line":"공감","visual_note":"화면"}},
    {{"second":"8-30","line":"핵심1","visual_note":"화면"}},
    {{"second":"30-50","line":"핵심2","visual_note":"화면"}},
    {{"second":"50-60","line":"가치 제안 CTA","visual_note":"화면"}}
  ],
  "on_screen_text_overlays": ["짧은 자막1", "짧은 자막2", "짧은 자막3"],
  "estimated_completion_rate": "HIGH|MEDIUM|LOW",
  "completion_rate_reason": "판단 이유",
  "quality_checklist": {{
    "clear_first_2s": true,
    "relatable_pain": true,
    "simple_words": true,
    "value_based_cta": true,
    "thumbnail_short": true,
    "no_banned_opening": true
  }}
}}
"""


def call_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    res = requests.post(
        url,
        headers={"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    res.raise_for_status()
    text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
    return parse_json(text)


def validate(asset):
    script = asset.get("script") or []
    first = script[0].get("line", "") if script else ""
    if len(script) < 5:
        return "REVISE_REQUIRED"
    if any(x in first for x in BANNED):
        return "REVISE_REQUIRED"
    checklist = asset.get("quality_checklist") or {}
    if isinstance(checklist, dict) and not all(bool(v) for v in checklist.values()):
        return "REVISE_REQUIRED"
    return "SCRIPT_APPROVED"


def main():
    svc = sheets_service()
    values = get_values(svc)
    if not values:
        raise RuntimeError(f"No rows found in {ASSETS_SHEET}")
    headers = ensure_headers(svc, values)
    values = get_values(svc)
    rows = records(headers, values)
    count = 0
    for row in [r for r in rows if selected(r)]:
        try:
            asset = call_gemini(build_prompt(row))
            status = validate(asset)
            update_row(svc, headers, row, {
                "ResearchBenchmark": json.dumps(asset.get("research_benchmark", {}), ensure_ascii=False),
                "ChosenEmotionalTrigger": asset.get("chosen_emotional_trigger", ""),
                "ChosenHookPattern": asset.get("chosen_hook_pattern", ""),
                "ThumbnailMainText": asset.get("thumbnail_main_text", ""),
                "ThumbnailSubText": asset.get("thumbnail_sub_text", ""),
                "ShortsTitle": asset.get("shorts_title", ""),
                "ShortsScriptJson": json.dumps(asset.get("script", []), ensure_ascii=False),
                "OnScreenTextOverlays": json.dumps(asset.get("on_screen_text_overlays", []), ensure_ascii=False),
                "EstimatedCompletionRate": asset.get("estimated_completion_rate", ""),
                "CompletionRateReason": asset.get("completion_rate_reason", ""),
                "ScriptApprovalStatus": status,
                "QualityChecklist": json.dumps(asset.get("quality_checklist", {}), ensure_ascii=False),
                "ChannelStatus": "SCRIPT_READY" if status == "SCRIPT_APPROVED" else "SCRIPT_REVIEW_REQUIRED",
                "UploadError": "" if status == "SCRIPT_APPROVED" else "script quality check failed",
            })
            count += 1
        except Exception as exc:
            update_row(svc, headers, row, {
                "ScriptApprovalStatus": "SCRIPT_FAILED",
                "ChannelStatus": "SCRIPT_FAILED",
                "UploadError": str(exc)[:500],
            })
    print(f"enhanced short video assets: {count} at {now_kst()}")


if __name__ == "__main__":
    main()
