import json
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

HEADERS = [
    "AssetId", "ContentId", "AssetType", "PublishChannel", "Title", "Body", "Caption",
    "Tags", "Checklist", "RiskNotice", "GeneratedAt", "AssetStatus", "PublishDecision",
    "TargetUrl", "PublishedAt", "PerformanceCheckDate", "Views", "Clicks", "Revenue",
    "TrackingNotes", "ChannelStatus", "CredentialStatus", "MediaStatus", "PlatformPostId",
    "UploadError", "MediaFilePath"
]

TARGET_CHANNELS = ["NAVER_BLOG", "INSTAGRAM_REELS", "TIKTOK", "THREADS", "X"]


def now_kst():
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def svc():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def values(service):
    return service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A1:AZ5000",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])


def ensure_headers(service, vals):
    headers = vals[0] if vals else []
    changed = False
    for h in HEADERS:
        if h not in headers:
            headers.append(h)
            changed = True
    if changed:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    return headers


def rows(headers, vals):
    out = []
    for row_no, row in enumerate(vals[1:], start=2):
        rec = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        rec["_row_number"] = row_no
        out.append(rec)
    return out


def norm(v):
    return str(v or "").strip().upper()


def existing_ids(records):
    return {r.get("AssetId", "") for r in records if r.get("AssetId")}


def base_for_content(records):
    by_content = {}
    for r in records:
        cid = r.get("ContentId", "")
        if not cid:
            continue
        by_content.setdefault(cid, {})
        if norm(r.get("AssetType")) == "BLOG":
            by_content[cid]["blog"] = r
        if norm(r.get("AssetType")) == "SHORTS":
            by_content[cid]["shorts"] = r
    return by_content


def asset_text(source, channel):
    title = source.get("Title", "")
    caption = source.get("Caption", "") or source.get("Body", "")
    risk = source.get("RiskNotice", "")
    tags = source.get("Tags", "")
    if channel == "NAVER_BLOG":
        return "Blog", title, source.get("Body", ""), caption, tags
    if channel == "INSTAGRAM_REELS":
        return "Shorts", title[:80], "", (caption[:1800] + "\n\n저장해두고 필요할 때 확인하세요."), tags
    if channel == "TIKTOK":
        return "Shorts", title[:80], "", (caption[:1200] + "\n\n더 자세한 비교는 프로필 링크에서 확인."), tags
    if channel == "THREADS":
        body = (caption or title)[:450]
        return "Social", title[:80], body, body, tags
    if channel == "X":
        body = (caption or title)[:250]
        return "Social", title[:80], body, body, tags
    return "Social", title, caption, caption, tags


def main():
    service = svc()
    vals = values(service)
    if not vals:
        print("publish_assets empty")
        return
    headers = ensure_headers(service, vals)
    vals = values(service)
    records = rows(headers, vals)
    ids = existing_ids(records)
    by_content = base_for_content(records)
    created = now_kst()
    new_rows = []

    for cid, group in by_content.items():
        blog = group.get("blog")
        shorts = group.get("shorts")
        source_any = blog or shorts
        if not source_any:
            continue
        for channel in TARGET_CHANNELS:
            source = blog if channel == "NAVER_BLOG" and blog else shorts or blog
            if not source:
                continue
            asset_type, title, body, caption, tags = asset_text(source, channel)
            asset_id = f"ASSET-{cid}-{channel}"
            if asset_id in ids:
                continue
            row = {h: "" for h in headers}
            row.update({
                "AssetId": asset_id,
                "ContentId": cid,
                "AssetType": asset_type,
                "PublishChannel": channel,
                "Title": title,
                "Body": body,
                "Caption": caption,
                "Tags": tags,
                "Checklist": source.get("Checklist", ""),
                "RiskNotice": source.get("RiskNotice", ""),
                "GeneratedAt": created,
                "AssetStatus": "ASSET_READY",
                "PublishDecision": "",
                "ChannelStatus": "WAITING_APPROVAL",
                "CredentialStatus": "CHECK_REQUIRED",
                "MediaStatus": "READY" if channel in {"INSTAGRAM_REELS", "TIKTOK"} and source.get("MediaFilePath") else "NOT_REQUIRED",
                "MediaFilePath": source.get("MediaFilePath", "") if channel in {"INSTAGRAM_REELS", "TIKTOK"} else "",
                "UploadError": "Cross-platform derivative. Review before approval.",
            })
            new_rows.append([row.get(h, "") for h in headers])
            ids.add(asset_id)

    if new_rows:
        service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A:AZ",
            valueInputOption="USER_ENTERED",
            insertDataOption="INSERT_ROWS",
            body={"values": new_rows},
        ).execute()
    print(f"cross-platform assets added: {len(new_rows)}")


if __name__ == "__main__":
    main()
