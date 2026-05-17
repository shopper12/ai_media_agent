# Next Step: Google Sheets Approval Queue

The output-only workflow is only a test. The next real milestone is to send approval queue rows into Google Sheets.

## Target structure

```text
n8n Code node output
→ Google Sheets append rows
→ owner edits OwnerDecision
→ next workflow reads approved rows
```

## Sheet name

```text
AI Media Approval Queue
```

## Header row

Create row 1 with these columns:

```text
ContentId
TopicId
Category
ExpectedProfitScore
Title
Format
RiskFlag
AIReviewScore
ApprovalStatus
OwnerDecision
CTA
CreatedAt
PublishedAt
ResultUrl
```

## OwnerDecision values

```text
APPROVE
HOLD
REJECT
```

## n8n setup

1. Open n8n at `http://localhost:5678`.
2. Open the successful output-only workflow.
3. Add a Google Sheets node after the Code node.
4. Create Google Sheets OAuth credential.
5. Choose the approval queue spreadsheet.
6. Operation: append rows.
7. Map JSON fields to the sheet columns.
8. Execute workflow.
9. Confirm rows are appended to the sheet.

## Next workflow after this

Once rows are in Google Sheets:

1. Read sheet rows.
2. Filter rows where `OwnerDecision` equals `APPROVE`.
3. Send approved rows to content generation.
4. Leave `HOLD` rows for rewrite.
5. Archive `REJECT` rows.
