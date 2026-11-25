# Personal AI Job Radar (free-first starter)

This starter scans configured public ATS job feeds, deduplicates requisitions, checks the 24-hour window, scores new roles against a candidate profile, and can send Telegram alerts.

## Cost and privacy design

- **Hosting:** GitHub Actions, scheduled every 5 minutes. Standard GitHub-hosted runners are free for public repositories. The schedule can be delayed by GitHub during busy periods.
- **No Cloudflare account. No credit/debit card is required by this setup.**
- **AI:** optional Gemini API call using `gemini-2.5-flash-lite` on the free tier. If no key is configured or the free quota is exhausted, a local keyword scorer runs instead. Do not connect Cloud Billing or upgrade this project. Do not change the model to a paid model.
- **No runtime Python packages:** Python standard library only.
- **Notifications:** Telegram bot; free to use for personal alerts.
- `data/state.json` stores only public requisition IDs and timestamps so repeat scans do not alert on the same job. The file is committed to the public repository.
- Keep all API tokens and your detailed profile in GitHub Actions Secrets. Never put tokens in source files, commits, screenshots, or `sources.json`.
- Gemini's free tier may use submitted prompts to improve Google products. The prompt sends job-posting text plus a generic skills profile, not a CV or personal identifiers. Do not put confidential material in the profile.

**Zero-payment guardrail:** use a public GitHub repository; do not add a payment method to Cloudflare (not used), do not link a Google Cloud Billing account, do not upgrade Gemini, and do not configure any paid API or runner. A quota limit should cause AI scoring to fall back locally, not switch to a paid service.

## What is supported in this version

- Greenhouse public job-board API
- Lever public postings API
- Ashby public job-board API
- SmartRecruiters public postings API
- Workday public CXS jobs endpoint (requires tenant, site, and base URL)

The scanner only sees the companies/boards you add in `config/sources.json`. It does not scrape LinkedIn and it cannot discover every employer on the internet. Company career pages that do not expose one of these public feeds need a separate connector.

## 1. Create a public GitHub repository

1. Sign in to GitHub and create a new repository, for example `personal-job-radar`.
2. Set visibility to **Public**. This is important: GitHub says standard hosted runners are free for public repositories. A private repository has a limited monthly included quota on the Free plan.
3. Do not enable a paid product, larger runner, or paid add-on.
4. Upload the extracted contents of this folder to the repository's default branch (usually `main`). Keep the `.github/workflows/job-radar.yml` path exactly as it is.
5. Open **Actions** in the repository and enable workflows if GitHub asks.

Public source code and `data/state.json` are visible to everyone. They contain no access tokens or personal profile in this starter. Do not put your CV, phone number, email address, salary, or secrets in public files.

## 2. Add your profile privately

In the repository, open **Settings → Secrets and variables → Actions → New repository secret**.

Create `JOB_RADAR_PROFILE_JSON` with a JSON value like this (adjust it whenever needed):

```json
{
  "target_titles": ["GRC Engineer", "GRC Automation Engineer", "Security Compliance Engineer", "Compliance Engineer", "FedRAMP Engineer", "TPRM", "IT Risk", "Product Security Assurance", "Customer Trust", "AI Governance"],
  "skills": ["FedRAMP 20x", "NIST 800-53", "continuous monitoring", "GRC automation", "evidence workflows", "Python", "API integrations", "TPRM", "ISO 27001", "SOC 2", "AWS compliance", "AppSec", "DPDPA"],
  "preferred_locations": ["India remote", "Remote - India", "Gurugram", "Gurgaon", "Noida", "Delhi NCR", "Chandigarh", "Mohali", "Panchkula"],
  "other_india_locations": ["Bengaluru", "Hyderabad", "Pune", "Mumbai", "Chennai", "Kolkata"],
  "minimum_ctc_inr_lpa": 30,
  "ideal_ctc_inr_lpa": 35,
  "experience_summary": "GRC engineering; FedRAMP 20x automation; compliance engineering; evidence workflows; Python/API integrations; TPRM; ISO 27001; SOC 2; AWS/cloud compliance; AppSec; DPDPA mapping. Certifications: ISO 27001 Lead Implementer, AWS Solutions Architect, ZTCA."
}
```

The scanner will use a built-in version of this profile if this secret is omitted. No name or current employer needs to be included.

## 3. Add company ATS feeds

Edit `config/sources.json` and add the employer boards you want to monitor. Examples of the required shapes:

