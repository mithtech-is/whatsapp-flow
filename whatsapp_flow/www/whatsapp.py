import frappe


def get_context(context):
    # The agent desk requires a logged-in user.
    if frappe.session.user == "Guest":
        frappe.local.flags.redirect_location = "/login?redirect-to=/whatsapp"
        raise frappe.Redirect

    context.no_cache = 1
    # The built index.html sets `window[key] = value` for each key in `boot`.
    # frappe-ui's frappeRequest reads window.csrf_token for POST requests.
    context.boot = {
        "csrf_token": frappe.sessions.get_csrf_token(),
        "user": frappe.session.user,
    }
    return context
