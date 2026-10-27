# whatsapp_desk

A **native-first** Frappe add-on that turns the three upstream WhatsApp apps into a full agent
desk: scoped inbox, teams & assignment, SLA, campaigns, a visual chatbot **flow builder**,
analytics, platform tooling and (later) voice.

> **Add-on, not a fork.** `whatsapp_desk` requires and *extends* three existing apps —
> `frappe_whatsapp`, `whatsapp_chat`, `frappe_whatsapp_chatbot` — plus Frappe & ERPNext core.
> Nothing is replaced or migrated. Whatomate is a **feature reference only** (AGPL-3.0; its code
> is never copied).

See [`whatsapp_desk-plan.md`](whatsapp_desk-plan.md) for the architecture & roadmap and
[`flow-builder-spec.md`](flow-builder-spec.md) for the visual flow builder.

## Native-first

Wherever Frappe/ERPNext or the three apps already provide something, `whatsapp_desk` reuses it
instead of adding a DocType:

| Concept | Backed by |
|---|---|
| Conversation / support episode | ERPNext **Issue** (native SLA) |
| Teams | Frappe **User Group** |
| Agent presence | Custom fields on **User** |
| Settings | existing **WhatsApp Settings** Single |
| Call records | **Call Log** |

## Install order

1. `frappe_whatsapp`
2. `whatsapp_chat`
3. `frappe_whatsapp_chatbot`
4. `whatsapp_desk`

```bash
bench get-app frappe_whatsapp
bench get-app whatsapp_chat
bench get-app frappe_whatsapp_chatbot
bench get-app whatsapp_desk /path/to/whatsapp_desk
bench --site <site> install-app whatsapp_desk
```

## Made by MithTech

whatsapp_desk is built and maintained by [MithTech](https://mith.tech), Frappe specialists in Bengaluru.
For WhatsApp on ERPNext set up and run for you, see [WhatsApp and ERPNext integration](https://mith.tech/services/integrations/whatsapp-erpnext).

## License

MIT (see `license.txt`).
