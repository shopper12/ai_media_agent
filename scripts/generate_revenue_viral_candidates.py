import json
import os
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
    "ContentId", "TopicId", "Category", "ExpectedProfitScore", "Title", "Format",
    "RiskFlag", "AIReviewScore", "ApprovalStatus", "OwnerDecision", "CTA", "CreatedAt",
    "PublishedAt", "ResultUrl", "DraftHook", "DraftBody", "DraftCTA", "RiskReviewStatus",
    "GeneratedAt", "FinalStatus", "ViralPotentialScore", "RecommendedFormat", "HookConcept",
    "ViralTrigger", "AffiliateProgram", "EstimatedUnitValue", "RiskLevel", "OwnerActionSuggestion",
    "ScoreBreakdown", "ExperimentFormat", "NextTrendSeed"
]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def read_values(svc):
    return svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1:AZ1000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(svc):
    values = read_values(svc)
    headers = values[0] if values else []
    for h in HEADERS:
        if h not in headers:
            headers.append(h)
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()
    return headers


def next_no(rows, headers):
    if "ContentId" not in headers:
        return 1
    idx = headers.index("ContentId")
    out = 0
    for row in rows[1:]:
        if idx < len(row) and str(row[idx]).startswith("CONTENT-"):
            try:
                out = max(out, int(str(row[idx]).split("-")[1]))
            except Exception:
                pass
    return out + 1


def weighted(metrics, weights):
    return round(sum(float(metrics.get(k, 0)) * float(v) for k, v in weights.items()), 3)


def choose_format(eps, vps):
    if eps >= 0.55 and vps >= 0.80:
        return "Both", "NAVER_BLOG, YOUTUBE_SHORTS, TIKTOK"
    if eps >= 0.55 and vps >= 0.65:
        return "Both", "NAVER_BLOG, YOUTUBE_SHORTS"
    if eps >= 0.55 and vps >= 0.60:
        return "Both", "NAVER_BLOG, INSTAGRAM_REELS"
    if eps >= 0.55:
        return "Blog", "NAVER_BLOG"
    if vps >= 0.60:
        return "Shorts", "YOUTUBE_SHORTS"
    return "Reject", ""


def hook(title):
    if "무료" in title:
        return "이 무료 도구를 몰라서 아직도 시간을 버리고 있습니다."
    if "손해" in title or "돈" in title:
        return "이걸 모르고 결제하면 진짜 손해입니다."
    if "환급" in title or "세금" in title:
        return "대부분이 놓쳐서 못 돌려받는 항목이 있습니다."
    return "이 작업 아직도 직접 하면 시간을 버리는 겁니다."


def trigger(title):
    if "체크리스트" in title or "비교" in title:
        return "저장해야 함"
    if "모르는" in title or "손해" in title:
        return "친구한테 보내야 함"
    return "나도 몰랐다"


def main():
    cfg = json.load(open(CONFIG_PATH, encoding="utf-8"))
    eps_w = cfg["scoring"]["expected_profit_score"]["weights"]
    vps_w = cfg["scoring"]["viral_potential_score"]["weights"]
    max_new = int(cfg.get("decision_queue", {}).get("max_candidates_per_week", 7))
    svc = service()
    headers = ensure_headers(svc)
    values = read_values(svc)
    n = next_no(values, headers)
    created = now_kst()
    experiments = cfg.get("experiment_formats", [])
    trends = cfg.get("next_trend_seed_topics", [])
    rows = []
    for tier in cfg.get("topic_tiers", []):
        for title in tier.get("title_patterns", []):
            if len(rows) >= max_new:
                break
            m = tier.get("base_metrics", {})
            eps = weighted(m, eps_w)
            vps = weighted(m, vps_w)
            fmt, channel = choose_format(eps, vps)
            if fmt == "Reject":
                continue
            risk = tier.get("risk_level", "MEDIUM")
            row = {h: "" for h in headers}
            row.update({
                "ContentId": f"CONTENT-{n:03d}",
                "TopicId": f"TOPIC-{n:03d}",
                "Category": tier.get("category", ""),
                "ExpectedProfitScore": eps,
                "Title": title,
                "Format": fmt,
                "RiskFlag": "disclosure required" if risk != "LOW" else "low risk",
                "AIReviewScore": round((eps + vps) / 2, 3),
                "ApprovalStatus": "READY_FOR_OWNER_APPROVAL",
                "CTA": f"channel={channel} | affiliate={tier.get('affiliate_program', '')}",
                "CreatedAt": created,
                "ViralPotentialScore": vps,
                "RecommendedFormat": fmt,
                "HookConcept": hook(title),
                "ViralTrigger": trigger(title),
                "AffiliateProgram": tier.get("affiliate_program", ""),
                "EstimatedUnitValue": tier.get("estimated_unit_value", ""),
                "RiskLevel": risk,
                "OwnerActionSuggestion": "APPROVE" if risk == "LOW" else "HOLD",
                "ScoreBreakdown": json.dumps(m, ensure_ascii=False),
                "ExperimentFormat": experiments[len(rows) % len(experiments)] if experiments else "",
                "NextTrendSeed": trends[len(rows) % len(trends)] if trends else "",
            })
            rows.append([row.get(h, "") for h in headers])
            n += 1
        if len(rows) >= max_new:
            break
    if rows:
        svc.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A:AZ",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
    print(f"appended EPS/VPS candidates: {len(rows)}")


if __name__ == "__main__":
    main()
