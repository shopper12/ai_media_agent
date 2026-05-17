# ChatGPT API vs OpenAI API

There is no separate ChatGPT subscription API that can be used from n8n as a replacement for OpenAI API billing.

## Key point

ChatGPT subscription and OpenAI API Platform are billed separately.

- ChatGPT Plus/Pro gives access to ChatGPT web/app features.
- OpenAI API requires Platform billing and API credits.
- n8n OpenAI nodes call the OpenAI API, not the ChatGPT web subscription.

## What this means for this project

If OpenAI API returns:

```text
429 insufficient_quota
```

then the API billing/quota must be fixed in OpenAI Platform.

Until then, continue with mock generation:

```text
Google Sheets approved rows
→ Code node mock draft generation
→ Google Sheets draft columns
```

After API billing is fixed:

```text
Google Sheets approved rows
→ OpenAI node
→ Google Sheets draft columns
```
