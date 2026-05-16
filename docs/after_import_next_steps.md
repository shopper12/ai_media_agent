# After Import Next Steps

## 1. Execute workflow

Open the imported workflow in n8n and click:

```text
Execute workflow
```

Expected output has three sections:

```text
topic_scoring
approval_queue
weekly_report
```

## 2. If execution succeeds

This confirms that n8n, Docker, and the mock workflow are working.

Next target:

```text
Connect Google Sheets or local CSV approval queue.
```

## 3. If execution fails

Run this in PowerShell:

```powershell
cd C:\codetest\ai_media_agent
docker compose logs n8n --tail=150
```

Send the log output back for debugging.

## 4. Next implementation milestone

Build a real approval queue workflow:

1. Generate topic candidates.
2. Generate draft content.
3. Write rows into approval queue.
4. Owner marks APPROVE / HOLD / REJECT.
5. Approved rows move to publish queue.
