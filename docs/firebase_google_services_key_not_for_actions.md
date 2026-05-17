# Firebase `google-services.json` is not the GitHub Actions service account key

The Android/Firebase `google-services.json` file is not the credential needed for the GitHub Actions Google Sheets automation.

## What it is

`google-services.json` is a Firebase/Android app configuration file. It often contains:

```text
project_info
mobilesdk_app_id
android package_name
api_key.current_key
configuration_version
```

This is not enough to authenticate GitHub Actions as a Google Sheets editor.

## What GitHub Actions needs

The GitHub Actions automation needs a Google Cloud service account private key JSON with these fields:

```text
type = service_account
private_key_id
private_key
client_email
token_uri
```

If the JSON does not contain `private_key` and `client_email`, it is not the right file for `GOOGLE_SERVICE_ACCOUNT_JSON`.

## Security note

If an API key from `google-services.json` was pasted into a chat, logs, or a public place, restrict or rotate the key in Google Cloud Console.

Recommended restrictions:

```text
Application restriction: Android apps
Package name: your Android package name
SHA-1 certificate fingerprint: your app signing/debug certificate
API restrictions: only the APIs the app actually needs
```

For this project, do not put Firebase Android API keys into GitHub Actions secrets for Google Sheets automation.

## Correct next step

Create a new service account key:

```text
Google Cloud Console
→ IAM & Admin
→ Service Accounts
→ select or create service account
→ Keys
→ Add key
→ Create new key
→ JSON
```

Then paste the entire downloaded service account JSON into GitHub Actions secret:

```text
GOOGLE_SERVICE_ACCOUNT_JSON
```

Also share the Google Sheet with the service account `client_email` as Editor.