```json
{
  "greenhouse": [
    {"company": "Company Name", "board_token": "board-token", "enabled": true}
  ],
  "lever": [
    {"company": "Company Name", "site": "lever-site-slug", "enabled": true}
  ],
  "ashby": [
    {"company": "Company Name", "board": "ashby-board-name", "enabled": true}
  ],
  "smartrecruiters": [
    {"company": "Company Name", "company_identifier": "company-id", "enabled": true}
  ],
  "workday": [
    {"company": "Company Name", "base_url": "https://company.wd5.myworkdayjobs.com", "tenant": "tenant-name", "site": "External_Careers", "enabled": true}
  ]
}
```

To find the right identifier, open the company's official careers page and inspect its job-board URL:

- Greenhouse: `https://job-boards.greenhouse.io/BOARD_TOKEN` or `https://boards.greenhouse.io/BOARD_TOKEN` → use `BOARD_TOKEN`.
- Lever: `https://jobs.lever.co/SITE_SLUG` → use `SITE_SLUG`.
- Ashby: `https://jobs.ashbyhq.com/BOARD_NAME` → use `BOARD_NAME`.
- SmartRecruiters: `https://jobs.smartrecruiters.com/COMPANY_ID` → use `COMPANY_ID`.
- Workday: use the official careers URL host, tenant segment, and site segment. Workday configurations differ by employer; test after adding each one.

Add one employer at a time and verify the Action log shows a nonzero job count. Do not guess identifiers. If a board fails, it is skipped and logged; other boards continue.

## 4. Set up Telegram alerts (recommended)

1. In Telegram, open the official `@BotFather`, send `/newbot`, and follow its steps.
2. Copy the bot token. Keep it private.
3. Open the new bot chat and press **Start**.
4. To obtain your chat ID, open `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates` in a browser after sending the bot a message. Read `message.chat.id` in the response. Do not share this URL or token with anyone.
5. Add these repository Actions Secrets:
   - `TELEGRAM_BOT_TOKEN` = bot token
   - `TELEGRAM_CHAT_ID` = your chat ID

If you do not configure Telegram, scan results appear in the GitHub Actions log only.

## 5. Enable the free Gemini AI layer (optional)

1. Open Google AI Studio: https://aistudio.google.com/apikey
2. Create an API key on the free tier.
3. **Do not click “Set up billing”, do not add/link a payment method, and do not upgrade the project.**
4. Add the key as the GitHub Actions secret `GEMINI_API_KEY`.
5. The script uses `gemini-2.5-flash-lite` only. It does not use Google Search grounding or other billable tools.

If AI quota is exhausted, the scanner falls back to local scoring. Google's free-tier data-use terms differ from its paid tier; don't send your resume, personal data, confidential work details, or employer documents. Only public job text and a generic skill profile are sent.

## 6. First run and monitoring

1. Open **Actions → Job Radar → Run workflow**.
2. For the very first run, it silently creates a baseline from current vacancies. This prevents old jobs already on the board from being falsely reported as new.
3. Check the run log. It should show one line per configured ATS board and the number of fetched jobs.
4. After that, the scheduled workflow runs every 5 minutes. New requisitions are deduplicated and checked against the previous 24 hours.
5. If a feed exposes an actual creation/publication timestamp, that is shown as **Published**. If it does not, the alert clearly says **First seen** and does not claim that the employer published it at that time.
6. If you add new employers later, run the workflow manually with `baseline_only = true` once to avoid flooding yourself with existing vacancies.

## 7. Run locally in Termux (optional)

This is for testing only; the phone must remain online and the process must keep running. Cloud scheduling via GitHub Actions is more reliable.

```bash
pkg update -y
pkg install python git -y
git clone https://github.com/YOUR-USERNAME/personal-job-radar.git
cd personal-job-radar
python job_radar.py --baseline-only
python job_radar.py
```

For local AI/Telegram testing, set environment variables in the Termux session before running. Do not hard-code tokens in the script or upload them to GitHub.

## Important accuracy limits

- Five-minute polling is near-real-time, not instant; GitHub may delay scheduled runs.
- Detection depends on the configured official ATS boards and how often employers publish data to them.
- The first run is a silent baseline. A later first-seen job may have been present elsewhere before it appeared in the configured feed; the alert labels this honestly.
- Jobs with verified publication timestamps older than 24 hours are stored for deduplication but not alerted.
- Salary is never inferred. “Not disclosed” means the vacancy did not state a figure.
- Scores are screening aids, not a probability of selection. Always open the official listing and check eligibility, location, mandatory experience, and compensation.
- ATS feed formats and free-tier quotas can change; monitor the workflow log periodically.
