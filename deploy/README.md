# Outreach stack — Twenty CRM + n8n (self-hosted, one server)

Twenty CRM and n8n on one host via a single `docker compose`, sharing one
Postgres and one Redis, behind Caddy (automatic HTTPS).

## What's here

| File | Purpose |
|------|---------|
| `docker-compose.yml` | All services: twenty-server, twenty-worker, n8n, postgres, redis, caddy |
| `.env` | Secrets + your domains. **Edit the domains. Keep private.** |
| `Caddyfile` | Reverse-proxy + TLS config. Edit the two domains. |
| `init-db/01-create-n8n-db.sql` | Creates the `n8n` database on first boot |

## Prerequisites
- A Linux server (2 vCPU / **4 GB RAM** min) with Docker + Docker Compose v2.
- Two DNS A-records pointing at the server's public IP, e.g.
  `crm.example.com` and `n8n.example.com`.
- Ports **80** and **443** open in the firewall (Caddy needs 80 for cert issuance).

---

## Step-by-step deploy

### 1. Copy this folder to the server
```bash
scp -r deploy/ user@your-server:/opt/outreach-stack
ssh user@your-server
cd /opt/outreach-stack
```

### 2. Set your domains
Edit **`.env`**:
```
TWENTY_SERVER_URL=https://crm.yourdomain.com
N8N_HOST=n8n.yourdomain.com
N8N_WEBHOOK_URL=https://n8n.yourdomain.com/
```
Edit **`Caddyfile`** — replace `crm.example.com` and `n8n.example.com` with the
same domains.

> The secrets in `.env` are pre-generated. For a real production deploy,
> regenerate them: `openssl rand -base64 32` (Twenty keys) and
> `openssl rand -hex 24` (passwords / n8n key).

### 3. Start everything
```bash
docker compose up -d
```
First boot takes a few minutes (image pulls + Twenty DB migrations).

### 4. Watch it come up
```bash
docker compose ps
docker compose logs -f twenty-server   # wait for "healthy"
```

### 5. Open the apps
- CRM:  `https://crm.yourdomain.com` → create the first workspace + admin user.
- n8n:  `https://n8n.yourdomain.com` → create the owner account.

---

## Connect n8n to Twenty

1. In **Twenty**: top-left workspace menu → **Settings → Developers → API keys →
   Generate**. Copy the key (shown once).
2. In **n8n**, the simplest robust path is the generic **HTTP Request** node
   against Twenty's REST API:
   - **Base URL (internal, no public hop):** `http://twenty-server:3000/rest`
   - **Auth:** Header `Authorization: Bearer <YOUR_TWENTY_API_KEY>`
   - Store the key as an n8n **Header Auth** credential so you don't paste it
     into every node.
   - Example — create a person:
     `POST http://twenty-server:3000/rest/people`
     body: `{ "name": { "firstName": "Jane", "lastName": "Doe" } }`
3. (Optional) **Twenty community node** for nicer UX instead of raw HTTP:
   Settings → Community Nodes → install `n8n-nodes-twenty`, then add a
   **Twenty API** credential (API key + domain). When using the community node,
   set the domain to `http://twenty-server:3000`.
4. (Optional) **Webhooks Twenty → n8n:** in n8n add a **Webhook** node, copy its
   URL, then in Twenty → Settings → Developers → **Webhooks** point an event
   (e.g. record created) at it. Internal URL: `http://n8n:5678/webhook/...`.

The existing `outreach_workflow.json` in the project root can be imported via
n8n → **Workflows → Import from File**.

---

## Day-2 operations

```bash
docker compose logs -f <service>      # tail logs
docker compose pull && docker compose up -d   # upgrade images (pin tags first!)
docker compose down                   # stop (keeps data in volumes)
```

### Backups (do this before you rely on it)
```bash
# Dump both databases
docker compose exec db pg_dump -U postgres default > twenty-$(date +%F).sql
docker compose exec db pg_dump -U postgres n8n     > n8n-$(date +%F).sql
```
Also back up the named volumes (`db-data`, `twenty-local-data`, `n8n-data`).

> ⚠️ Never lose `TWENTY_ENCRYPTION_KEY` / `N8N_ENCRYPTION_KEY` — without them the
> encrypted data in the DBs (tokens, credentials) is unrecoverable.
