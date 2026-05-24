import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
FEEDBACK_SHEET = os.environ.get("STRATEGY_FEEDBACK_SHEET_NAME", "strategy_feedback")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

REQUIRED_COLUMNS = ["FeedbackApplied", "FeedbackDecision", "FeedbackUpdatedAt"]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def svc():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def get_values(service, sheet):
    try:
        return service.spreadsheets().values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{sheet}!A1:AZ5000",
            valueRenderOption="FORMATTED_VALUE",
        ).execute().get("values", [])
    except Exception:
        return []


def ensure_headers(service, values):
    headers = values[0] if values else []
    changed = False
    for col in REQUIRED_COLUMNS:
        if col not in headers:
            headers.append(col)
            changed = True
    if changed:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A1",
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


def to_float(v):
    try:
        return float(str(v or "0").replace(",", ""))
    except ValueError:
        return 0.0


def clamp(v):
    return round(max(0.0, min(1.0, v)), 3)


def update_row(service, headers, row, updates):
    data = [row.get(h, "") for h in headers]
    for k, v in updates.items():
        if k in headers:
            data[headers.index(k)] = v
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A{row['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [data]},
    ).execute()


def feedback_index(feedback_rows):
    by_category = {}
    by_hook = {}
    for r in feedback_rows:
        key = str(r.get("FeedbackKey", "")).strip()
        typ = str(r.get("FeedbackType", "")).strip().upper()
        adj = to_float(r.get("ScoreAdjustment"))
        decision = str(r.get("Decision", "")).strip()
        if not key:
            continue
        if typ == "CATEGORY":
            by_category[key] = {"adjustment": adj, "decision": decision}
        elif typ == "HOOK":
            by_hook[key] = {"adjustment": adj, "decision": decision}
    return by_category, by_hook


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


def main():
    service = svc()
    values = get_values(service, SHEET_NAME)
    if not values:
        print("candidate sheet is empty")
        return
    headers = ensure_headers(service, values)
    values = get_values(service, SHEET_NAME)
    candidate_rows = rows(headers, values)

    fb_values = get_values(service, FEEDBACK_SHEET)
    fb_headers = fb_values[0] if fb_values else []
    fb_rows = rows(fb_headers, fb_values) if fb_values else []
    by_category, by_hook = feedback_index(fb_rows)

    count = 0
    for row in candidate_rows:
        if str(row.get("OwnerDecision", "")).strip():
            continue
        if str(row.get("FinalStatus", "")).strip():
            continue
        eps = to_float(row.get("ExpectedProfitScore"))
        vps = to_float(row.get("ViralPotentialScore"))
        if eps <= 0 and vps <= 0:
            continue
        cat = str(row.get("Category", "")).strip()
        hook = str(row.get("HookConcept", "")).strip()
        cat_fb = by_category.get(cat, {"adjustment": 0.0, "decision": "NO_DATA"})
        hook_fb = by_hook.get(hook, {"adjustment": 0.0, "decision": "NO_DATA"})
        cat_adj = cat_fb["adjustment"]
        hook_adj = hook_fb["adjustment"]
        new_eps = clamp(eps + cat_adj * 0.70)
        new_vps = clamp(vps + cat_adj * 0.50 + hook_adj * 0.80)
        fmt, channel = choose_format(new_eps, new_vps)
        decision = "KEEP"
        if fmt == "Reject":
            decision = "HOLD_OR_REJECT"
        elif new_eps > eps or new_vps > vps:
            decision = "BOOSTED"
        elif new_eps < eps or new_vps < vps:
            decision = "DOWNRANKED"
        updates = {
            "ExpectedProfitScore": new_eps,
            "ViralPotentialScore": new_vps,
            "AIReviewScore": round((new_eps + new_vps) / 2, 3),
            "RecommendedFormat": fmt,
            "Format": fmt,
            "CTA": f"channel={channel} | feedback_applied=true",
            "FeedbackApplied": json.dumps({
                "category": cat,
                "category_adjustment": cat_adj,
                "category_decision": cat_fb["decision"],
                "hook_adjustment": hook_adj,
                "hook_decision": hook_fb["decision"],
            }, ensure_ascii=False),
            "FeedbackDecision": decision,
            "FeedbackUpdatedAt": now_kst(),
        }
        update_row(service, headers, row, updates)
        count += 1
    print(f"feedback applied to candidate rows: {count}")


if __name__ == "__main__":
    main()
