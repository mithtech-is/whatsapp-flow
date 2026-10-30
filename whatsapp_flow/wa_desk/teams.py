"""Teams (native Frappe User Group) + agent presence (native User fields).

Native-first: a WA team IS a `User Group`; its members are `User Group Member` rows; agent
availability/capacity are the `wd_wa_availability` / `wd_wa_capacity` fields on `User`.

We keep a per-team **Assignment Rule** as stored strategy/config, but it is created DISABLED:
we do the actual assignment ourselves (assignment.py) so we never auto-assign unrelated Issues
on the site. The rule's user list is kept in sync with the team's online agents.
"""

from __future__ import annotations

import frappe


def team_rule_name(team: str) -> str:
    return f"WA Team: {team}"


def members(team: str) -> list[str]:
    if not team or not frappe.db.exists("User Group", team):
        return []
    return frappe.get_all("User Group Member", filters={"parent": team}, pluck="user")


def online_agents(team: str) -> list[str]:
    """Members whose WhatsApp availability is Online, enabled users only."""
    out = []
    for u in members(team):
        row = frappe.db.get_value("User", u, ["enabled", "wd_wa_availability"], as_dict=True)
        if row and row.enabled and row.wd_wa_availability == "Online":
            out.append(u)
    return out


def open_load(user: str) -> int:
    """Number of open conversation ToDos assigned to a user (for load balancing)."""
    return frappe.db.count(
        "ToDo", {"allocated_to": user, "reference_type": "Issue", "status": "Open"}
    )


def pick_agent(team: str) -> str | None:
    """Least-loaded online agent, honouring wd_wa_capacity (0/None = unlimited)."""
    candidates = online_agents(team)
    if not candidates:
        return None
    best, best_load = None, None
    for u in candidates:
        load = open_load(u)
        cap = frappe.db.get_value("User", u, "wd_wa_capacity") or 0
        if cap and load >= cap:
            continue  # at capacity
        if best_load is None or load < best_load:
            best, best_load = u, load
    return best


def ensure_team_assignment_rule(team: str) -> str | None:
    """Create (disabled) Assignment Rule config for a team, and sync its users. Idempotent."""
    if not frappe.db.exists("User Group", team):
        return None
    name = team_rule_name(team)
    if frappe.db.exists("Assignment Rule", name):
        rule = frappe.get_doc("Assignment Rule", name)
    else:
        rule = frappe.new_doc("Assignment Rule")
        rule.name = name
        rule.document_type = "Issue"
        rule.disabled = 1  # config only — we assign ourselves
        rule.rule = "Load Balancing"
        rule.assign_condition = "status == 'Open'"
        rule.priority = 0
        # assignment days are mandatory on the rule
        for d in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"):
            rule.append("assignment_days", {"day": d})
    _sync_rule_users(rule, team)
    rule.flags.ignore_permissions = True
    rule.save()
    return rule.name


def _sync_rule_users(rule, team: str) -> None:
    rule.set("users", [])
    for u in online_agents(team):
        rule.append("users", {"user": u})


def sync_team(team: str) -> None:
    """Re-sync a team's rule user list from its current online agents."""
    if frappe.db.exists("Assignment Rule", team_rule_name(team)):
        ensure_team_assignment_rule(team)
