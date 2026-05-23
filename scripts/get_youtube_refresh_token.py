import json
import os
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
CLIENT_FILE = Path(os.environ.get("YOUTUBE_OAUTH_CLIENT_FILE", "youtube_oauth_client.json"))
CLIENT_JSON_ENV = os.environ.get("YOUTUBE_OAUTH_CLIENT_JSON", "").strip()


def ensure_client_file() -> Path:
    if CLIENT_JSON_ENV:
        try:
            data = json.loads(CLIENT_JSON_ENV)
        except json.JSONDecodeError as exc:
            raise SystemExit(f"YOUTUBE_OAUTH_CLIENT_JSON is not valid JSON: {exc}")
        CLIENT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return CLIENT_FILE

    if CLIENT_FILE.exists():
        return CLIENT_FILE

    raise SystemExit(
        "Missing OAuth client JSON. Save the downloaded Google OAuth desktop client JSON as "
        f"{CLIENT_FILE} or set YOUTUBE_OAUTH_CLIENT_JSON."
    )


def main():
    client_file = ensure_client_file()
    flow = InstalledAppFlow.from_client_secrets_file(str(client_file), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print("\n=== COPY THESE VALUES TO GITHUB SECRETS ===")
    print("Secret name: YOUTUBE_OAUTH_CLIENT_JSON")
    print("Secret value:")
    print(client_file.read_text(encoding="utf-8"))
    print("\nSecret name: YOUTUBE_OAUTH_REFRESH_TOKEN")
    print("Secret value:")
    print(creds.refresh_token)
    print("\nDone.")


if __name__ == "__main__":
    main()
