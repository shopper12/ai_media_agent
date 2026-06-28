import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "youtube_trend_short.py"
SPEC = importlib.util.spec_from_file_location("youtube_trend_short", SCRIPT_PATH)
youtube_trend_short = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(youtube_trend_short)


def test_select_trend_uses_first_usable_video():
    videos = [
        youtube_trend_short.TrendVideo(
            video_id="abc123",
            title="Trend title",
            channel_title="Creator",
            description="",
            published_at="2026-06-28T00:00:00Z",
            category_id="24",
            view_count=100,
            like_count=10,
            comment_count=1,
            source_url="https://www.youtube.com/watch?v=abc123",
        )
    ]

    selected = youtube_trend_short.select_trend(videos)

    assert selected.video_id == "abc123"
    assert selected.source_url.endswith("abc123")


def test_fallback_script_includes_disclosure_and_source():
    trend = youtube_trend_short.mock_trends()[0]

    script = youtube_trend_short.fallback_script(trend)

    assert youtube_trend_short.AI_DISCLOSURE in script.description
    assert trend.source_url in script.description
    assert script.provider == "fallback"
    assert script.narration


def test_public_upload_requires_explicit_confirmation():
    try:
        youtube_trend_short.assert_public_upload_confirmation("public", "")
    except RuntimeError as exc:
        assert "Public upload blocked" in str(exc)
    else:
        raise AssertionError("public upload should require explicit confirmation")


def test_upload_body_marks_synthetic_and_not_made_for_kids():
    script = youtube_trend_short.fallback_script(youtube_trend_short.mock_trends()[0])

    body = youtube_trend_short.build_upload_body(script, "public")

    assert body["status"]["privacyStatus"] == "public"
    assert body["status"]["containsSyntheticMedia"] is True
    assert body["status"]["selfDeclaredMadeForKids"] is False
    assert youtube_trend_short.AI_DISCLOSURE in body["snippet"]["description"]
