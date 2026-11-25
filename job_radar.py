#!/usr/bin/env python3
"""Zero-hosting-cost job radar starter. Python standard library only."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
SOURCES_FILE = ROOT / "config" / "sources.json"
STATE_FILE = ROOT / "data" / "state.json"
GEMINI_MODEL = "gemini-3.5-flash-lite"  # Free-tier model; do not change to a paid model.
USER_AGENT = "PersonalJobRadar/1.0 (+https://github.com/)"
MAX_AI_JOBS_PER_CALL = 12
MIN_ALERT_SCORE = 55

DEFAULT_PROFILE = {
    "target_titles": [
        "GRC Engineer", "GRC Automation Engineer", "Security Compliance Engineer",
        "Compliance Engineer", "FedRAMP Engineer", "NIST 800-53", "Continuous Monitoring",
        "TPRM Analyst", "Third Party Risk", "IT Risk Engineer", "Product Security Assurance",
        "Customer Trust", "AI Governance", "AI Security Governance"
    ],
    "skills": [
        "GRC", "FedRAMP", "NIST 800-53", "continuous monitoring", "evidence workflows",
        "Python", "API integrations", "TPRM", "IT risk", "ISO 27001", "SOC 2", "AWS",
        "AppSec", "application security", "DPDPA", "compliance automation", "control mapping",
        "remediation tracking", "security compliance", "cloud compliance", "AI governance"
    ],
    "preferred_locations": [
        "India remote", "Remote - India", "Gurugram", "Gurgaon", "Noida", "Delhi NCR",
        "Delhi", "Chandigarh", "Mohali", "Panchkula"
    ],
    "other_india_locations": [
        "Bengaluru", "Bangalore", "Hyderabad", "Pune", "Mumbai", "Chennai", "Kolkata", "Jaipur"
    ],
    "minimum_ctc_inr_lpa": 30,
    "ideal_ctc_inr_lpa": 35,
    "experience_summary": (
        "GRC engineering and security compliance work; FedRAMP 20x Class C automation; "
        "evidence workflows; Python and API integrations; TPRM; ISO 27001; SOC 2; AWS/cloud compliance; AppSec. "
        "Certifications: ISO 27001 Lead Implementer, AWS Solutions Architect, ZTCA."
    )
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(dt: datetime | None = None) -> str:
    dt = dt or utc_now()
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            # Most ATS APIs use milliseconds; small values are seconds.
            seconds = float(value) / 1000 if float(value) > 10_000_000_000 else float(value)
            return datetime.fromtimestamp(seconds, timezone.utc)
        text = str(value).strip()
        if re.fullmatch(r"\d{10,13}", text):
            return parse_datetime(int(text))
        # Do not manufacture a date from relative text such as "Posted 2 days ago".
        if not re.match(r"^\d{4}-\d{2}-\d{2}", text):
            return None
        text = text.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def strip_html(value: Any) -> str:
    if not value:
        return ""
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", str(value), flags=re.I)
    text = re.sub(r"</\s*(p|li|div|h[1-6])\s*>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip()


def http_json(url: str, method: str = "GET", payload: dict | None = None, headers: dict | None = None) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if body is not None:
        req_headers["Content-Type"] = "application/json"
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=body, headers=req_headers, method=method)
    with urllib.request.urlopen(req, timeout=25) as response:
        raw = response.read()
    return json.loads(raw.decode("utf-8", errors="replace"))


def normalize_job(provider: str, company: str, raw_id: Any, title: Any, location: Any,
                  url: Any, description: Any, published: Any = None, remote: Any = None) -> dict:
    source_id = str(raw_id or url or title or "unknown")
    job_id = f"{provider}:{company.casefold().strip()}:{source_id}"
    loc = str(location or "Not specified")
    if remote is True and "remote" not in loc.casefold():
        loc = f"{loc} (Remote)" if loc != "Not specified" else "Remote"
    return {
        "id": job_id,
        "company": str(company),
        "title": strip_html(title) or "Untitled role",
        "location": loc,
        "url": str(url or ""),
        "description": strip_html(description)[:16000],
        "published_at": iso_utc(parse_datetime(published)) if parse_datetime(published) else None,
        "provider": provider,
    }


def fetch_greenhouse(source: dict) -> list[dict]:
    board = urllib.parse.quote(str(source["board_token"]), safe="")
    data = http_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
    out = []
    for item in data.get("jobs", []):
        out.append(normalize_job(
            "greenhouse", source["company"], item.get("id"), item.get("title"),
            (item.get("location") or {}).get("name"), item.get("absolute_url"),
            item.get("content"), item.get("published_at") or item.get("first_published")
        ))
    return out


def fetch_lever(source: dict) -> list[dict]:
    site = urllib.parse.quote(str(source["site"]), safe="")
    data = http_json(f"https://api.lever.co/v0/postings/{site}?mode=json")
    out = []
    for item in data if isinstance(data, list) else []:
        cats = item.get("categories") or {}
        desc = "\n".join(filter(None, [item.get("descriptionPlain"), item.get("additionalPlain")]))
        out.append(normalize_job(
            "lever", source["company"], item.get("id"), item.get("text"),
            cats.get("location") or cats.get("allLocations"), item.get("hostedUrl"),
            desc, item.get("createdAt") or item.get("created_at"), item.get("workplaceType") == "remote"
        ))
    return out


def fetch_ashby(source: dict) -> list[dict]:
    board = urllib.parse.quote(str(source["board"]), safe="")
    data = http_json(f"https://api.ashbyhq.com/posting-api/job-board/{board}")
    out = []
    for item in data.get("jobs", []):
        desc = "\n".join(filter(None, [item.get("descriptionPlain"), item.get("descriptionHtml")]))
        out.append(normalize_job(
            "ashby", source["company"], item.get("id"), item.get("title"),
            item.get("location"), item.get("jobUrl") or item.get("applyUrl"),
            desc, item.get("publishedAt"), item.get("isRemote")
        ))
    return out


def fetch_smartrecruiters(source: dict) -> list[dict]:
    company = urllib.parse.quote(str(source["company_identifier"]), safe="")
    out, offset, limit = [], 0, 100
    for _ in range(5):
        data = http_json(f"https://api.smartrecruiters.com/v1/companies/{company}/postings?limit={limit}&offset={offset}")
        items = data.get("content", [])
        for item in items:
            loc = item.get("location") or {}
            loc_text = ", ".join(filter(None, [loc.get("city"), loc.get("region"), loc.get("country")]))
            job_id = item.get("id")
            job_url = item.get("ref") or f"https://jobs.smartrecruiters.com/{source['company_identifier']}/{job_id}"
            desc = item.get("jobAd", {}).get("sections", {}) if isinstance(item.get("jobAd"), dict) else {}
            desc_text = " ".join(strip_html(v.get("text")) for v in desc.values() if isinstance(v, dict)) if isinstance(desc, dict) else ""
            out.append(normalize_job(
                "smartrecruiters", source["company"], job_id, item.get("name"), loc_text,
                job_url, desc_text, item.get("releasedDate") or item.get("released_date")
            ))
        if len(items) < limit:
            break
        offset += limit
    return out


def fetch_workday(source: dict) -> list[dict]:
    base = str(source["base_url"]).rstrip("/")
    tenant = urllib.parse.quote(str(source["tenant"]), safe="")
    site = urllib.parse.quote(str(source["site"]), safe="")
    endpoint = f"{base}/wday/cxs/{tenant}/{site}/jobs"
    out, offset, limit = [], 0, 20
    for _ in range(10):
        data = http_json(endpoint, method="POST", payload={
            "appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""
        })
        items = data.get("jobPostings", [])
        for item in items:
            path = item.get("externalPath") or ""
            job_url = base + path if path.startswith("/") else path or base
            desc = " ".join(strip_html(x) for x in (item.get("bulletFields") or []))
            out.append(normalize_job(
                "workday", source["company"], item.get("bulletFields", [None])[0] if False else path,
                item.get("title"), item.get("locationsText"), job_url, desc,
                item.get("publishedAt") or item.get("datePosted")
            ))
        total = data.get("total")
        if len(items) < limit or (isinstance(total, int) and offset + limit >= total):
            break
        offset += limit
    return out


FETCHERS = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
    "smartrecruiters": fetch_smartrecruiters,
    "workday": fetch_workday,
}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc


def get_profile() -> dict:
    raw = os.getenv("JOB_RADAR_PROFILE_JSON", "").strip()
    if raw:
        try:
            custom = json.loads(raw)
            merged = DEFAULT_PROFILE.copy()
            merged.update(custom)
            return merged
        except json.JSONDecodeError as exc:
            print(f"WARNING: JOB_RADAR_PROFILE_JSON is invalid; using built-in profile: {exc}")
    return DEFAULT_PROFILE.copy()


def fetch_all(sources: dict) -> list[dict]:
    jobs: list[dict] = []
    for provider, entries in sources.items():
        fetcher = FETCHERS.get(provider.casefold())
        if not fetcher:
            print(f"WARNING: Unsupported ATS provider '{provider}' (skipped)")
            continue
        for source in entries or []:
            if source.get("enabled", True) is False:
                continue
            try:
                found = fetcher(source)
                jobs.extend(found)
                print(f"{provider}: {source.get('company', 'Unknown')} -> {len(found)} jobs")
            except Exception as exc:  # one bad employer must not stop all the others
                print(f"WARNING: {provider} / {source.get('company', 'Unknown')}: {type(exc).__name__}: {exc}")
            time.sleep(0.25)
    # Deduplicate in case multiple feeds contain the same requisition.
    unique = {job["id"]: job for job in jobs}
    return list(unique.values())


def local_score(job: dict, profile: dict) -> dict:
    title = job.get("title", "").casefold()
    text = (job.get("title", "") + " " + job.get("description", "")).casefold()
    target_titles = [str(x).casefold() for x in profile.get("target_titles", [])]
    skills = [str(x).casefold() for x in profile.get("skills", [])]
    preferred = [str(x).casefold() for x in profile.get("preferred_locations", [])]
    other_india = [str(x).casefold() for x in profile.get("other_india_locations", [])]

    title_hits = [t for t in target_titles if t and (t in title or (len(t) > 12 and t in text))]
    skill_hits = [s for s in skills if s and s in text]
    location_text = job.get("location", "").casefold()
    preferred_hits = [loc for loc in preferred if loc and loc in location_text]
    india_hits = [loc for loc in other_india if loc and loc in location_text]

    title_score = min(35, 12 + 8 * len(title_hits)) if title_hits else 0
    skill_score = min(45, round(45 * len(skill_hits) / max(5, min(len(skills), 12))))
    location_score = 20 if preferred_hits else (12 if india_hits else (8 if "remote" in location_text else 0))
    fit = min(100, title_score + skill_score + location_score)
    reasons = []
    if title_hits:
        reasons.append("Title aligns with: " + ", ".join(title_hits[:3]))
    if skill_hits:
        reasons.append("Skills found: " + ", ".join(skill_hits[:5]))
    if preferred_hits:
        reasons.append("Preferred location match: " + ", ".join(preferred_hits[:3]))
    elif india_hits:
        reasons.append("India location match, but outside the primary preferred cities")
    else:
        reasons.append("Location needs manual verification")
    return {
        "fit_score": fit,
        "employer_quality_score": 50,
        "employer_quality_note": "Not independently assessed; review company fundamentals and role scope.",
        "match_reasons": reasons[:4],
        "experience_gaps": ["AI review unavailable; compare mandatory requirements manually."],
        "compensation": "Not disclosed unless stated in the job posting.",
        "scoring_method": "Local keyword fallback (AI unavailable or not configured)."
    }


def gemini_score_batch(jobs: list[dict], profile: dict, api_key: str) -> dict[str, dict]:
    if not jobs or not api_key:
        return {}
    compact_jobs = [{
        "id": j["id"], "company": j["company"], "title": j["title"],
        "location": j["location"], "url": j["url"], "description": j["description"][:8500]
    } for j in jobs[:MAX_AI_JOBS_PER_CALL]]
    prompt = f"""You are a careful job-fit analyst. Compare each public job posting against this candidate profile.
