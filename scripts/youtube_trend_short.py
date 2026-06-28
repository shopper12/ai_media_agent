import argparse
import asyncio
import json
import os
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "out" / "youtube_trend_short"
YOUTUBE_UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
PUBLIC_UPLOAD_CONFIRMATION = "PUBLIC_UPLOAD"
AI_DISCLOSURE = (
    "AI-assisted original commentary. No original YouTube video, music, "
    "or thumbnail assets were reused."
)


@dataclass
class TrendVideo:
    video_id: str
    title: str
    channel_title: str
    description: str
    published_at: str
    category_id: str
    view_count: int
    like_count: int
    comment_count: int
    source_url: str


@dataclass
class ShortScript:
    title: str
    description: str
    tags: list[str]
    narration: list[str]
    on_screen: list[str]
    cta: str
    provider: str


def get_env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def request_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} from {url}: {body}") from exc


def parse_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def trend_from_item(item: dict[str, Any]) -> TrendVideo:
    snippet = item.get("snippet", {})
    statistics = item.get("statistics", {})
    video_id = item.get("id", "")
    return TrendVideo(
        video_id=video_id,
        title=snippet.get("title", ""),
        channel_title=snippet.get("channelTitle", ""),
        description=snippet.get("description", ""),
        published_at=snippet.get("publishedAt", ""),
        category_id=snippet.get("categoryId", ""),
        view_count=parse_int(statistics.get("viewCount")),
        like_count=parse_int(statistics.get("likeCount")),
        comment_count=parse_int(statistics.get("commentCount")),
        source_url=f"https://www.youtube.com/watch?v={video_id}",
    )


def load_trends_from_fixture(path: Path) -> list[TrendVideo]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data.get("items", data if isinstance(data, list) else [])
    return [trend_from_item(item) for item in items]


def mock_trends() -> list[TrendVideo]:
    return [
        TrendVideo(
            video_id="DRYRUN00001",
            title="A fast-moving AI app just became the internet's top demo",
            channel_title="Dry Run Trends",
            description="Fixture trend used when no YouTube API key is available.",
            published_at="2026-06-28T00:00:00Z",
            category_id="28",
            view_count=1_250_000,
            like_count=78_000,
            comment_count=4_200,
            source_url="https://www.youtube.com/watch?v=DRYRUN00001",
        )
    ]


def fetch_youtube_trends(
    api_key: str,
    region: str,
    video_category_id: str,
    max_results: int,
) -> list[TrendVideo]:
    query = {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular",
        "regionCode": region,
        "videoCategoryId": video_category_id,
        "maxResults": str(max_results),
        "key": api_key,
    }
    url = "https://www.googleapis.com/youtube/v3/videos?" + urllib.parse.urlencode(query)
    data = request_json(url)
    return [trend_from_item(item) for item in data.get("items", [])]


def select_trend(videos: list[TrendVideo]) -> TrendVideo:
    if not videos:
        raise RuntimeError("No trend videos were returned.")
    usable = [video for video in videos if video.video_id and video.title]
    if not usable:
        raise RuntimeError("Trend response did not include usable video IDs and titles.")
    return usable[0]


def load_prompt_template() -> str:
    prompt_path = REPO_ROOT / "prompts" / "youtube_trend_short.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "Create a rights-safe bilingual Korean/English YouTube Shorts script. "
        "Do not reuse the original video's audio, clips, thumbnail, or claims beyond "
        "public metadata. Return strict JSON."
    )


def strip_json_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    return stripped


def fallback_script(trend: TrendVideo) -> ShortScript:
    short_title = f"US trend watch: {trend.title[:64]}"
    description = "\n".join(
        [
            f"Today on the US YouTube popular chart: {trend.title}",
            "",
            "This Short explains why the topic is spreading and what to watch next.",
            AI_DISCLOSURE,
            f"Trend source: {trend.source_url}",
        ]
    )
    narration = [
        f"Today's US YouTube trend signal is: {trend.title}.",
        "The key is not only the view count. It is the conversation people can join quickly.",
        "This is a quick bilingual breakdown, not a reuse of the original video.",
        "We are looking at why it spread, what changed, and what to watch next.",
        "The original is linked as a source. This Short is new commentary.",
    ]
    on_screen = [
        "US TREND WATCH",
        trend.title,
        "Why it is spreading",
        "What to watch next",
        "Original commentary only",
    ]
    return ShortScript(
        title=short_title[:100],
        description=description[:4800],
        tags=["US trends", "YouTube Shorts", "AI commentary", "trend watch", "shorts"],
        narration=narration,
        on_screen=on_screen,
        cta="Follow for fast bilingual trend breakdowns.",
        provider="fallback",
    )


