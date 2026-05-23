# Naver Blog bridge setup

This bridge lets GitHub Actions send approved `NAVER_BLOG` rows to a local machine. The local machine keeps the Naver login session and later performs the browser-based publishing step.

## 1. Pull latest repo

```powershell
cd C:\codetest\ai_media_agent
git pull
```

If Git is not installed, install Git for Windows first.

## 2. Run local bridge server

```powershell
cd C:\codetest\ai_media_agent
python bridge\naver_blog_webhook_server.py
```

Default local endpoint:

```text
http://127.0.0.1:8787/webhook/naver-blog-publish
```

## 3. Expose local endpoint temporarily

Use a tunnel such as ngrok or Cloudflare Tunnel.

Example with ngrok:

```powershell
ngrok http 8787
```

Copy the HTTPS forwarding URL and append the webhook path:

```text
https://xxxx.ngrok-free.app/webhook/naver-blog-publish
```

## 4. Add GitHub Secrets

Repository → Settings → Secrets and variables → Actions → New repository secret

```text
NAVER_BLOG_WEBHOOK_URL=https://xxxx.ngrok-free.app/webhook/naver-blog-publish
NAVER_BLOG_ID=your-naver-blog-id
```

## 5. Approve Sheet row

In `publish_assets`:

```text
PublishChannel = NAVER_BLOG
PublishDecision = APPROVE
TargetUrl = blank
```

## 6. Run workflow

GitHub Actions:

```text
Send Naver Blog rows to bridge → Run workflow
```

If accepted, local files appear under:

```text
bridge_inbox/naver_blog/
```

The sheet row status becomes one of:

```text
SENT_TO_NAVER_BRIDGE
PUBLISHED
FAILED
NEED_CREDENTIAL
```

## 7. Next implementation

The next file to add is a local browser publisher that reads `bridge_inbox/naver_blog/*.json`, opens the Naver Blog editor with an existing browser session, fills title/body/tags, and returns the final URL.