Candidate profile (generic skills only; do not infer identity):
{json.dumps(profile, ensure_ascii=False)}

Jobs:
{json.dumps(compact_jobs, ensure_ascii=False)}

Return ONLY valid JSON: an array with one object per input job. Every object must contain:
- id (exact input id)
- fit_score (integer 0-100; profile match, NOT hiring probability)
- employer_quality_score (integer 0-100; separate from fit; evaluate product/SaaS relevance, company maturity/reputation only when supported; otherwise use 50)
- employer_quality_note (one short sentence; say when evidence is insufficient)
- match_reasons (array of up to 4 concise evidence-based reasons)
- experience_gaps (array of up to 4 actual mandatory requirements not evidenced in profile; do not treat absent posting details as candidate deficiencies)
- compensation (quote only what the posting explicitly states, otherwise exactly 'Not disclosed')
Rules: Never invent salary, posting date, location eligibility, company facts, or experience. Do not use the current employer identity. Distinguish skills evidence from requirements that are merely not mentioned. A job with unclear India remote eligibility must say so. Do not score hiring probability. No markdown fences."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={urllib.parse.quote(api_key)}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 5000, "responseMimeType": "application/json"}
    }
    try:
        data = http_json(url, method="POST", payload=payload)
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            parsed = parsed.get("jobs", [])
        out = {}
        for item in parsed if isinstance(parsed, list) else []:
            if not isinstance(item, dict) or not item.get("id"):
                continue
            jid = str(item["id"])
            clean = {
                "fit_score": max(0, min(100, int(item.get("fit_score", 50)))),
                "employer_quality_score": max(0, min(100, int(item.get("employer_quality_score", 50)))),
                "employer_quality_note": str(item.get("employer_quality_note", "Not enough evidence to assess."))[:300],
                "match_reasons": [str(x)[:250] for x in item.get("match_reasons", [])[:4]],
                "experience_gaps": [str(x)[:250] for x in item.get("experience_gaps", [])[:4]],
                "compensation": str(item.get("compensation", "Not disclosed"))[:300],
                "scoring_method": f"AI: {GEMINI_MODEL} (free-tier project only)"
            }
            out[jid] = clean
        return out
    except Exception as exc:
        # If free quota is exhausted or model unavailable, fall back without retrying or upgrading.
        print(f"WARNING: Gemini unavailable / quota reached; using local scores. Details: {type(exc).__name__}: {exc}")
        return {}


