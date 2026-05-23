# Real publisher attachment plan

This project must publish to real audience channels, not GitHub Pages.

## Pipeline position

```text
generate_content_candidates
→ owner approval
→ generate_gemini_drafts
→ final owner approval
→ generate_publish_assets
→ route_publish_assets
→ publish_real_channels
→ sync_publish_log
→ performance_report
```

## Standard channels

| Channel | Purpose | First implementation |
|---|---|---|
| `NAVER_BLOG` | Korean blog distribution | local publisher bridge |
| `YOUTUBE_SHORTS` | short-form video | API publisher after mp4 creation |
| `INSTAGRAM_REELS` | short-form video | API publisher after mp4 creation |
| `TIKTOK` | short-form video | API publisher after mp4 creation |

## Publisher attachment model

A publisher is attached by adding one adapter with the same interface:

```python
class Publisher:
    def can_publish(asset) -> PublishCheck: ...
    def publish(asset) -> PublishResult: ...
```

Each adapter receives a row from `publish_assets` and returns:

```text
ChannelStatus
CredentialStatus
MediaStatus
TargetUrl
PlatformPostId
PublishedAt
UploadError
```

## NAVER Blog path

Naver Blog is the Korean blog target. Do not store a Naver password in GitHub Actions.

The first safe implementation is:

```text
GitHub Actions
→ approved NAVER_BLOG asset
→ create local-publish package
→ local PC publisher opens browser with existing Naver login session
→ publish post
→ write TargetUrl back to Sheet
```

## Video path

YouTube Shorts, Instagram Reels, and TikTok require a media file. The order is:

```text
Shorts asset
→ generate mp4
→ upload to YouTube Shorts
→ reuse same mp4 for Instagram Reels and TikTok
→ write TargetUrl / PlatformPostId back to Sheet
```

## Required status rules

| Condition | Status |
|---|---|
| no `PublishDecision=APPROVE` | `WAITING_APPROVAL` |
| Naver blog but no local publisher | `READY_FOR_LOCAL_PUBLISH` |
| video channel but no `MediaFilePath` | `NEED_MEDIA_FILE` |
| video channel missing API token | `NEED_CREDENTIAL` |
| ready to call platform API | `READY_TO_PUBLISH` |
| platform upload done | `PUBLISHED` |
| platform upload failed | `FAILED` |
