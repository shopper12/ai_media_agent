"""Generate content candidates using Gemini AI with category-specific prompts.

This replaces the old hardcoded template system with:
1. Category-specific prompts loaded from prompts/category/
2. Gemini API for intelligent, varied content generation
3. Quality scoring based on config weights
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build

SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
GOOGLE_SERVICE_ACCOUNT_JSON = os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
SHEET_NAME = os.environ.get("SHEET_NAME", "sheet1")
CONFIG_PATH = os.environ.get("CONTENT_STRATEGY_CONFIG", "config/content_candidate_strategy.json")
PROMPTS_DIR = Path(os.environ.get("PROMPTS_DIR", "prompts/category"))

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
HEADERS = [
    "ContentId", "TopicId", "Category", "ExpectedProfitScore",
    "Title", "Format", "RiskFlag", "AIReviewScore",
    "ApprovalStatus", "OwnerDecision", "CTA", "CreatedAt",
    "PublishedAt", "ResultUrl", "DraftHook", "DraftBody",
    "DraftCTA", "RiskReviewStatus", "GeneratedAt", "FinalStatus",
    "RecommendedFormat", "ViralPotentialScore", "PublishChannel",
    "HookConcept", "ViralTrigger", "AffiliateProgram",
    "EstimatedUnitValue", "RiskLevel", "ShortsScriptJson",
    "ThumbnailMainText", "ThumbnailSubText", "SEOKeywords",
]


def now_kst() -> str:
    return datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M:%S KST")


def sheets_service():
    info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_category_prompt(category_name: str) -> str:
    """Load category-specific prompt from prompts/category/. Falls back to generic."""
    slug = re.sub(r"[^가-힣a-zA-Z0-9]+", "_", category_name).strip("_")
    prompt_file = PROMPTS_DIR / f"{slug}.md"
    if prompt_file.exists():
        return prompt_file.read_text(encoding="utf-8")
    generic = PROMPTS_DIR.parent / "generic_content.md"
    if generic.exists():
        return generic.read_text(encoding="utf-8")
    return ""


def score_candidate(tier_config: dict) -> tuple[float, float]:
    """Calculate EPS and VPS from tier base_metrics."""
    m = tier_config.get("base_metrics", {})
    eps = (
        m.get("affiliate_or_ad_unit_value", 0.5) * 0.30 +
        m.get("search_trend_momentum", 0.5) * 0.20 +
        m.get("competitor_content_performance", 0.5) * 0.20 +
        m.get("conversion_intent_score", 0.5) * 0.15 +
        m.get("repeatability", 0.5) * 0.10 +
        m.get("automation_ease", 0.5) * 0.05
    )
    vps = (
        m.get("hook_shock_value", 0.5) * 0.35 +
        m.get("relatability_score", 0.5) * 0.25 +
        m.get("share_motivation", 0.5) * 0.20 +
        m.get("trend_timing", 0.5) * 0.20
    )
    return round(eps, 3), round(vps, 3)


def pick_format(eps: float, vps: float, config: dict) -> tuple[str, str]:
    """Pick recommended_format and publish_channel from format_rules."""
    for rule in config.get("format_rules", []):
        cond = rule["condition"]
        cond_py = cond.replace("EPS", str(eps)).replace("VPS", str(vps))
        try:
            if eval(cond_py):  # noqa: S307
                return rule["recommended_format"], rule["publish_channel"]
        except Exception:
            continue
    return "Blog", "NAVER_BLOG"


def gemini_generate(prompt_text: str, tier: dict, existing_titles: set) -> dict | None:
    """Call Gemini to generate a single content candidate."""
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    existing_str = "\n".join(f"- {t}" for t in list(existing_titles)[-20:]) if existing_titles else "없음"
    title_ideas = "\n".join(f"- {p}" for p in tier.get("title_patterns", []))
    hook_ideas = "\n".join(f"- {h}" for h in tier.get("hook_patterns", []))

    full_prompt = f"""{prompt_text}

---
## 이번 생성 지시

카테고리: {tier['category']}

참고 제목 패턴 (그대로 쓰지 말고 변형해서 사용):
{title_ideas}

참고 훅 패턴:
{hook_ideas}

이미 생성된 제목 (중복 금지):
{existing_str}

