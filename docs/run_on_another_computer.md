# Run this project on another computer

This project separates portable files from local secrets.

## Portable through GitHub

These are synced through GitHub:

```text
docker-compose.yml
.env.example
n8n/workflows/*.json
docs/*.md
```

## Not portable through GitHub

These must be recreated on each computer:

```text
.env
n8n credentials
Google account login
Google Gemini(PaLM) Api credential
Google Sheets credential
Docker volume n8n_data
```

Do not commit secrets.

---

## Recommended clean setup on a new computer

### 1. Install prerequisites

```text
Git
Docker Desktop
```

Docker must be running.

Check:

```powershell
docker run --rm hello-world
```

### 2. Clone repo

```powershell
cd C:\codetest
git clone https://github.com/shopper12/ai_media_agent.git
cd C:\codetest\ai_media_agent
```

If repo already exists:

```powershell
cd C:\codetest\ai_media_agent
git pull
```

### 3. Create local env file

```powershell
copy .env.example .env
notepad .env
```

Fill only what is needed locally. Do not commit `.env`.

### 4. Start n8n

```powershell
docker compose up -d --force-recreate
```

Open:

```text
http://localhost:5678
```

### 5. Recreate n8n credentials

Create these credentials manually in n8n:

```text
Google Sheets account
Google Gemini(PaLM) Api account
```

Gemini credential:

```text
Credentials → Google Gemini(PaLM) Api → API Key
```

Google Sheets credential:

```text
Credentials → Google Sheets OAuth2 API
```

or the working Google Sheets credential type used on the original machine.

### 6. Import workflow

Import the current end-to-end workflow:

```text
C:\codetest\ai_media_agent\n8n\workflows\10_approved_sheet_to_gemini_to_sheet.json
```

Then open these nodes and select local credentials:

```text
Read Approved Rows → Google Sheets account
Gemini Message Model → Google Gemini(PaLM) Api account
Update Draft To Sheet → Google Sheets account
```

### 7. Execute

Run:

```text
10 Approved Sheet To Gemini To Sheet
```

Expected result:

```text
OwnerDecision = APPROVE rows are read from Google Sheets.
Gemini generates draft fields.
The same Google Sheet row is updated.
```

---

## Full migration option

If you want another computer to have the same n8n internal workflows and credentials without recreating them, migrate the Docker volume. This requires a fixed `N8N_ENCRYPTION_KEY`; otherwise credentials may not decrypt correctly on another machine.

This is not the recommended path for now. The recommended path is:

```text
GitHub for workflow files
Recreate credentials per computer
```
