# Go-Live Guide — Stalwart hub + Gmail relay + n8n + Twenty

This takes the **local** setup to a **production** server where email actually sends and
receives. Architecture (the "Stalwart-as-hub" model):

```
n8n / Mailspring  ──IMAP+SMTP──►  Stalwart (your server)  ──relay──►  Gmail/Workspace ──► influencer
influencer reply  ──MX────────►  Stalwart (INBOX)  ◄──IMAP── n8n / Mailspring
```
- **Send:** everything submits to Stalwart; Stalwart relays out through Google (authenticated → inbox, not spam).
- **Receive:** your domain's MX points at Stalwart; replies land in your own mailbox.
- **One owned mailbox** shows incoming *and* outgoing (sent copies saved by Stalwart).

---

## 0. Prerequisites
- A **real domain** (e.g. `yourbrand.com`).
- A **VPS with a static public IP and outbound port 25 allowed** — Hetzner / OVH / Scaleway (AWS, GCP, DigitalOcean, Azure **block 25**).
- **Google Workspace** on that domain (≈$6/mo) if you want to send *as* `you@yourbrand.com`. (Free Gmail rewrites the From to `…@gmail.com`.)
- Docker + Docker Compose on the VPS.

## 1. Deploy the stack
```bash
scp -r deploy/ user@server:/opt/outreach-stack && ssh user@server
cd /opt/outreach-stack
# edit .env: real domains + regenerate all secrets (openssl rand)
docker compose up -d            # base file only (NOT docker-compose.local.yml)
```
`.env` changes: `TWENTY_SERVER_URL=https://crm.yourbrand.com`, `N8N_HOST`/`WEBHOOK_URL=https://n8n.yourbrand.com`, regenerate `PG_PASSWORD`, `TWENTY_*`, `N8N_ENCRYPTION_KEY`, `STALWART_ADMIN_PASSWORD`.

## 2. DNS records (at your domain registrar)
| Type | Host | Value | Purpose |
|------|------|-------|---------|
| A | `mail` | server IP | Stalwart hostname |
| A | `crm` / `n8n` | server IP | Twenty / n8n (Caddy TLS) |
| **MX** | `@` | `mail.yourbrand.com` (priority 10) | **receive → Stalwart** |
| **PTR** | (set at VPS provider) | IP → `mail.yourbrand.com` | reverse DNS |
| **SPF** (TXT) | `@` | `v=spf1 include:_spf.google.com ~all` | authorize Google relay |
| **DKIM** (TXT) | (Stalwart shows it) | (key from Stalwart) | sign your mail |
| **DMARC** (TXT) | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:dmarc@yourbrand.com` | policy |

> If sending via **Workspace relay**, also add Google's DKIM (from the Workspace admin console) — Google guides you through it.

## 3. Stalwart: domain, DKIM, relay
In Stalwart admin (`https://mail.yourbrand.com/admin`):
1. **Add your domain** (`yourbrand.com`) → it generates the **DKIM** record → publish that TXT in DNS.
2. **Create a mailbox** (e.g. `outreach@yourbrand.com`).
3. **Outbound relay (the hub):** Settings → SMTP → Outbound → **Outbound Delivery Strategy** (a.k.a. Relay Hosts / Routing):
   - Relay host: `smtp-relay.gmail.com` (Workspace) **or** `smtp.gmail.com` (single account)
   - Port `587`, **STARTTLS**
   - Auth: your Google address + **App Password**
   - Route **all** outbound through it
   - Settings → SMTP → Outbound → TLS: **disable DANE + MTA-STS** (required with a relay)
4. (Workspace) Admin console → Apps → Gmail → **SMTP relay service**: enable, allow your server IP / require auth.

## 4. Point n8n at Stalwart
Create two n8n credentials (Credentials → New):
- **SMTP** — host `mail.yourbrand.com`, port `465`, SSL on, user `outreach@yourbrand.com`, password = Stalwart mailbox password.
- **IMAP** — host `mail.yourbrand.com`, port `993`, SSL on, same user/password.

The workflow's email nodes are already **SMTP Send Email** + **Email Trigger (IMAP)** — just select these credentials on:
`Send via Gmail`, `Send Approved Reply via Gmail` (SMTP) and `Monitor Gmail Inbox` (IMAP).
Set the SMTP nodes' **From** to `outreach@yourbrand.com`.

## 5. Mailspring (optional human inbox)
Add account → IMAP `mail.yourbrand.com:993` + SMTP `:465`, user `outreach@yourbrand.com`.
With a real Let's Encrypt cert there's no self-signed-cert friction. Sent + received both live in Stalwart → one unified view.

## 6. Cutover checklist
- [ ] `dig MX yourbrand.com` → points at `mail.yourbrand.com`
- [ ] Send test from Stalwart → external Gmail: lands in **inbox** (check spam first few)
- [ ] Reply from external → arrives in Stalwart INBOX (n8n picks it up)
- [ ] [mail-tester.com](https://www.mail-tester.com) score ≥ 9/10 (SPF/DKIM/DMARC all pass)
- [ ] Warm up: low volume first week, ramp gradually
- [ ] Bulk-set real influencers to `Cold lead` (cadence_admin / enrich scripts) and flip workflow **Active**

---

### Why the relay can't be configured locally
On `mail.local` (no real domain / no public IP / no MX) Gmail rejects direct sends as
*unauthenticated* (proven in testing), and replies can't route to a localhost server.
The relay + receiving only become real once steps 2–3 above exist. Until then, local
testing uses Gmail directly (your Gmail account) for send + receive.