위 프롬프트의 출력 형식(JSON)을 그대로 따라 응답하세요.
코드블록(```json ... ```) 안에 완전한 JSON만 출력하세요. 다른 설명 텍스트는 일절 포함하지 마세요.
"""

    try:
        response = model.generate_content(full_prompt)
        raw = response.text.strip()
        json_match = re.search(r"```json\s*([\s\S]+?)\s*```", raw)
        if json_match:
            return json.loads(json_match.group(1))
        return json.loads(raw)
    except Exception as exc:
        print(f"[Gemini error] {tier['category']}: {exc}")
        return None


def get_existing_data(service):
    values = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:AZ",
        valueRenderOption="FORMATTED_VALUE",
    ).execute().get("values", [])
    if not values:
        return set(), set(), 0
    headers = values[0]
    title_idx = headers.index("Title") if "Title" in headers else 4
    id_idx = 0
    existing_titles = set()
    existing_ids = set()
    max_num = 0
    for row in values[1:]:
        if len(row) > title_idx:
            existing_titles.add(row[title_idx])
        if row:
            existing_ids.add(row[id_idx])
            if str(row[id_idx]).startswith("CONTENT-"):
                try:
                    max_num = max(max_num, int(row[id_idx].split("-")[1]))
                except (IndexError, ValueError):
                    pass
    return existing_titles, existing_ids, max_num


def build_row(content_id: str, topic_id: str, tier: dict, generated: dict,
             eps: float, vps: float, fmt: str, channel: str, created_at: str) -> list:
    script = generated.get("shorts_script", [])
    script_json = json.dumps(script, ensure_ascii=False) if script else ""
    tags = generated.get("tags", [])
    seo_keywords = ", ".join(tags) if tags else tier.get("category", "")
    cta = generated.get("cta", "")
    hook = generated.get("hook", "")
    blog_outline = generated.get("blog_body_outline", [])
    body_summary = " / ".join(blog_outline[:3]) if blog_outline else ""
    return [
        content_id,
        topic_id,
        tier["category"],
        round(eps * 100, 1),
        generated.get("title", ""),
        fmt,
        tier.get("risk_level", "LOW"),
        round(vps * 100, 1),
        "READY_FOR_OWNER_APPROVAL",
        "",
        cta,
        created_at,
        "", "",
        hook,
        body_summary,
        cta,
        "PENDING",
        created_at,
        "",
        fmt,
        round(vps, 3),
        channel,
        ", ".join(tier.get("hook_patterns", [])[:1]),
        ", ".join(tier.get("title_patterns", [])[:1]),
        tier.get("affiliate_program", ""),
        tier.get("estimated_unit_value", ""),
        tier.get("risk_level", "LOW"),
        script_json,
        generated.get("thumbnail_main", ""),
        generated.get("thumbnail_sub", ""),
        seo_keywords,
    ]


def ensure_headers(service):
    current = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!1:1",
    ).execute().get("values", [])
    if not current or current[0][:len(HEADERS)] != HEADERS:
        service.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=f"{SHEET_NAME}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": [HEADERS]},
        ).execute()
        print("headers updated")


def append_rows(service, rows: list):
    if not rows:
        print("no rows to append")
        return
    service.spreadsheets().values().append(
        spreadsheetId=SPREADSHEET_ID,
        range=f"{SHEET_NAME}!A:AF",
        valueInputOption="USER_ENTERED",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()
    print(f"appended {len(rows)} candidates")


def main():
    config = load_config()
    service = sheets_service()
    ensure_headers(service)
    existing_titles, _, max_num = get_existing_data(service)

    max_per_run = int(config.get("candidate_rules", {}).get("max_new_candidates_per_run", 6))
    tiers = config.get("topic_tiers", [])
    created_at = now_kst()
    rows = []
    next_num = max_num + 1

    for tier in tiers:
        if len(rows) >= max_per_run:
            break
        category = tier["category"]
        eps, vps = score_candidate(tier)
        fmt, channel = pick_format(eps, vps, config)
        prompt_text = load_category_prompt(category)
        if not prompt_text:
            print(f"[skip] no prompt for {category}")
            continue

        generated = gemini_generate(prompt_text, tier, existing_titles)
        if not generated:
            print(f"[skip] gemini failed for {category}")
            continue

        title = generated.get("title", "")
        if not title or title in existing_titles:
            print(f"[skip] duplicate or empty title for {category}")
            continue

        content_id = f"CONTENT-{next_num:03d}"
        topic_id = f"TOPIC-{next_num:03d}"
        next_num += 1
        existing_titles.add(title)

        row = build_row(content_id, topic_id, tier, generated,
                       eps, vps, fmt, channel, created_at)
        rows.append(row)
        print(f"[ok] {content_id} | {category} | {title} | EPS={eps} VPS={vps}")

    append_rows(service, rows)


if __name__ == "__main__":
    main()
