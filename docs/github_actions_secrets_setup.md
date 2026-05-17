# GitHub Actions Secrets and Variables Setup

This project can run the Gemini + Google Sheets automation through GitHub Actions.

## Repository path

```text
shopper12/ai_media_agent
```

Go to:

```text
GitHub repository
→ Settings
→ Secrets and variables
→ Actions
```

---

## Required Repository secrets

Create these under:

```text
Secrets
→ Repository secrets
→ New repository secret
```

### 1. GEMINI_API_KEY

Value:

```text
Google AI Studio Gemini API key
```

Example format:

```text
AIza...
```

Do not include quotes.

---

### 2. GOOGLE_SERVICE_ACCOUNT_JSON

Value:

```text
Full Google service account JSON key content
```

Paste the whole JSON, including braces:

```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "...@....iam.gserviceaccount.com",
  "client_id": "...",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "..."
}
```

Important:

```text
Share the Google Sheet with the service account client_email as Editor.
```

---

### 3. SPREADSHEET_ID

Value:

```text
1dMYlR9HA4dCCb9uGU8iFinhPsr7h-jKyfXf3BHh004w
```

This is the current `AI Media Approval Queue` spreadsheet ID.

---

## Optional Repository variables

Create these under:

```text
Variables
→ Repository variables
→ New repository variable
```

### 1. SHEET_NAME

Value:

```text
sheet1
```

If omitted, the workflow uses `sheet1`.

---

### 2. GEMINI_MODEL

Value:

```text
gemini-2.5-flash
```

If omitted, the workflow uses `gemini-2.5-flash`.

---

## Existing GitHub Actions workflow

The workflow file is:

```text
.github/workflows/gemini_sheets.yml
```

It uses:

```yaml
GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
SPREADSHEET_ID: ${{ secrets.SPREADSHEET_ID }}
SHEET_NAME: ${{ vars.SHEET_NAME || 'sheet1' }}
GEMINI_MODEL: ${{ vars.GEMINI_MODEL || 'gemini-2.5-flash' }}
```

---

## Run manually

Go to:

```text
Actions
→ Generate Gemini drafts from approved sheet rows
→ Run workflow
```

---

## Expected behavior

The Action reads rows from Google Sheets where:

```text
OwnerDecision = APPROVE
```

Then it calls Gemini and updates the same row with:

```text
DraftHook
DraftBody
DraftCTA
RiskReviewStatus
GeneratedAt
FinalStatus
```

---

## Do not store these as plain repo files

Do not commit:

```text
.env
service-account.json
Google API key files
any raw API key
```

Use GitHub Actions Secrets for Actions and n8n Credentials for n8n.
