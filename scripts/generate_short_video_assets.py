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
    "ScriptApprovalStatus",
    "ShortsScriptJson",
    "ThumbnailMainText",
    "ThumbnailSubText",
    "ShortsTitle",
    "OnScreenTextOverlays",
    "VideoDurationSec",
    "VideoQualitySource",
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
    if norm(record.get("PublishDecision")) != "APPROVE":
        return False
    if not is_short_target(record):
        return False
    if str(record.get("TargetUrl", "")).strip():
        return False
    if str(record.get("MediaFilePath", "")).strip():
        return False
    # New quality gate: do not render videos from unapproved or failed scripts.
    if norm(record.get("ScriptApprovalStatus")) != "SCRIPT_APPROVED":
        return False
    return True


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


def text_width(draw, text, font):
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def wrap_text(draw, text, font, max_width):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    words = re.split(r"(\s+)", text)
    lines = []
    current = ""
    for word in words:
        trial = current + word
        if text_width(draw, trial, font) <= max_width:
            current = trial
        else:
            if current.strip():
                lines.append(current.strip())
            if text_width(draw, word, font) <= max_width:
                current = word.strip()
            else:
                buf = ""
                for ch in word:
                    trial_ch = buf + ch
                    if text_width(draw, trial_ch, font) <= max_width:
                        buf = trial_ch
                    else:
                        if buf:
                            lines.append(buf)
                        buf = ch
                current = buf
    if current.strip():
        lines.append(current.strip())
    return lines


def parse_seconds(value):
    raw = str(value or "").replace("–", "-").replace("~", "-")
    nums = [int(x) for x in re.findall(r"\d+", raw)]
    if len(nums) >= 2 and nums[1] > nums[0]:
        return max(2, min(20, nums[1] - nums[0]))
    return 8


def parse_script(record):
    raw = str(record.get("ShortsScriptJson", "")).strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list) and data:
                return [
                    {
                        "second": str(item.get("second", "")),
                        "line": str(item.get("line", "")),
                        "visual_note": str(item.get("visual_note", "")),
                    }
                    for item in data
                    if isinstance(item, dict) and str(item.get("line", "")).strip()
                ]
        except json.JSONDecodeError:
            pass
    fallback = []
    if record.get("Body"):
        fallback.append({"second": "0-4", "line": str(record.get("Title", ""))[:80], "visual_note": "제목 강조"})
        body = re.sub(r"\s+", " ", str(record.get("Body", ""))).strip()
        chunks = [body[i:i + 120] for i in range(0, min(len(body), 480), 120)]
        for i, chunk in enumerate(chunks, start=1):
            fallback.append({"second": f"{i*8}-{i*8+8}", "line": chunk, "visual_note": "핵심 내용"})
        fallback.append({"second": "50-60", "line": str(record.get("Caption") or "저장해두면 나중에 찾기 편합니다.")[:120], "visual_note": "CTA"})
    return fallback


def draw_centered(draw, lines, font, x_center, y, max_lines, line_gap=18):
    used = 0
    for line in lines[:max_lines]:
        bbox = draw.textbbox((0, 0), line, font=font)
        width = bbox[2] - bbox[0]
        draw.text((x_center - width / 2, y), line, fill="black", font=font)
        y += (bbox[3] - bbox[1]) + line_gap
        used += 1
    return y, used


