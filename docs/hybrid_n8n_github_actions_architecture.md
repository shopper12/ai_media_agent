# Hybrid architecture: n8n + GitHub Actions

The final goal is automation, not manual workflow editing.

## Correct division of labor

```text
n8n = visual automation/orchestration layer
GitHub = source of truth for workflow JSON, scripts, docs
GitHub Actions = headless scheduled runner / backup automation
GitHub Secrets = secrets for GitHub Actions only
n8n Credentials = secrets for n8n runtime
Google Sheets = approval queue and owner control surface
```

## Why keep n8n

Use n8n when the workflow needs:

```text
manual upload/input steps
visual debugging
Google Sheets/Drive integrations
owner approval routing
low-code adjustments
future Telegram/YouTube/SNS publishing branches
```

## Why keep GitHub Actions

Use GitHub Actions when the workflow needs:

```text
scheduled execution without keeping a local PC open
portable automation from any computer
secret injection through GitHub Actions secrets
CI-style validation and fallback runs
```

## Important limitation

GitHub Actions secrets are not automatically available inside a local n8n container.

This does not work automatically:

```text
GitHub Secrets → local Docker n8n credentials
```

GitHub Secrets only exist while GitHub Actions jobs run.

## Current recommended setup

For now, keep both:

```text
1. n8n workflow for visual upload/approval/draft generation
2. GitHub Actions workflow as serverless/scheduled fallback
3. Google Sheets as the shared state layer
```

## Practical operating model

### Daily/manual use

```text
Open n8n
Run/import workflow 10_approved_sheet_to_gemini_to_sheet.json
Check Google Sheet output
```

### Scheduled/headless use

```text
GitHub Actions
→ secrets.GEMINI_API_KEY
→ secrets.GOOGLE_SERVICE_ACCOUNT_JSON
→ secrets.SPREADSHEET_ID
→ scripts/github_actions_gemini_sheets.py
→ Google Sheet update
```

## If the goal is zero setup on other computers

Run n8n on one always-on server, for example EC2.

```text
EC2/Docker n8n = single permanent n8n instance
GitHub = workflow source and deployment source
Any computer = browser access only
```

Then the user does not recreate credentials per computer.

## Next target architecture

```text
User uploads / edits queue in Google Sheet or n8n
→ n8n handles visual/manual flows
→ GitHub Actions handles scheduled fallback generation
→ both write to the same Google Sheet
→ user only reviews APPROVE/HOLD/REJECT and final outputs
```

## Do not do this

Do not commit plaintext API keys into workflow JSON or `.env`.

Use:

```text
n8n Credentials for n8n
GitHub Actions Secrets for Actions
```
