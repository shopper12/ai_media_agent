"""Generate YouTube Shorts videos with TTS narration.

Upgrade from plain text-on-white-background:
- ElevenLabs TTS narration per scene (Korean voice)
- Gradient/color background instead of white
- Auto-resize text to fit frame
- Falls back gracefully if ElevenLabs key not set (silent video)

Requires: ffmpeg, Pillow, requests
Optional: ELEVENLABS_API_KEY env var for TTS
"""
import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from google.oauth2 import service_account
from googleapiclient.discovery import build
from PIL import Image, ImageDraw, ImageFont

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
ASSETS_SHEET = os.environ.get("PUBLISH_ASSETS_SHEET_NAME", "publish_assets")
OUT_DIR = Path(os.environ.get("SHORT_VIDEO_OUT_DIR", "generated/short_videos"))
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# ElevenLabs Korean voice (Rachel → swap to Korean voice ID if available)
# Use voice ID for 'Bella' or any Korean-compatible voice
ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_MODEL = "eleven_multilingual_v2"

# Color themes per scene index for visual variety
SCENE_THEMES = [
    {"bg": (15, 20, 40), "text": (255, 255, 255), "accent": (255, 200, 0)},    # dark navy + gold
    {"bg": (30, 30, 30), "text": (255, 255, 255), "accent": (100, 220, 255)},   # charcoal + cyan
    {"bg": (20, 60, 20), "text": (255, 255, 255), "accent": (150, 255, 100)},   # dark green
    {"bg": (60, 10, 10), "text": (255, 255, 255), "accent": (255, 120, 80)},    # dark red
    {"bg": (40, 20, 60), "text": (255, 255, 255), "accent": (200, 150, 255)},   # dark purple
    {"bg": (10, 40, 60), "text": (255, 255, 255), "accent": (80, 200, 255)},    # dark teal
    {"bg": (50, 30, 0), "text": (255, 255, 255), "accent": (255, 180, 0)},      # dark amber
    {"bg": (15, 20, 40), "text": (255, 255, 255), "accent": (255, 200, 0)},     # repeat dark navy
]

REQUIRED_COLUMNS = [
    "PublishDecision", "PublishChannel", "ChannelStatus", "CredentialStatus",
    "MediaStatus", "MediaFilePath", "TargetUrl", "PlatformPostId",
    "PublishedAt", "UploadError", "ScriptApprovalStatus", "ShortsScriptJson",
    "ThumbnailMainText", "ThumbnailSubText", "ShortsTitle",
    "OnScreenTextOverlays", "VideoDurationSec", "VideoQualitySource",
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
    for col in REQUIRED_COLUMNS:
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


def records_from_values(headers, values):
    records = []
    for row_num, row in enumerate(values[1:], start=2):
        rec = {headers[i]: (row[i] if i < len(row) else "") for i in range(len(headers))}
        rec["_row_number"] = row_num
        records.append(rec)
    return records


def update_row(service, headers, record, updates):
    row = [record.get(h, "") for h in headers]
    for key, val in updates.items():
        if key in headers:
            row[headers.index(key)] = val
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{ASSETS_SHEET}!A{record['_row_number']}",
        valueInputOption="USER_ENTERED",
        body={"values": [row]},
    ).execute()


def norm(v) -> str:
    return str(v or "").strip().upper()


def is_shorts_target(rec):
    ch = norm(rec.get("PublishChannel"))
    at = norm(rec.get("AssetType"))
    return ch in {"YOUTUBE_SHORTS", "SHORTS", "YOUTUBE", "YOUTUBE SHORTS"} or at in {"SHORTS", "YOUTUBE SHORTS"}


def is_selected(rec):
    if norm(rec.get("PublishDecision")) != "APPROVE":
        return False
    if not is_shorts_target(rec):
        return False
    if str(rec.get("TargetUrl", "")).strip():
        return False
    if str(rec.get("MediaFilePath", "")).strip():
        return False
    if norm(rec.get("ScriptApprovalStatus")) != "SCRIPT_APPROVED":
        return False
    return True


def slugify(v):
    slug = re.sub(r"[^0-9a-zA-Z가-힣_-]+", "-", str(v or "short")).strip("-").lower()
    return slug or "short"


def find_font(size: int = 72):
    candidates = [
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    lines, current = [], ""
    for char in text:
        trial = current + char
        bbox = draw.textbbox((0, 0), trial, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def draw_gradient_bg(image: Image.Image, theme: dict):
    """Draw a vertical gradient background."""
    draw = ImageDraw.Draw(image)
    w, h = image.size
    bg = theme["bg"]
    # Slightly lighter at top, darker at bottom
    for y in range(h):
        ratio = y / h
        r = int(bg[0] * (1 - ratio * 0.3))
        g = int(bg[1] * (1 - ratio * 0.3))
        b = int(bg[2] * (1 - ratio * 0.3))
        draw.line([(0, y), (w, y)], fill=(max(0, r), max(0, g), max(0, b)))


def draw_scene_card(record: dict, scene: dict, index: int, total: int, out_png: Path):
    """Render a single scene card: gradient bg + centered text + accent bar."""
    W, H = 1080, 1920
    theme = SCENE_THEMES[index % len(SCENE_THEMES)]
    img = Image.new("RGB", (W, H))
    draw_gradient_bg(img, theme)
    draw = ImageDraw.Draw(img)

    accent = theme["accent"]
    text_color = theme["text"]
    padding = 80

    # Top accent bar
    draw.rectangle([(0, 0), (W, 12)], fill=accent)
    # Bottom accent bar
    draw.rectangle([(0, H - 12), (W, H)], fill=accent)

    # Scene counter dots
    dot_r = 