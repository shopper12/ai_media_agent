# AI Media Agent

Goal: let the owner approve, hold, or reject content while the AI media agent handles topic selection, content drafting, review artifacts, and reporting.

The base n8n flows still support **mock mode** so the workflow structure can be checked before connecting external APIs.

---

## 0. Prerequisite

Docker `hello-world` should run successfully.

```powershell
docker run --rm hello-world
```

---

## 1. Clone

```powershell
cd C:\codetest
git clone https://github.com/shopper12/ai_media_agent.git
cd C:\codetest\ai_media_agent
```

If the folder already exists:

```powershell
cd C:\codetest\ai_media_agent
git pull
```

---

## 2. Run n8n

```powershell
cd C:\codetest\ai_media_agent
copy .env.example .env
docker compose up -d
docker ps
```

Open:

```text
http://localhost:5678
```

---

## 3. Import n8n workflows

Import the workflow JSON files from the n8n UI.

```text
docs/n8n_import.md
```

Current workflows:

```text
n8n/workflows/01_mock_ai_tools_topic_scoring.json
n8n/workflows/02_mock_content_approval_queue.json
n8n/workflows/03_mock_weekly_report.json
```

---

## 4. Approval Queue

Template:

```text
data/approval_queue_template.csv
```

Allowed `OwnerDecision` values:

```text
APPROVE
HOLD
REJECT
```

---

## 5. US Trend YouTube Shorts Automation

The manual GitHub Actions workflow creates one vertical Short from the current US YouTube popular chart.

```text
.github/workflows/youtube-trend-short.yml
```

Default behavior:

- Reads YouTube Data API `videos.list` with `chart=mostPopular`, `regionCode=US`, and `videoCategoryId=0`.
- Does not download or reuse the original YouTube video, audio, transcript, or thumbnail.
- Uses Gemini for a Korean/English commentary script when available; otherwise uses a safe fallback script.
- Uses `edge-tts`, Pillow, MoviePy, and FFmpeg to render a 1080x1920 MP4 plus thumbnail artifact.
- Allows public upload only when `confirm_public_upload` is exactly `PUBLIC_UPLOAD`.

Required GitHub repository secrets:

```text
YOUTUBE_API_KEY
YOUTUBE_CLIENT_ID
YOUTUBE_CLIENT_SECRET
YOUTUBE_REFRESH_TOKEN
GEMINI_API_KEY
```

Optional repository variable:

```text
GEMINI_MODEL=gemini-1.5-flash
```

Local dry run:

```powershell
python -m pip install -r requirements.txt
python scripts/youtube_trend_short.py --dry-run --skip-upload
```

Public upload flow:

1. Run the `YouTube Trend Short` workflow manually in GitHub Actions.
2. Set `dry_run=false`.
3. Keep `privacy_status=public`.
4. Enter `confirm_public_upload=PUBLIC_UPLOAD`.

Important:

- YouTube may restrict uploads from unverified API projects created after 2020-07-28 to private visibility. If that happens, the workflow should fail instead of silently bypassing the public-upload requirement.
- The upload metadata sets `containsSyntheticMedia=true`, `selfDeclaredMadeForKids=false`, and adds an AI-assisted original-commentary disclosure.

---

## 6. Logs

```powershell
cd C:\codetest\ai_media_agent
docker compose ps
docker compose logs n8n --tail=150
```

---

## 7. Stop

```powershell
cd C:\codetest\ai_media_agent
docker compose down
```

---

## 8. Current Scope

Current capabilities:

- AI tools and SaaS topic mock scoring
- Content approval queue mock generation
- Weekly report mock generation
- Approval queue template
- US trend YouTube Shorts generation/upload workflow

Next useful upgrades:

- Connect the Google Sheets approval queue to the Shorts workflow
- Add Telegram approval notifications
- Add affiliate-link data
