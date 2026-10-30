# WhatsApp Flow

**Build WhatsApp chatbots by drawing them — no coding.**

WhatsApp Flow adds a visual, drag‑and‑drop builder to your Frappe/ERPNext site so
you can design what your WhatsApp number says and does automatically. You draw a
flowchart — "if the customer says X, reply Y, then ask Z" — and it runs live.

---

## What you can do

- 🧩 **Draw chatbot flows** on a canvas: welcome messages, questions, buttons,
  conditions, call an API, hand off to a human — all as connected boxes.
- ▶️ **Test before you go live** with the built‑in simulator.
- 💬 **Agent inbox** — staff reply to real customer chats, with assignment,
  canned replies, notes, and tags.
- ⏱️ **Response targets (SLA)** — track how fast conversations get answered.
- 📣 **Campaigns & templates** — send approved template messages to lists of people.
- 📊 **Analytics** — see message volume, open chats, and campaign results.
- 📞 **Call logs & voice menus (IVR)** — built from the same flow canvas.

---

## How it fits in

WhatsApp Flow is an **add‑on**. It sits on top of three existing WhatsApp apps and
makes them easier to use — it doesn't replace them:

```
          WhatsApp Flow   ← the visual flow builder + desk (this app)
                │
  frappe_whatsapp · whatsapp_chat · frappe_whatsapp_chatbot   ← send/receive, templates, chat
                │
            Frappe / ERPNext   ← the platform underneath
```

Those three apps handle **connecting your WhatsApp number and sending messages**.
WhatsApp Flow adds the **visual builder and the agent tools** around them.

---

## Install

Install the three WhatsApp apps first, then this one:

```bash
bench get-app frappe_whatsapp
bench get-app whatsapp_chat
bench get-app frappe_whatsapp_chatbot
bench get-app whatsapp_flow <repo-url>

bench --site yoursite install-app whatsapp_flow
bench --site yoursite migrate
```

Then open **`https://yoursite/whatsapp`** and log in.

> Full step‑by‑step setup (connecting your WhatsApp number, the chatbot worker
> queue, etc.) is in **[INSTALL.md](INSTALL.md)**.

---

## What you need to actually send messages

The builder, simulator, and desk work right away. To send/receive **real** WhatsApp
messages you also need, from Meta:

- a **WhatsApp Business account** + phone number,
- an **access token** and **phone number ID**, and
- a **public web address (HTTPS)** so Meta can deliver incoming messages.

You enter these in the WhatsApp apps' settings (Frappe Desk).

---

## License

MIT — see [`license.txt`](license.txt). *(Whatomate is only a design reference; none of its code is used.)*