def normalize_script(raw: dict[str, Any], trend: TrendVideo, provider: str) -> ShortScript:
    fallback = fallback_script(trend)
    title = str(raw.get("title") or fallback.title).strip()[:100]
    description = str(raw.get("description") or fallback.description).strip()
    if AI_DISCLOSURE not in description:
        description = f"{description}\n\n{AI_DISCLOSURE}"
    if trend.source_url not in description:
        description = f"{description}\nTrend source: {trend.source_url}"

    tags = raw.get("tags") or fallback.tags
    tags = [str(tag).strip() for tag in tags if str(tag).strip()][:15]
    narration = raw.get("narration") or fallback.narration
    narration = [str(line).strip() for line in narration if str(line).strip()][:8]
    on_screen = raw.get("on_screen") or fallback.on_screen
    on_screen = [str(line).strip() for line in on_screen if str(line).strip()][:8]

    return ShortScript(
        title=title or fallback.title,
        description=description[:4800],
        tags=tags or fallback.tags,
        narration=narration or fallback.narration,
        on_screen=on_screen or fallback.on_screen,
        cta=str(raw.get("cta") or fallback.cta).strip(),
        provider=provider,
    )


def generate_script_with_gemini(trend: TrendVideo, api_key: str, model: str) -> ShortScript:
    template = load_prompt_template()
    trend_payload = json.dumps(asdict(trend), ensure_ascii=False, indent=2)
    prompt = f"{template}\n\nTREND_METADATA:\n{trend_payload}\n"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.6,
            "responseMimeType": "application/json",
        },
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
    )
    data = request_json(url, payload)
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(part.get("text", "") for part in parts)
    raw = json.loads(strip_json_fence(text))
    return normalize_script(raw, trend, provider=f"gemini:{model}")


def generate_script(trend: TrendVideo) -> ShortScript:
    api_key = get_env("GEMINI_API_KEY")
    if not api_key:
        return fallback_script(trend)
    model = get_env("GEMINI_MODEL", "gemini-1.5-flash")
    try:
        return generate_script_with_gemini(trend, api_key, model)
    except Exception as exc:
        print(f"Gemini generation failed, using fallback script: {exc}")
        return fallback_script(trend)


def find_font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "C:/Windows/Fonts/malgunbd.ttf" if bold else "",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def wrap_for_draw(text: str, width: int) -> str:
    chunks = []
    for paragraph in text.splitlines():
        chunks.extend(textwrap.wrap(paragraph, width=width) or [""])
    return "\n".join(chunks)


def make_slide_image(title: str, body: str, footer: str, size: tuple[int, int] = (1080, 1920)):
    from PIL import Image, ImageDraw

    image = Image.new("RGB", size, "#101820")
    draw = ImageDraw.Draw(image)
    width, height = size

    for y in range(height):
        blend = y / height
        red = int(16 + 25 * blend)
        green = int(24 + 38 * blend)
        blue = int(32 + 22 * blend)
        draw.line([(0, y), (width, y)], fill=(red, green, blue))

    accent = "#f7c948"
    draw.rounded_rectangle((64, 84, 1016, 164), radius=28, fill=accent)
    draw.text((96, 104), "US TREND SHORT", fill="#101820", font=find_font(34, bold=True))

    title_font = find_font(66, bold=True)
    body_font = find_font(46)
    footer_font = find_font(30)

    draw.text((72, 270), wrap_for_draw(title, 14), fill="#ffffff", font=title_font, spacing=16)
    draw.rounded_rectangle((64, 900, 1016, 1510), radius=36, fill="#ffffff")
    draw.text((108, 950), wrap_for_draw(body, 22), fill="#101820", font=body_font, spacing=14)
    draw.text((72, 1760), wrap_for_draw(footer, 42), fill="#d7dee8", font=footer_font, spacing=8)
    return image


