# Windows data folder permission fix

If n8n cannot write `/files/data/approval_queue.json`, check whether old test files are owned or locked by Docker.

Recommended local fix:

```powershell
cd C:\codetest\ai_media_agent
docker compose down
Remove-Item -Force .\data\test.txt -ErrorAction SilentlyContinue
icacls .\data /grant "Everyone:(OI)(CI)F" /T
docker compose up -d --force-recreate
```

Then run the workflow again and check:

```powershell
type C:\codetest\ai_media_agent\data\approval_queue.json
```

If Windows bind mount still blocks writes, switch the workflow output path to `/home/node/.n8n/approval_queue.json` and inspect it with:

```powershell
docker exec ai_media_agent_n8n sh -lc "cat /home/node/.n8n/approval_queue.json"
```
