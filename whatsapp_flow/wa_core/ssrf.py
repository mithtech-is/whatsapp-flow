"""Basic SSRF guard for outbound webhooks / custom actions (#66).

Blocks requests to loopback, private, link-local and reserved address space. Resolves the
hostname and checks every resolved address. Not a substitute for an allowlist in high-risk
deployments, but stops the common SSRF pivots.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import frappe
from frappe import _


def validate(url: str) -> None:
    if not url:
        frappe.throw(_("Empty URL."))
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        frappe.throw(_("Only http/https URLs are allowed."))
    host = parsed.hostname
    if not host:
        frappe.throw(_("URL has no host."))
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
    except Exception:
        frappe.throw(_("Could not resolve host {0}").format(host))
    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if (
            ip.is_loopback or ip.is_private or ip.is_link_local
            or ip.is_multicast or ip.is_reserved or ip.is_unspecified
        ):
            frappe.throw(_("Refusing to call a private/reserved address: {0}").format(addr))
