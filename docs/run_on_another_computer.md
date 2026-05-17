# Run this project on another computer

This repository is a private personal repo, but keep a hard separation between portable source files and secrets.

## Source of truth in GitHub

These should be managed through GitHub:

```text
docker-compose.yml
.env.example
n8n/workflows/*.json
docs/*.md
```

## Secrets and local state

These should not be committed as plain text, even in a private repo:

```text
.env
Google service account JSON
Gemini API key
OpenAI API key
n8n credentials
n8n_data Docker volume
```

Reason: private repos can still leak through account compromise, accidental sharing, cloned PCs, token exposure, or later public conversion.

---

## Recommended setup for another computer

### 1. Clone or update repo

```powershell
cd C:\codetest
git clone https://github.com/shopper12/ai_media_agent.git
cd C:\codetest\ai_media_agent
```

If it already exists:

```powershell
cd C:\codetest\ai_media_agent
git pull
```

### 2. Create local env file

```powershell
copy .env.example .env
notepad .env
```

Do not commit `.env`.

### 3. Start n8n

```powershell
docker compose up -d --force-recreate
```

Open:

```text
http://localhost:5678
```

### 4. Recreate credentials on that computer

Create these in n8n:

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

### 5. Import workflow

Import:

```text
C:\codetest\ai_media_agent\n8n\workflows\10_approved_sheet_to_gemini_to_sheet.json
```

Then open these nodes and select credentials:

```text
Read Approved Rows → Google Sheets account
Gemini Message Model → Google Gemini(PaLM) Api account
Update Draft To Sheet → Google Sheets account
```

---

## If you want fewer manual steps

There are two safer options than committing plaintext secrets.

### Option A: Fixed n8n encryption key + volume migration

Use the same `N8N_ENCRYPTION_KEY` on every computer and migrate the n8n database/volume.

This can preserve credentials, but it is more fragile.

### Option B: Encrypted secret files in repo

Store secrets only in encrypted form, for example:

```text
secrets.enc.json
```

Decrypt locally after cloning. Do not commit decrypted files.

---

## Current recommendation

For now:

```text
GitHub stores workflows and project files.
Each computer recreates n8n credentials once.
```

When the workflow stabilizes, move to one of these:

```text
fixed N8N_ENCRYPTION_KEY + volume backup
or encrypted secrets file
```
