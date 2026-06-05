# Influencer Outreach Stack — Twenty CRM + n8n (self-hosted)

A self-hosted influencer-outreach system: **Twenty CRM** (contacts + pipeline) + **n8n**
(automation) + **Stalwart** (optional self-hosted mail), all in one `docker compose`.

It runs a 2-email cold cadence, detects replies, drafts AI responses you approve in Twenty,
sends them, tracks a Kanban pipeline, analyzes closed deals, and auto-cleans stale leads.

> **No contacts or credentials are in this repo.** They live inside Docker volumes/databases,
> so you start with an empty CRM and add your own contacts + your own email/API credentials.

## Pipeline (Kanban stages on each contact)
```
Cold lead → Email 1 sent → Email 2 sent
   → Lead · awaiting my approval   (reply came in → AI drafts a response)
   → Lead · awaiting client reply  (you approved → it sent)
   → Deal  (AI extracts price/terms, creates an Opportunity)
   → Done  (no reply after 7 days, or a "not interested" reply)
```

## Setup

### 1. Start the stack
```bash
cd deploy
cp .env.example .env          # then fill in your own secrets (see comments in the file)
# local testing:
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d
# production: see deploy/GO-LIVE.md
```
- Twenty → http://localhost:3100  (create your workspace + admin user)
- n8n   → http://localhost:5678  (create your owner account)

### 2. Provision the Twenty custom fields
The workflow needs ~20 custom fields on the **Person** object. Create them all at once:
```bash
# Twenty → Settings → Developers → API keys → generate one
export TWENTY_API_KEY="eyJ..."
python3 setup_twenty_fields.py
```

### 3. Import the n8n workflow
- n8n → Workflows → **Import from File** → `outreach_workflow.json`
- Create your credentials in n8n and select them on the nodes:
  - **Header Auth** (`Authorization: Bearer <your Twenty API key>`) → the HTTP Request nodes
  - **SMTP** (Gmail/Workspace or your server) → the Send Email nodes
  - **IMAP** (Gmail or your server) → the `Monitor Gmail Inbox` trigger
  - **OpenRouter** (or your LLM) → the AI Agent nodes
- Set your **sending address** (replace `YOUR_SENDING_EMAIL@example.com`) in the two filter
  code nodes (`Filter Replies Only`, `Extract Bounced Email`) and the Send Email nodes' From.

### 4. Add contacts & go
- Import contacts into Twenty (UI, or adapt `import_to_twenty.py` / `enrich_twenty.py` to your spreadsheet).
- New contacts start at **Cold lead** to enter the cadence.
- Flip the n8n workflow **Active** when ready.

## Scripts
| Script | Purpose |
|---|---|
| `setup_twenty_fields.py` | Create all required custom fields on Person (idempotent) |
| `import_to_twenty.py` | Bulk-import contacts from a spreadsheet (`--commit` to apply) |
| `enrich_twenty.py` | Backfill social URLs / size / niche from a spreadsheet |
| `cadence_admin.py` | Test helpers: add-test / pause-others / restore / status |

All scripts read `TWENTY_API_KEY` (and optional `TWENTY_BASE_URL`) from the environment.

## Email options
- **Simplest:** send + receive via Gmail/Workspace (SMTP + IMAP) — best deliverability.
- **Self-hosted hybrid:** send via Gmail/Workspace relay, receive on your own **Stalwart**
  server. Requires a real domain + DNS (MX/SPF/DKIM/DMARC). Full steps in **`deploy/GO-LIVE.md`**.

## Layout
```
deploy/                 docker-compose + .env.example + Caddyfile + GO-LIVE.md
outreach_workflow.json   the n8n workflow
setup_twenty_fields.py  provision Twenty custom fields
import_to_twenty.py / enrich_twenty.py / cadence_admin.py   helper scripts
```