def render_thumbnail(script: ShortScript, trend: TrendVideo, output_dir: Path) -> Path:
    from PIL import Image, ImageDraw

    output_path = output_dir / "thumbnail.jpg"
    image = Image.new("RGB", (1280, 720), "#101820")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1280, 128), fill="#f7c948")
    draw.text((48, 36), "US TREND WATCH", fill="#101820", font=find_font(54, bold=True))
    draw.text((56, 190), wrap_for_draw(script.title, 22), fill="#ffffff", font=find_font(64, bold=True), spacing=12)
    draw.text((56, 610), trend.channel_title, fill="#d7dee8", font=find_font(34))
    image.save(output_path, quality=92)
    return output_path


async def save_edge_tts(text: str, output_path: Path) -> None:
    import edge_tts

    voice = get_env("EDGE_TTS_VOICE", "ko-KR-SunHiNeural")
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(output_path))


def render_audio(script: ShortScript, output_dir: Path, dry_run: bool) -> Path | None:
    if dry_run and get_env("ENABLE_TTS_IN_DRY_RUN") != "1":
        return None
    text = " ".join(script.narration + [script.cta])
    audio_path = output_dir / "narration.mp3"
    try:
        asyncio.run(save_edge_tts(text, audio_path))
        return audio_path
    except Exception as exc:
        print(f"TTS generation skipped: {exc}")
        return None


def render_video(script: ShortScript, trend: TrendVideo, output_dir: Path, dry_run: bool) -> Path:
    import numpy as np
    from moviepy.editor import AudioFileClip, ImageClip, concatenate_videoclips

    output_path = output_dir / "youtube_trend_short.mp4"
    audio_path = render_audio(script, output_dir, dry_run)
    slide_texts = script.on_screen or [script.title]
    body_lines = script.narration or [script.description]
    slide_count = max(len(slide_texts), len(body_lines), 5)
    audio_duration = None
    audio_clip = None
    if audio_path and audio_path.exists():
        audio_clip = AudioFileClip(str(audio_path))
        audio_duration = min(max(audio_clip.duration + 1, 45), 60)
    total_duration = audio_duration or 48
    per_slide = total_duration / slide_count

    clips = []
    for index in range(slide_count):
        title = slide_texts[index % len(slide_texts)]
        body = body_lines[index % len(body_lines)]
        footer = f"Source trend: {trend.channel_title} | {AI_DISCLOSURE}"
        image = make_slide_image(title, body, footer)
        clips.append(ImageClip(np.array(image)).set_duration(per_slide))

    video = concatenate_videoclips(clips, method="compose").set_duration(total_duration)
    if audio_clip is not None:
        video = video.set_audio(audio_clip.subclip(0, min(audio_clip.duration, total_duration)))
    video.write_videofile(
        str(output_path),
        fps=30,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=2,
        logger=None,
    )
    if audio_clip is not None:
        audio_clip.close()
    video.close()
    for clip in clips:
        clip.close()
    return output_path


def assert_public_upload_confirmation(privacy_status: str, confirmation: str) -> None:
    if privacy_status == "public" and confirmation != PUBLIC_UPLOAD_CONFIRMATION:
        raise RuntimeError(
            "Public upload blocked. Pass --confirm-public-upload PUBLIC_UPLOAD "
            "or set CONFIRM_PUBLIC_UPLOAD=PUBLIC_UPLOAD."
        )


