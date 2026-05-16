# Approval Queue Schema

Google Sheets or CSV approval queue columns:

| Column | Meaning |
|---|---|
| ContentId | content id |
| TopicId | topic id |
| Category | category |
| ExpectedProfitScore | expected profit score |
| Title | content title |
| Format | Shorts / Blog / Newsletter |
| RiskFlag | risk flag |
| AIReviewScore | AI review score |
| ApprovalStatus | READY_FOR_OWNER_APPROVAL / OWNER_REVIEW_REQUIRED |
| OwnerDecision | APPROVE / HOLD / REJECT |
| CTA | conversion call-to-action |
| CreatedAt | created timestamp |
| PublishedAt | published timestamp |
| ResultUrl | published URL |

Rules:

- Empty OwnerDecision means no publish.
- APPROVE moves item to publish queue.
- HOLD moves item to rewrite queue.
- REJECT moves item to archive queue.
