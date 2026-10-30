"""Runtime patch layer (§2.2).

Guarded monkeypatches on the chatbot engine — plain Python classes/functions, not DocTypes.
Each patch:
  * checks the target still exists and has the expected signature,
  * checks the installed app commit against the pin (compat/pinned.py),
  * on any mismatch, records a SKIPPED status and leaves upstream behaviour intact,
  * never raises out of apply() (hooks.py wraps it too).

Status is exposed via compat/health.py and surfaced on the WhatsApp Settings health page.

The four targets (plan §2.2):
  1. processor.process_incoming_message  -> enqueue on the `wa_bot` queue (async)       [Phase 0]
  2. flow_engine exec() -> frappe.utils.safe_exec                                        [Phase 0]
  3. ChatbotProcessor.process -> skip when a human owns the conversation (+graph dispatch) [Phase 0 / 3]
  4. AIResponder.build_context -> add External API context                              [Phase 3]
"""

from __future__ import annotations

import inspect

from whatsapp_flow.compat import pinned

WA_BOT_QUEUE = "wa_bot"

# patch_name -> {"status": "applied|skipped|error", "detail": str}
_STATUS: dict[str, dict] = {}
_APPLIED = False


def _record(name: str, status: str, detail: str = "") -> None:
    _STATUS[name] = {"status": status, "detail": detail}


def get_status() -> dict[str, dict]:
    """Snapshot of every patch's outcome (read by the health page)."""
    return dict(_STATUS)


def apply() -> None:
    """Apply all guarded patches. Idempotent; safe to call from every process."""
    global _APPLIED
    if _APPLIED:
        return
    _APPLIED = True

    _patch_async_processing()
    _patch_safe_exec()
    _patch_human_skip()
    _patch_build_context()


# ---------------------------------------------------------------------------
# 1. Async processing — move the chatbot off Meta's webhook request onto `wa_bot`.
# ---------------------------------------------------------------------------
def _patch_async_processing() -> None:
    name = "async_processing"
    try:
        if not pinned.commit_matches("frappe_whatsapp_chatbot"):
            return _record(name, "skipped", "pinned commit mismatch")

        from frappe_whatsapp_chatbot.chatbot import processor

        original = getattr(processor, "process_incoming_message", None)
        if original is None or getattr(original, "_wd_wrapped", False):
            return _record(name, "skipped", "target missing or already wrapped")

        sig = list(inspect.signature(original).parameters)
        if sig[:1] != ["doc"]:
            return _record(name, "skipped", f"unexpected signature: {sig}")

        def process_incoming_message_async(doc, method=None):
            # Cheap guards here so we never enqueue for outgoing/bot messages.
            # All heavier logic stays in the ORIGINAL, run in the worker (it logs
            # its own errors). We do NOT re-raise — the message save must not break.
            import frappe

            try:
                if getattr(doc, "type", None) != "Incoming":
                    return
                if getattr(doc.flags, "ignore_chatbot", False):
                    return
                frappe.enqueue(
                    "whatsapp_flow.compat.patches._run_original_processor",
                    queue=WA_BOT_QUEUE,
                    enqueue_after_commit=True,
                    job_id=f"wa_bot::{getattr(doc, 'name', '')}",
                    doc_name=getattr(doc, "name", None),
                )
            except Exception:
                frappe.log_error(frappe.get_traceback(), "whatsapp_flow: async enqueue failed")

        process_incoming_message_async._wd_wrapped = True  # type: ignore[attr-defined]
        process_incoming_message_async._wd_original = original  # type: ignore[attr-defined]
        processor.process_incoming_message = process_incoming_message_async
        _record(name, "applied")
    except Exception as e:  # pragma: no cover
        _record(name, "error", str(e))


def _run_original_processor(doc_name: str | None = None) -> None:
    """Worker entry point: reuse the upstream processor logic off-request.

    Note: the upstream in-process `_processing_messages` re-entrancy set does not span
    processes, so it no longer helps here. The real loop guards — `flags.ignore_chatbot`
    and `type != 'Incoming'` — are enforced by the upstream function itself and survive
    the enqueue boundary.
    """
    import frappe

    if not doc_name:
        return
    try:
        from frappe_whatsapp_chatbot.chatbot import processor

        original = getattr(processor.process_incoming_message, "_wd_original", None)
        if original is None:
            return
        doc = frappe.get_doc("WhatsApp Message", doc_name)
        original(doc)
    except frappe.DoesNotExistError:
        return
    except Exception:
        frappe.log_error(frappe.get_traceback(), "whatsapp_flow: wa_bot processing failed")


