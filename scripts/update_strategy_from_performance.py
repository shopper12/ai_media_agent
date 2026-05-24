import json
import os
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
FEEDBACK_SHEET = os.environ.get("STRATEGY_FEEDBACK_SHEET_NAME", "strategy_feedback")
VIEW_BASELINE = float(os.environ.get("VIEW_BASELINE", "1000"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

FEEDBACK_HEADERS = [
    "GeneratedAt",
    "FeedbackKey",
    "FeedbackType",
    "Category",
    "HookPattern",
    "PublishChannel",
    "AssetCount",
    "PublishedCount",
    "TotalViews",
    "TotalLikes",
    "TotalComments",
    "AvgViews",
    "EngagementRate",
    "ScoreAdjustment",
    "Decision",
    "Notes",
]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def sheet_id(svc, name):
    meta = svc.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    for sh in meta.get("sheets", []):
        if sh.get("properties", {}).get("title") == name:
            return sh.get("properties", {}).get("sheetId")
    return None


def ensure_sheet(svc, name, headers):
    if sheet_id(svc, name) is None:
        svc.spreadsheets().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": [{"addSheet": {"properties": {"title": name}}}]},
        ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{name}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [headers]},
    ).execute()


def read_records(svc, name):
    values = svc.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{name}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if not values:
        return [], []
    headers = values[0]
    rows = []
    for index, row in enumerate(values[1:], start=2):
        item = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        item["_row_number"] = index
        rows.append(item)
    return headers, rows


def to_float(value):
    try:
        return float(str(value or "0").replace(",", ""))
    except ValueError:
        return 0.0


def norm(value):
    return str(value or "").strip()


def content_lookup(candidates):
    return {r.get("ContentId", ""): r for r in candidates if r.get("ContentId")}


def score_adjustment(avg_views, engagement_rate):
    view_ratio = avg_views / VIEW_BASELINE if VIEW_BASELINE else 0
    raw = (view_ratio - 1.0) * 0.08 + engagement_rate * 0.20
    if avg_views == 0:
        raw -= 0.06
    return round(max(-0.12, min(0.12, raw)), 3)


def decision_from(adj, published_count):
    if published_count == 0:
        return "NO_DATA"
    if adj >= 0.04:
        return "BOOST"
    if adj <= -0.04:
        return "CUT_OR_REWRITE"
    return "KEEP_TESTING"


def add_bucket(buckets, key, asset, candidate):
    b = buckets[key]
    b["assets"] += 1
    if asset.get("TargetUrl"):
        b["published"] += 1
    b["views"] += to_float(asset.get("Views"))
    b["likes"] += to_float(asset.get("Likes"))
    b["comments"] += to_float(asset.get("Comments"))
    b["category"] = candidate.get("Category", asset.get("AssetType", ""))
    b["hook"] = norm(asset.get("ChosenHookPattern") or candidate.get("HookConcept") or asset.get("ThumbnailMainText"))
    b["channel"] = norm(asset.get("PublishChannel"))


def build_feedback(candidates, assets):
    lookup = content_lookup(candidates)
    generated_at = now_kst()
    buckets = defaultdict(lambda: {"assets": 0, "published": 0, "views": 0.0, "likes": 0.0, "comments": 0.0, "category": "", "hook": "", "channel": ""})

    for asset in assets:
        if not asset.get("PlatformPostId") and not asset.get("TargetUrl"):
            continue
        candidate = lookup.get(asset.get("ContentId", ""), {})
        category = norm(candidate.get("Category") or asset.get("AssetType") or "UNKNOWN")
        hook = norm(asset.get("ChosenHookPattern") or candidate.get("HookConcept") or asset.get("ThumbnailMainText") or "UNKNOWN")
        channel = norm(asset.get("PublishChannel") or "UNKNOWN")
        add_bucket(buckets, ("CATEGORY", category), asset, candidate)
        add_bucket(buckets, ("HOOK", hook), asset, candidate)
        add_bucket(buckets, ("CHANNEL", channel), asset, candidate)

    rows = []
    for (feedback_type, feedback_key), data in sorted(buckets.items()):
        published = data["published"]
        avg_views = data["views"] / published if published else 0
        engagement_rate = (data["likes"] + data["comments"]) / data["views"] if data["views"] else 0
        adj = score_adjustment(avg_views, engagement_rate)
        decision = decision_from(adj, published)
        notes = ""
        if decision == "BOOST":
            notes = "Increase future EPS/VPS slightly for this pattern."
        elif decision == "CUT_OR_REWRITE":
            notes = "Reduce priority or rewrite hook/thumbnail before reuse."
        elif decision == "KEEP_TESTING":
            notes = "Insufficient edge; keep limited tests."
        else:
            notes = "No published metric yet."
        rows.append([
            generated_at,
            feedback_key,
            feedback_type,
            data["category"] if feedback_type != "CATEGORY" else feedback_key,
            data["hook"] if feedback_type != "HOOK" else feedback_key,
            data["channel"] if feedback_type != "CHANNEL" else feedback_key,
            data["assets"],
            published,
            int(data["views"]),
            int(data["likes"]),
            int(data["comments"]),
            round(avg_views, 2),
            round(engagement_rate, 4),
            adj,
            decision,
            notes,
        ])
    if not rows:
        rows.append([generated_at, "NO_DATA", "SYSTEM", "", "", "", 0, 0, 0, 0, 0, 0, 0, 0, "NO_DATA", "No published assets with metrics yet."])
    return rows


def write_feedback(svc, rows):
    ensure_sheet(svc, FEEDBACK_SHEET, FEEDBACK_HEADERS)
    svc.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{FEEDBACK_SHEET}!A2:Z5000",
        body={},
    ).execute()
    svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{FEEDBACK_SHEET}!A2",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()


def main():
    svc = service()
    _, candidates = read_records(svc, SHEET_NAME)
    _, assets = read_records(svc, ASSETS_SHEET)
    feedback = build_feedback(candidates, assets)
    write_feedback(svc, feedback)
    print(f"strategy feedback rows: {len(feedback)}")


if __name__ == "__main__":
    main()
