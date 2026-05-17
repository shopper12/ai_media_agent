# Gemini API key as n8n Credential

This project uses a stored n8n credential instead of putting the Gemini API key in `.env`.

## 1. Create Gemini API key

Open Google AI Studio and create an API key.

## 2. Create n8n credential

In recent n8n versions, the credential display name is usually:

```text
Header Auth
```

not `HTTP Header Auth`.

In n8n:

```text
Credentials
→ Create credential
→ search: Header Auth
```

If it does not appear from the global Credentials menu, create it inside the HTTP Request node:

```text
HTTP Request node
→ Authentication: Generic Credential Type
→ Generic Auth Type: Header Auth
→ Create new credential
```

Set:

```text
Credential name: Gemini API Key Header
Name: x-goog-api-key
Value: your Gemini API key
```

Save.

## 3. Import workflow

Import:

```text
C:\codetest\ai_media_agent\n8n\workflows\09_gemini_draft_with_credential.json
```

## 4. Attach credential if n8n asks

Open the HTTP Request node:

```text
Gemini Generate Content
```

Credential:

```text
Gemini API Key Header
```

## 5. Execute

Run the workflow.

Expected output from final node:

```text
DraftHook
DraftBody
DraftCTA
RiskReviewStatus
GeneratedAt
FinalStatus
```

## Notes

The workflow calls:

```text
https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent
```

with HTTP header:

```text
x-goog-api-key: <stored in n8n credential>
```

Do not paste API keys into workflow Code nodes or GitHub files.
