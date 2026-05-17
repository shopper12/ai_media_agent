# Google Sheets credential setup for n8n self-hosted

If n8n Google login fails with:

```text
Client missing a project id
401 invalid_client
```

it means the Google credential is not correctly configured for a self-hosted n8n instance. Create a Google Cloud project and credential first.

## Recommended for local automation: Service Account

This avoids the browser OAuth login flow.

### 1. Google Cloud

1. Open Google Cloud Console.
2. Create a project, for example `ai-media-agent`.
3. Enable `Google Sheets API`.
4. Enable `Google Drive API` if n8n needs to find spreadsheets by name.
5. Create a Service Account.
6. Create a JSON key for that Service Account.
7. Download the JSON key.

### 2. Google Sheet

1. Open the approval queue Google Sheet.
2. Click Share.
3. Share it with the service account email from the JSON file.
4. Give Editor permission.

### 3. n8n

1. Google Sheets node.
2. Credential: Google Service Account.
3. Paste or upload the service account JSON.
4. Select the spreadsheet by ID or URL.
5. Operation: append row.

## OAuth alternative

Use this only if you need to write as your personal Google account.

### 1. Google Cloud

1. Create a Google Cloud project.
2. Enable `Google Sheets API`.
3. Configure OAuth consent screen.
4. Add your Gmail address as a test user if the app is in testing mode.
5. Create OAuth Client ID.
6. Application type: Web application.

### 2. Redirect URI

In n8n credential screen, copy the OAuth callback URL shown by n8n.

Typical local callback URL:

```text
http://localhost:5678/rest/oauth2-credential/callback
```

Add it to Google Cloud OAuth Client as an Authorized redirect URI.

### 3. n8n

1. Paste Client ID.
2. Paste Client Secret.
3. Save.
4. Connect Google account.

## Do not commit secrets

Never commit these files or values:

- service account JSON key
- OAuth client secret
- refresh token
- `.env`

Use `.env` or n8n credentials only.
