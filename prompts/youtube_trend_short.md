# YouTube Trend Shorts Prompt

Create a rights-safe bilingual Korean/English YouTube Shorts script from the provided YouTube Data API trend metadata.

Rules:
- Do not download, quote at length from, imitate, or reuse the original video's audio, video clips, thumbnail, transcript, or copyrighted creative expression.
- Treat the trend metadata as a source signal only: title, channel name, public counts, publish date, and source URL.
- Make the Short original commentary for Korean viewers who want a fast explanation of a US trend.
- Use Korean as the main narration language and natural English phrases where helpful.
- Avoid unverifiable claims, medical/legal/financial advice, harassment, and sensational certainty.
- Include a clear AI-assisted/original-commentary disclosure in the description.
- Keep the video suitable for a 45-60 second vertical Short.

Return strict JSON only with this shape:

{
  "title": "100 characters or fewer",
  "description": "YouTube description with disclosure and source URL",
  "tags": ["up to 15 concise tags"],
  "narration": ["5 to 7 short spoken lines"],
  "on_screen": ["5 to 7 very short screen text lines"],
  "cta": "one short call to action"
}
