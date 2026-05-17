# Next Step: Read approved rows from Google Sheets

This step comes after the Google Sheets append-row test succeeds.

## 1. Confirm the append worked

Open the sheet:

```text
AI Media Approval Queue
```

Expected rows:

```text
CONTENT-001
CONTENT-002
CONTENT-003
```

## 2. Owner decision test

In the `OwnerDecision` column, set values manually:

```text
CONTENT-001  APPROVE
CONTENT-002  HOLD
CONTENT-003  REJECT
```

## 3. Create next n8n workflow

Create a new workflow named:

```text
08 Read Approved Rows
```

Nodes:

```text
Manual Trigger
→ Google Sheets: Get row(s) in sheet
→ Filter: OwnerDecision equals APPROVE
→ Code: build approved content generation input
```

## 4. Google Sheets read node

Recommended node settings:

```text
Resource: Sheet Within Document
Operation: Get Row(s)
Document: AI Media Approval Queue
Sheet: sheet1
Return All: true
```

## 5. Filter node condition

```text
{{$json.OwnerDecision}} equals APPROVE
```

## 6. Code node output

Use this code:

```javascript
return $input.all().map(item => {
  const row = item.json;
  return {
    json: {
      contentId: row.ContentId,
      category: row.Category,
      score: row.ExpectedProfitScore,
      title: row.Title,
      format: row.Format,
      risk: row.RiskFlag,
      approvalStatus: row.ApprovalStatus,
      ownerDecision: row.OwnerDecision,
      nextStep: 'GENERATE_CONTENT_DRAFT'
    }
  };
});
```

## 7. Success criteria

Execution output should include only rows with:

```text
OwnerDecision = APPROVE
```

In the example setup, only `CONTENT-001` should pass.

## 8. Next milestone

After approved rows are filtered correctly:

```text
Approved rows
→ AI content draft generation
→ risk review
→ owner final review
```
