# Where to put OpenAI API key

Do not paste the OpenAI API key into workflow code.

There are two places:

## Option A: n8n Credential

Use this when using n8n's OpenAI node or AI Agent node.

Steps:

1. Open n8n.
2. Go to Credentials.
3. Create credential.
4. Search OpenAI.
5. Paste API key.
6. Save.
7. In the OpenAI node, select that credential.

This is the recommended method for n8n nodes.

## Option B: `.env`

Use this when using HTTP Request node or Code node to call OpenAI manually.

Local file:

```text
C:\codetest\ai_media_agent\.env
```

Add:

```env
OPENAI_API_KEY=sk-...
```

Then recreate Docker:

```powershell
cd C:\codetest\ai_media_agent
docker compose down
docker compose up -d --force-recreate
```

Check inside container:

```powershell
docker exec ai_media_agent_n8n sh -lc "test -n \"$OPENAI_API_KEY\" && echo OPENAI_API_KEY_SET || echo OPENAI_API_KEY_MISSING"
```

## Where it fits in the workflow

Do not put the key into 08.

08 only prepares approved row data and a draft prompt.

Add AI generation after 08:

```text
08 Read Approved Rows
→ Build Content Draft Input
→ OpenAI Chat Model or OpenAI node
→ Risk Review
→ Google Sheets update row
```

The OpenAI node uses the OpenAI credential.