def make_scene(record, scene, index, total, out_png):
    width, height = 1080, 1920
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    font_path = find_font()
    title_font = ImageFont.truetype(font_path, 74) if font_path else ImageFont.load_default()
    body_font = ImageFont.truetype(font_path, 66) if font_path else ImageFont.load_default()
    small_font = ImageFont.truetype(font_path, 34) if font_path else ImageFont.load_default()
    label_font = ImageFont.truetype(font_path, 44) if font_path else ImageFont.load_default()

    main = str(record.get("ThumbnailMainText") or record.get("ThumbnailText") or record.get("ShortsTitle") or record.get("Title") or "").strip()
    sub = str(record.get("ThumbnailSubText") or record.get("ChosenHookPattern") or "").strip()
    title = str(record.get("ShortsTitle") or record.get("Title") or "").strip()
    line = str(scene.get("line", "")).strip()
    note = str(scene.get("visual_note", "")).strip()
    second = str(scene.get("second", "")).strip()

    draw.text((70, 70), f"SCENE {index + 1}/{total}", fill="black", font=small_font)
    if second:
        draw.text((760, 70), second, fill="black", font=small_font)

    y = 210
    if index == 0 and main:
        y, _ = draw_centered(draw, wrap_text(draw, main, title_font, 900), title_font, width / 2, y, 3, 20)
        if sub:
            y += 30
            y, _ = draw_centered(draw, wrap_text(draw, sub, label_font, 900), label_font, width / 2, y, 2, 16)
        y += 100
    else:
        y, _ = draw_centered(draw, wrap_text(draw, title, label_font, 920), label_font, width / 2, y, 2, 16)
        y += 120

    y, _ = draw_centered(draw, wrap_text(draw, line, body_font, 900), body_font, width / 2, y, 7, 22)

    if note:
        bottom_lines = wrap_text(draw, note, small_font, 860)
        draw_centered(draw, bottom_lines, small_font, width / 2, 1540, 3, 12)

    overlays = str(record.get("OnScreenTextOverlays", "")).strip()
    if overlays:
        try:
            parsed = json.loads(overlays)
            overlay_text = " · ".join(str(x) for x in parsed[:3]) if isinstance(parsed, list) else overlays
        except json.JSONDecodeError:
            overlay_text = overlays
        draw_centered(draw, wrap_text(draw, overlay_text, small_font, 900), small_font, width / 2, 1740, 2, 12)

    image.save(out_png)


def render_scene_png_to_mp4(scene_png, duration, scene_mp4):
    subprocess.run([
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(scene_png),
        "-f", "lavfi",
        "-i", "anullsrc=channel_layout=stereo:sample_rate=44100",
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-vf", "scale=1080:1920",
        "-c:a", "aac",
        "-shortest",
        str(scene_mp4),
    ], check=True)


def concat_videos(scene_files, out_mp4):
    list_file = out_mp4.with_suffix(".concat.txt")
    list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in scene_files), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(list_file),
        "-c", "copy",
        str(out_mp4),
    ], check=True)


def make_video(record, out_mp4):
    scenes = parse_script(record)
    if not scenes:
        raise ValueError("ShortsScriptJson is empty or invalid")
    work_dir = out_mp4.parent / f".{out_mp4.stem}_scenes"
    work_dir.mkdir(parents=True, exist_ok=True)
    scene_files = []
    total_duration = 0
    for idx, scene in enumerate(scenes[:8]):
        duration = parse_seconds(scene.get("second"))
        total_duration += duration
        scene_png = work_dir / f"scene_{idx:02d}.png"
        scene_mp4 = work_dir / f"scene_{idx:02d}.mp4"
        make_scene(record, scene, idx, min(len(scenes), 8), scene_png)
        render_scene_png_to_mp4(scene_png, duration, scene_mp4)
        scene_files.append(scene_mp4)
    concat_videos(scene_files, out_mp4)
    return total_duration


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
    skipped = 0
    for record in records:
        if norm(record.get("PublishDecision")) == "APPROVE" and is_short_target(record) and not str(record.get("TargetUrl", "")).strip() and not selected(record):
            if not str(record.get("MediaFilePath", "")).strip():
                skipped += 1
                update_row(service, headers, record, {
                    "MediaStatus": "BLOCKED",
                    "ChannelStatus": "SCRIPT_REQUIRED",
                    "UploadError": "ScriptApprovalStatus must be SCRIPT_APPROVED before video rendering.",
                })
    for record in targets:
        base = slugify(record.get("AssetId") or record.get("Title"))
        out_mp4 = OUT_DIR / f"{base}.mp4"
        try:
            duration = make_video(record, out_mp4)
            update_row(service, headers, record, {
                "PublishChannel": "YOUTUBE_SHORTS",
                "MediaFilePath": str(out_mp4),
                "MediaStatus": "READY",
                "ChannelStatus": "MEDIA_READY",
                "VideoDurationSec": duration,
                "VideoQualitySource": "SCRIPT_APPROVED_SCENE_RENDER",
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
    print(f"generated short videos: {made}; blocked waiting for script approval: {skipped}")


if __name__ == "__main__":
    main()
