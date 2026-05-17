import json
import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build


SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
CONFIG_PATH = os.environ.get("CONTENT_STRATEGY_CONFIG", "config/content_candidate_strategy.json")

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = [
    "ContentId",
    "TopicId",
    "Category",
    "ExpectedProfitScore",
    "Title",
    "Format",
    "RiskFlag",
    "AIReviewScore",
    "ApprovalStatus",
    "OwnerDecision",
    "CTA",
    "CreatedAt",
    "PublishedAt",
    "ResultUrl",
    "DraftHook",
    "DraftBody",
    "DraftCTA",
    "RiskReviewStatus",
    "GeneratedAt",
    "FinalStatus",
]

BASE_TEMPLATES = [
    {
        "title": "{category}: 사람들이 돈을 쓰는 이유와 바로 써볼 도구 5개",
        "cta": "comparison sheet",
        "risk": "disclosure required",
        "score_boost": 8,
    },
    {
        "title": "{category}: 반복 시간을 줄이는 자동화 루틴 3단계",
        "cta": "workflow checklist",
        "risk": "low risk",
        "score_boost": 6,
    },
    {
        "title": "{category}: 초보자가 실패하기 쉬운 선택 기준 7개",
        "cta": "decision checklist",
        "risk": "low risk",
        "score_boost": 4,
    },
    {
        "title": "{category}: 유료 결제 전에 확인할 가격·기능 비교표",
        "cta": "pricing checklist",
        "risk": "price check",
        "score_boost": 7,
    },
    {
        "title": "{category}: 하루 10분으로 시작하는 저노력 생산성 세팅",
        "cta": "starter template",
        "risk": "low risk",
        "score_boost": 5,
    },
]


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_existing_content_ids(service):
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:A",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    return {row[0] for row in values[1:] if row}


def get_next_number(existing_ids):
    max_num = 0
    for content_id in existing_ids:
        if isinstance(content_id, str) and content_id.startswith("CONTENT-"):
            try:
                max_num = max(max_num, int(content_id.split("-")[1]))
            except (IndexError, ValueError):
                continue
    return max_num + 1


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def generate_candidates(config, existing_ids):
    random.seed(datetime.now().strftime("%Y-%m-%d"))
    max_new = int(config["candidate_rules"].get("max_new_candidates_per_run", 5))
    min_score = int(config["candidate_rules"].get("min_expected_profit_score", 75))
    next_num = get_next_number(existing_ids)
    created_at = now_kst()

    rows = []
    categories = config.get("audience_categories", [])
    random.shuffle(categories)
    templates = BASE_TEMPLATES[:]
    random.shuffle(templates)

    for category_info in categories:
        if len(rows) >= max_new:
            break
        template = templates[len(rows) % len(templates)]
        category = category_info["category"]
        motives = ", ".join(category_info.get("spending_motives", [])[:3])
        formats = category_info.get("formats", ["Blog"])
        fmt = " and ".join(formats[:2])
        score = min(99, min_score + template["score_boost"] + random.randint(0, 8))
        content_id = f"CONTENT-{next_num:03d}"
        topic_id = f"TOPIC-{next_num:03d}"
        next_num += 1
        title = template["title"].format(category=category)
        # Keep title unique enough for repetitive runs.
        if any(title == row[4] for row in rows):
            title = f"{title} - {created_at[:10]}"
        rows.append([
            content_id,
            topic_id,
            category,
            score,
            title,
            fmt,
            template["risk"],
            max(70, score - random.randint(2, 8)),
            config["candidate_rules"].get("approval_status_initial_value", "READY_FOR_OWNER_APPROVAL"),
            config["candidate_rules"].get("owner_decision_initial_value", ""),
            f"{template['cta']} | motive: {motives}",
            created_at,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ])
    return rows


def append_rows(service, rows):
    if not rows:
        print("no rows to append")
        return
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:T",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    print(f"appended candidates: {len(rows)}")
    for row in rows:
        print(f"candidate: {row[0]} | {row[2]} | {row[4]} | score={row[3]}")


def ensure_headers(service):
    current = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1:T1",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if current and current[0][: len(HEADERS)] == HEADERS:
        return
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1:T1",
        valueInputOption="USER_ENTERED",
        body={"values": [HEADERS]},
    ).execute()
    print("headers updated")


def main():
    config = load_config()
    service = sheets_service()
    ensure_headers(service)
    existing_ids = get_existing_content_ids(service)
    rows = generate_candidates(config, existing_ids)
    append_rows(service, rows)


if __name__ == "__main__":
    main()