# ---------------------------------------------------------------------------
# 2. safe_exec — neutralise the raw exec() calls in the flow engine.
#    flow_engine.py uses the bare builtin `exec(...)`. Injecting a module-level
#    name `exec` shadows the builtin inside that module only, so both call sites
#    (run_script, run_response_script) route through safe_exec without us having
#    to reimplement their methods.
# ---------------------------------------------------------------------------
def _patch_safe_exec() -> None:
    name = "safe_exec"
    try:
        if not pinned.commit_matches("frappe_whatsapp_chatbot"):
            return _record(name, "skipped", "pinned commit mismatch")

        from frappe_whatsapp_chatbot.chatbot import flow_engine

        if getattr(flow_engine, "_wd_safe_exec", False):
            return _record(name, "skipped", "already applied")

        # Confirm the call sites still exist as expected.
        src = inspect.getsource(flow_engine)
        if "exec(" not in src:
            return _record(name, "skipped", "no exec() call site found")

        from frappe.utils.safe_exec import safe_exec

        def _guarded_exec(script, _globals=None, _locals=None):
            return safe_exec(script, _globals=_globals, _locals=_locals)

        flow_engine.exec = _guarded_exec  # shadows builtin within this module
        flow_engine._wd_safe_exec = True
        _record(name, "applied")
    except Exception as e:  # pragma: no cover
        _record(name, "error", str(e))


# ---------------------------------------------------------------------------
# 3. Human-skip — the bot must not reply while a human owns the conversation.
#    (Graph-mode dispatch is layered on in Phase 3.)
# ---------------------------------------------------------------------------
def _patch_human_skip() -> None:
    name = "human_skip"
    try:
        if not pinned.commit_matches("frappe_whatsapp_chatbot"):
            return _record(name, "skipped", "pinned commit mismatch")

        from frappe_whatsapp_chatbot.chatbot.processor import ChatbotProcessor

        original = ChatbotProcessor.process
        if getattr(original, "_wd_wrapped", False):
            return _record(name, "skipped", "already wrapped")

        sig = list(inspect.signature(original).parameters)
        if sig != ["self"]:
            return _record(name, "skipped", f"unexpected signature: {sig}")

        def process(self):
            import frappe

            try:
                from_number = (self.message_data or {}).get("from")
                if from_number:
                    contact = frappe.db.get_value(
                        "WhatsApp Contact",
                        {"mobile_no": from_number},
                        ["name", "wd_bot_active"],
                        as_dict=True,
                    )
                    # bot_active explicitly 0 => a human owns it => skip the bot.
                    if contact and contact.get("wd_bot_active") == 0:
                        return
            except Exception:
                # Never let the guard itself break processing — fall through to upstream.
                pass
            # Graph-mode dispatch: if a Graph flow handles this message, skip the step engine.
            try:
                from whatsapp_flow.wa_bot.graph_runner import maybe_run_graph

                if maybe_run_graph(self.message_data):
                    return
            except Exception:
                pass
            return original(self)

        process._wd_wrapped = True  # type: ignore[attr-defined]
        ChatbotProcessor.process = process
        _record(name, "applied")
    except Exception as e:  # pragma: no cover
        _record(name, "error", str(e))


# ---------------------------------------------------------------------------
# 4. build_context — add the "External API" AI context type (#14/#16).
# ---------------------------------------------------------------------------
def _patch_build_context() -> None:
    name = "build_context"
    try:
        if not pinned.commit_matches("frappe_whatsapp_chatbot"):
            return _record(name, "skipped", "pinned commit mismatch")

        from frappe_whatsapp_chatbot.chatbot.ai_responder import AIResponder

        original = AIResponder.build_context
        if getattr(original, "_wd_wrapped", False):
            return _record(name, "skipped", "already wrapped")

        def build_context(self):
            ctx = original(self) or ""
            try:
                from whatsapp_flow.wa_bot.ai_context import external_api_context

                extra = external_api_context(getattr(self, "phone_number", None))
                if extra:
                    ctx = f"{ctx}\n\n{extra}" if ctx else extra
            except Exception:
                import frappe

                frappe.log_error(frappe.get_traceback(), "whatsapp_flow: external api context failed")
            return ctx

        build_context._wd_wrapped = True  # type: ignore[attr-defined]
        AIResponder.build_context = build_context
        _record(name, "applied")
    except Exception as e:  # pragma: no cover
        _record(name, "error", str(e))
