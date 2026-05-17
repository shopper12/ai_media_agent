# n8n WriteBinaryFile not writable fix

If the WriteBinaryFile node says the target file is not writable even after `N8N_RESTRICT_FILE_ACCESS_TO` is set, create the target file first and grant write permission inside the container.

PowerShell:

```powershell
cd C:\codetest\ai_media_agent

docker exec ai_media_agent_n8n sh -lc "mkdir -p /files/data && touch /files/data/approval_queue.json && chmod 666 /files/data/approval_queue.json && ls -la /files/data/approval_queue.json"
```

Then execute `04 Local File Approval Queue Mock` again.

If using the internal volume workflow:

```powershell
docker exec ai_media_agent_n8n sh -lc "touch /home/node/.n8n/approval_queue.json && chmod 666 /home/node/.n8n/approval_queue.json && ls -la /home/node/.n8n/approval_queue.json"
```

Then execute `05 Internal Approval Queue Mock` again.
