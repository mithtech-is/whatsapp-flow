# Installing WhatsApp Flow

WhatsApp Flow is an **add-on**. It needs three other WhatsApp apps installed first,
then it adds the flow builder and desk on top. This guide walks through it step by step.

---

## Before you start

You need a working **Frappe + ERPNext** site (Frappe v15 or v16, Python 3.10+).

You'll install **four apps in this order**:

1. `frappe_whatsapp`
2. `whatsapp_chat`
3. `frappe_whatsapp_chatbot`
4. `whatsapp_flow`  ← this app, last

> **Tip:** Use the tested versions of the three WhatsApp apps (commit hashes in
> [`whatsapp_flow/compat/pinned.py`](whatsapp_flow/compat/pinned.py)). Newer versions
> *may* work — the app checks and falls back safely — but the pinned ones are proven.

No Node.js needed: the app ships with its screens already built in.

---

## Step 1 — Get the apps

```bash
bench get-app frappe_whatsapp <url>
bench get-app whatsapp_chat <url>
bench get-app frappe_whatsapp_chatbot <url>
bench get-app whatsapp_flow <url>
```

## Step 2 — Install them on your site

```bash
bench --site yoursite install-app frappe_whatsapp whatsapp_chat frappe_whatsapp_chatbot
bench --site yoursite install-app whatsapp_flow
bench --site yoursite migrate
```

That's it — the app sets up its fields, roles, SLA, analytics, and screens automatically.

## Step 3 — Turn on the chatbot worker *(required for flows to run)*

Flows run as background jobs on a queue called **`wa_bot`**. Your background worker
must listen to it, or flows will never execute.

- **Local/dev:** `bench worker --queue wa_bot,long,default,short`
- **Production (supervisor/docker):** add `wa_bot` to a worker's `--queue` list,
  e.g. `--queue long,default,short,wa_bot`, and restart it.

---

## Connect your WhatsApp number

This is done in the **WhatsApp apps' settings in Frappe Desk** (not in WhatsApp Flow —
the three apps own the connection). From Meta you'll need:

| You need | Where to get it |
|----------|-----------------|
| Phone number ID + Access token | Meta → your app → **WhatsApp → API Setup** |
| WhatsApp Business account ID + App ID | same page |
| A **public HTTPS web address** | your server/domain (Meta can't reach `localhost`) |

Then set the **webhook** in Meta → WhatsApp → Configuration to:

```
https://yoursite/api/method/frappe_whatsapp.utils.webhook.webhook
```

and use the same **Verify Token** on both sides.

---

## Use it

Open **`https://yoursite/whatsapp`** and log in.

Screens: **Flows · Inbox · Campaigns · Calls · Templates · Analytics · Settings**.

Start in **Flows** to draw a chatbot, use **Simulate** to test it, then **Publish**.

---

## Optional

- **Encrypted WhatsApp Flows (forms):** add your private key in
  *Settings → Retention & Ops → WhatsApp Flows private key*.
- **Voice/calling:** turn on *Settings → Retention & Ops → Enable Voice*. Call logs and
  IVR design work; **real phone audio** also needs Meta Calling API access + a media server.

---

## Going to production — quick checklist

- [ ] The three WhatsApp apps installed **before** `whatsapp_flow`
- [ ] `wa_bot` added to a worker queue (Step 3)
- [ ] WhatsApp number connected + public HTTPS webhook verified
- [ ] `bench --site yoursite migrate` ran with no errors
- [ ] Don't disable CSRF — the app handles it correctly on its own
- [ ] Remove any demo/sample data if you loaded it

---

## (Developers only) Rebuilding the screens

Not needed for a normal install — the built screens ship in the repo. Only if you change
the frontend:

```bash
cd apps/whatsapp_flow/frontend
yarn install
yarn build
```
> Build on the **same OS** your Node runs on — a `node_modules` built on Windows won't
> run on Linux/WSL (and vice-versa).
