import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from PIL import Image, ImageDraw, ImageFont

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
OUT_DIR = Path(os.environ.get("SHORT_VIDEO_OUT_DIR", "generated/short_videos"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

REQUIRED_COLUMNS = [
    "PublishDecision",
    "PublishChannel",
    "ChannelStatus",
    "CredentialStatus",
    "MediaStatus",
    "MediaFilePath",
    "TargetUrl",
    "PlatformPostId",
    "PublishedAt",
    "UploadError",
]


def now_kst() -> str:
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
    for column in REQUIRED_COLUMNS:
        if column not in headers:
            headers.append(column)
            changed = True
    if changed:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{ASSETS_SHEET}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [headers]},
        ).execute()
    return headers


def records_from_values(headers, values):
    records = []
    for row_number, row in enumerate(values[1:], start=2):
        record = {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}
        record["_row_number"] = row_number
        records.append(record)
    return records


def update_row(service, headers, record, updates):
    row = [record.get(header, "") for header in headers]
    for key, value in updates.items():
        if key in headers:
            row[headers.index(key)] = value
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{record['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def norm(value) -> str:
    return str(value or "").strip().upper()


def is_short_target(record):
    channel = norm(record.get("PublishChannel"))
    asset_type = norm(record.get("AssetType"))
    return channel in {"YOUTUBE_SHORTS", "SHORTS", "YOUTUBE", "YOUTUBE SHORTS"} or asset_type in {"SHORTS", "YOUTUBE SHORTS"}


def selected(record):
    return norm(record.get("PublishDecision")) == "APPROVE" and is_short_target(record) and not str(record.get("MediaFilePath", "")).strip()


def slugify(value):
    slug = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "-", str(value or "short")).strip("-").lower()
    return slug or "short"


def find_font():
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return path
    return None


def wrap_text(draw, text, font, max_width):
    words = re.split(r"(\s+)", text)
    lines = []
    current = ""
    for word in words:
        trial = current + word
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current.strip():
                lines.append(current.strip())
            current = word.strip()
    if current.strip():
        lines.append(current.strip())
    return lines


def make_slide(record, out_png):
    width, height = 1080, 1920
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = find_font()
    title_font = ImageFont.truetype(font_path, 72) if font_path else ImageFont.load_default()
    body_font = ImageFont.truetype(font_path, 48) if font_path else ImageFont.load_default()
    small_font = ImageFont.truetype(font_path, 34) if font_path else ImageFont.load_default()

    title = str(record.get("Title", ""))[:90]
    body = str(record.get("Body") or record.get("Caption") or "")
    body = re.sub(r"\s+", " ", body).strip()[:600]
    tags = str(record.get("Tags", ""))[:140]

    y = 180
    draw.text((80, y), "AI TOOL SHORTS", fill="black", font=small_font)
    y += 120
    for line in wrap_text(draw, title, title_font, 920)[:4]:
        draw.text((80, y), line, fill="black", font=title_font)
        y += 90
    y += 60
    for line in wrap_text(draw, body, body_font, 920)[:11]:
        draw.text((80, y), line, fill="black", font=body_font)
        y += 66
    draw.text((80, 1680), tags, fill="black", font=small_font)
    draw.text((80, 1760), "Generated by AI Media Agent", fill="black", font=small_font)
    image.save(out_png)


def make_video(slide_png, out_mp4):
    cmd = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(slide_png),
        "-f",
        "lavfi",
        "-i",
        "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t",
        "12",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-vf",
        "scale=1080:1920",
        "-c:a",
        "aac",
        "-shortest",
        str(out_mp4),
    ]
    subprocess.run(cmd, check=True)


def main():
    service = sheets_service()
    values = get_values(service)
    if not values:
        raise RuntimeError(f"No rows found in sheet: {ASSETS_SHEET}")
    headers = ensure_headers(service, values)
    values = get_values(service)
    records = records_from_values(headers, values)
    targets = [record for record in records if selected(record)]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    made = 0
    for record in targets:
        base = slugify(record.get("AssetId") or record.get("Title"))
        slide_png = OUT_DIR / f"{base}.png"
        out_mp4 = OUT_DIR / f"{base}.mp4"
        try:
            make_slide(record, slide_png)
            make_video(slide_png, out_mp4)
            update_row(service, headers, record, {
                "PublishChannel": "YOUTUBE_SHORTS",
                "MediaFilePath": str(out_mp4),
                "MediaStatus": "READY",
                "ChannelStatus": "MEDIA_READY",
                "UploadError": "",
            })
            made += 1
        except Exception as exc:
            update_row(service, headers, record, {
                "PublishChannel": "YOUTUBE_SHORTS",
                "MediaStatus": "FAILED",
                "ChannelStatus": "FAILED",
                "UploadError": str(exc)[:500],
            })
    print(f"generated short videos: {made}")


if __name__ == "__main__":
    main()
