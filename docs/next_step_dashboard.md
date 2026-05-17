# Next Step: Approval Dashboard

This step creates a local HTML dashboard from the mock approval queue.

## 1. Pull latest repo

```powershell
cd C:\codetest\ai_media_agent
git pull
```

## 2. Prepare output folder

```powershell
mkdir n8n-files -Force
icacls .\n8n-files /grant "Everyone:(OI)(CI)F" /T
```

## 3. Recreate n8n container

```powershell
docker compose down
docker compose up -d --force-recreate
```

## 4. Import workflow

In n8n, import:

```text
C:\codetest\ai_media_agent\n8n\workflows\07_generate_approval_dashboard.json
```

## 5. Execute workflow

Open workflow:

```text
07 Generate Approval Dashboard
```

Click:

```text
Execute workflow
```

## 6. Check output

PowerShell:

```powershell
dir C:\codetest\ai_media_agent\n8n-files
ii C:\codetest\ai_media_agent\n8n-files\dashboard.html
```

Expected output file:

```text
C:\codetest\ai_media_agent\n8n-files\dashboard.html
```

## 7. Next after dashboard

If this works, the next milestone is Google Sheets approval queue:

1. Create Google Sheet.
2. Add columns from `docs/approval_queue_schema.md`.
3. Add n8n Google Sheets credential.
4. Replace HTML file output with Google Sheets append rows.
