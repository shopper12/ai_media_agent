# `google-services.json` is not the required file

For GitHub Actions, do not use Android/Firebase `google-services.json`.

## Wrong file

```text
google-services.json
```

This is usually an Android/Firebase app configuration file. It is not a Google service account private key and cannot be used as `GOOGLE_SERVICE_ACCOUNT_JSON` for the GitHub Actions workflow.

## Required file

You need a Google Cloud service account key JSON. It contains fields like:

```json
{
  "type": "service_account",
  "project_id": "...",
  "private_key_id": "...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "...@....iam.gserviceaccount.com",
  "client_id": "...",
  "token_uri": "https://oauth2.googleapis.com/token"
}
```

The important markers are:

```text
"type": "service_account"
"private_key"
"client_email"
```

## How to create it

Google Cloud Console:

```text
IAM & Admin
→ Service Accounts
→ Create Service Account
→ Keys
→ Add key
→ Create new key
→ JSON
```

Download the JSON file.

## Google Sheets sharing

Open the downloaded JSON and copy:

```text
client_email
```

Then open the Google Sheet:

```text
AI Media Approval Queue
→ Share
→ paste client_email
→ Editor
```

## GitHub Actions secret

GitHub repository:

```text
Settings
→ Secrets and variables
→ Actions
→ Secrets
→ New repository secret
```

Secret name:

```text
GOOGLE_SERVICE_ACCOUNT_JSON
```

Secret value:

```text
paste the entire service account JSON file content
```

Do not paste only the file path. Do not use `google-services.json`.