def build_upload_body(script: ShortScript, privacy_status: str) -> dict[str, Any]:
    return {
        "snippet": {
            "title": script.title,
            "description": script.description,
            "tags": script.tags,
            "categoryId": "22",
            "defaultLanguage": "ko",
            "defaultAudioLanguage": "ko",
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
    }


def require_upload_env() -> dict[str, str]:
    required = {
        "YOUTUBE_CLIENT_ID": get_env("YOUTUBE_CLIENT_ID"),
        "YOUTUBE_CLIENT_SECRET": get_env("YOUTUBE_CLIENT_SECRET"),
        "YOUTUBE_REFRESH_TOKEN": get_env("YOUTUBE_REFRESH_TOKEN"),
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError(f"Missing YouTube upload secrets: {', '.join(missing)}")
    return required


def upload_video(video_path: Path, script: ShortScript, privacy_status: str) -> dict[str, Any]:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    secrets = require_upload_env()
    credentials = Credentials(
        token=None,
        refresh_token=secrets["YOUTUBE_REFRESH_TOKEN"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=secrets["YOUTUBE_CLIENT_ID"],
        client_secret=secrets["YOUTUBE_CLIENT_SECRET"],
        scopes=[YOUTUBE_UPLOAD_SCOPE],
    )
    credentials.refresh(Request())
    service = build("youtube", "v3", credentials=credentials)
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True, mimetype="video/mp4")
    request = service.videos().insert(
        part="snippet,status",
        body=build_upload_body(script, privacy_status),
        media_body=media,
        notifySubscribers=False,
    )
    response = request.execute()
    response["url"] = f"https://www.youtube.com/watch?v={response.get('id')}"
    return response


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def build_metadata(
    trend: TrendVideo,
    script: ShortScript,
    args: argparse.Namespace,
    video_path: Path | None,
    thumbnail_path: Path | None,
    upload_response: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "trend": asdict(trend),
        "script": asdict(script),
        "policy": {
            "aiDisclosure": AI_DISCLOSURE,
            "containsSyntheticMedia": True,
            "reusedOriginalYouTubeMedia": False,
            "publicUploadConfirmationRequired": True,
        },
        "render": {
            "videoPath": str(video_path) if video_path else "",
            "thumbnailPath": str(thumbnail_path) if thumbnail_path else "",
            "targetResolution": "1080x1920",
            "targetDurationSeconds": "45-60",
        },
        "upload": upload_response or {"status": "skipped"},
        "settings": {
            "region": args.region,
            "videoCategoryId": args.video_category_id,
            "privacyStatus": args.privacy_status,
            "dryRun": args.dry_run,
            "skipUpload": args.skip_upload,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and optionally upload a rights-safe trend Shorts video.")
    parser.add_argument("--region", default=get_env("TREND_REGION", "US"))
    parser.add_argument("--video-category-id", default=get_env("TREND_VIDEO_CATEGORY_ID", "0"))
    parser.add_argument("--max-results", type=int, default=int(get_env("TREND_MAX_RESULTS", "5")))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--privacy-status", choices=["public", "unlisted", "private"], default=get_env("YOUTUBE_PRIVACY_STATUS", "public"))
    parser.add_argument("--confirm-public-upload", default=get_env("CONFIRM_PUBLIC_UPLOAD"))
    parser.add_argument("--trend-fixture", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-upload", action="store_true")
    parser.add_argument("--no-render", action="store_true")
    return parser.parse_args()


def get_trends(args: argparse.Namespace) -> list[TrendVideo]:
    if args.trend_fixture:
        return load_trends_from_fixture(args.trend_fixture)
    api_key = get_env("YOUTUBE_API_KEY")
    if api_key:
        return fetch_youtube_trends(api_key, args.region, args.video_category_id, args.max_results)
    if args.dry_run:
        return mock_trends()
    raise RuntimeError("Missing YOUTUBE_API_KEY. Use --dry-run for fixture-only execution.")


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    trends = get_trends(args)
    trend = select_trend(trends)
    script = generate_script(trend)

    video_path = None
    thumbnail_path = None
    if not args.no_render:
        thumbnail_path = render_thumbnail(script, trend, args.output_dir)
        video_path = render_video(script, trend, args.output_dir, args.dry_run)

    upload_response = None
    if args.skip_upload or args.dry_run:
        upload_response = {"status": "skipped", "reason": "dry run or skip upload requested"}
    else:
        assert_public_upload_confirmation(args.privacy_status, args.confirm_public_upload)
        if video_path is None or not video_path.exists():
            raise RuntimeError("Video file was not rendered; cannot upload.")
        upload_response = upload_video(video_path, script, args.privacy_status)
        write_json(args.output_dir / "upload_response.json", upload_response)

    metadata = build_metadata(trend, script, args, video_path, thumbnail_path, upload_response)
    write_json(args.output_dir / "metadata.json", metadata)
    print(json.dumps({"status": "ok", "outputDir": str(args.output_dir), "upload": upload_response}, ensure_ascii=False))


if __name__ == "__main__":
    main()
