# Google Sheets append rows mapping

Use this after the service account is created, the JSON key is downloaded, and the Google Sheet is shared with the service account email.

## 1. n8n credential

In n8n:

```text
Credentials
→ Create Credential
→ Google Sheets API
→ Service Account
```

Paste the service account JSON key content.

## 2. Workflow to edit

Use the workflow that already runs successfully:

```text
07 Dashboard Output Only
```

Add a Google Sheets node after the Code node.

## 3. Google Sheets node settings

Recommended settings:

```text
Resource: Sheet Within Document
Operation: Append Row in Sheet
Document: use spreadsheet URL or ID
Sheet: Sheet1 or the actual tab name
Mapping Column Mode: Map Each Column Manually
```

## 4. Manual mappings

Map fields like this:

```text
ContentId            {{$json.contentId}}
Category             {{$json.category}}
ExpectedProfitScore  {{$json.score}}
Title                {{$json.title}}
Format               {{$json.format}}
RiskFlag             {{$json.risk}}
ApprovalStatus       {{$json.status}}
CreatedAt            {{$json.generatedAt}}
```

Leave other columns blank for now:

```text
TopicId
AIReviewScore
OwnerDecision
CTA
PublishedAt
ResultUrl
```

## 5. Test

Click:

```text
Execute workflow
```

Expected result:

```text
Three rows are appended to the Google Sheet.
```

## 6. Next milestone

After rows are written to Google Sheets:

1. Owner fills OwnerDecision with APPROVE, HOLD, or REJECT.
2. Create a second workflow that reads the sheet.
3. Filter rows where OwnerDecision is APPROVE.
4. Send approved rows to content generation.