def send_telegram(text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("INFO: Telegram not configured; results are in the workflow log.")
        return
    chunks = []
    remaining = text
    while len(remaining) > 3800:
        cut = remaining.rfind("\n\n", 0, 3800)
        if cut < 1000:
            cut = 3800
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    for chunk in chunks:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            http_json(url, method="POST", payload={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True})
        except Exception as exc:
            print(f"WARNING: Telegram notification failed: {type(exc).__name__}: {exc}")


def format_ist(value: str | None) -> str:
    dt = parse_datetime(value)
    if not dt:
        return "First seen during this scan (publication time not exposed by the feed)"
    return dt.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y, %I:%M %p IST")


def make_alert(jobs: list[dict], scores: dict[str, dict]) -> str:
    ranked = []
    for job in jobs:
        score = scores.get(job["id"], {})
        merged = {**job, **score}
        if int(merged.get("fit_score", 0)) >= MIN_ALERT_SCORE:
            ranked.append(merged)
    ranked.sort(key=lambda x: (int(x.get("fit_score", 0)), int(x.get("employer_quality_score", 0))), reverse=True)
    if not ranked:
        return ""
    lines = [f"🚨 JOB RADAR — {len(ranked)} new role(s) matching your profile", "Only newly detected roles; fit score is not hiring probability.", ""]
    for i, job in enumerate(ranked[:10], 1):
        published = job.get("published_at")
        date_label = (f"Published (source timestamp): {format_ist(published)}" if published
                      else f"First seen (feed does not expose publish time): {format_ist(job.get('first_seen_at'))}")
        lines.extend([
            f"{i}. {job['company']} — {job['title']}",
            f"Fit: {job.get('fit_score', 0)}/100 | Employer/role quality: {job.get('employer_quality_score', 50)}/100",
            f"Location: {job.get('location', 'Not specified')}",
            date_label,
            "Matches: " + ("; ".join(job.get("match_reasons", [])[:3]) or "No detailed reasons returned."),
            "Gaps/checks: " + ("; ".join(job.get("experience_gaps", [])[:2]) or "Review the mandatory requirements."),
            f"Compensation: {job.get('compensation', 'Not disclosed')}",
            f"Official listing: {job.get('url', '')}",
            ""
        ])
    if len(ranked) > 10:
        lines.append(f"Plus {len(ranked) - 10} additional qualifying role(s) in the run log.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan configured ATS feeds and alert on new matching jobs.")
    parser.add_argument("--baseline-only", action="store_true", help="Record currently visible jobs without alerting.")
    args = parser.parse_args()

    sources = load_json(SOURCES_FILE, {})
    if not isinstance(sources, dict):
        raise RuntimeError("config/sources.json must be a JSON object.")
    state = load_json(STATE_FILE, {"initialized": False, "seen": {}})
    if not isinstance(state, dict):
        state = {"initialized": False, "seen": {}}
    state.setdefault("seen", {})
    state.setdefault("initialized", False)

    jobs = fetch_all(sources)
    print(f"Fetched {len(jobs)} unique jobs across configured ATS boards.")
    now = utc_now()
    now_text = iso_utc(now)
    seen = state["seen"]

    # On the very first successful scan, create a silent baseline. This avoids
    # incorrectly labelling months-old vacancies as newly published.
    if args.baseline_only or (not state.get("initialized") and jobs):
        for job in jobs:
            seen.setdefault(job["id"], {"first_seen_at": now_text, "published_at": job.get("published_at")})
        state["initialized"] = True
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Baseline saved for {len(jobs)} jobs. No alerts sent.")
        return 0

    new_in_window = []
    cutoff = now - timedelta(hours=24)
    for job in jobs:
        if job["id"] in seen:
            continue
        first_seen = now
        job["first_seen_at"] = iso_utc(first_seen)
        seen[job["id"]] = {"first_seen_at": job["first_seen_at"], "published_at": job.get("published_at")}
        pub = parse_datetime(job.get("published_at"))
        if pub:
            if pub >= cutoff:
                new_in_window.append(job)
        else:
            # The feed does not disclose publication time: retain this as a
            # clearly labelled first-seen result, never claim it was published now.
            new_in_window.append(job)

    state["initialized"] = True
    # One small daily heartbeat keeps a public repo from looking inactive,
    # without creating a commit on every five-minute scan.
    state["last_heartbeat_date"] = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not new_in_window:
        print("No newly detected roles within the 24-hour publication/first-seen window.")
        return 0

    profile = get_profile()
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    ai_scores = gemini_score_batch(new_in_window, profile, api_key) if api_key else {}
    scores = {job["id"]: ai_scores.get(job["id"], local_score(job, profile)) for job in new_in_window}
    alert = make_alert(new_in_window, scores)
    if alert:
        send_telegram(alert)
        print(alert)
    else:
        print(f"Detected {len(new_in_window)} new job(s), but none reached the {MIN_ALERT_SCORE}/100 alert threshold.")
    print("State updated; run commit in the GitHub workflow to preserve deduplication.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FATAL: {type(error).__name__}: {error}", file=sys.stderr)
        raise
