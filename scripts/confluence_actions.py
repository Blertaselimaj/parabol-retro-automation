
Confluence actions · PY
#!/usr/bin/env python3
"""
Posts a joint retro's action items (Parabol "tasks" created during the meeting)
onto a Confluence page, as a new dated section appended below whatever was
there before -- so the page builds a running history across cycles rather than
being overwritten each time.
 
Used by run_joint_cycle.py the day after each joint retro meeting. Requires
two extra secrets beyond PARABOL_TOKEN: CONFLUENCE_EMAIL (the Atlassian login
email) and CONFLUENCE_API_TOKEN (an API token generated from
id.atlassian.com/manage-profile/security/api-tokens).
"""
import base64
import html
import json
import os
import sys
import urllib.error
import urllib.request
 
sys.path.insert(0, os.path.dirname(__file__))
from parabol_retro_automation import gql  # noqa: E402
 
CONFLUENCE_SITE = "oprime.atlassian.net"
CONFLUENCE_PAGE_ID = "4511957005"  # "Joined Retro's LDTE and PRT", space PRI
 
STATUS_LABELS = {
    "active": "In progress",
    "stuck": "Blocked / needs attention",
    "done": "Done",
    "future": "Planned for later",
}
 
 
def _confluence_request(email, api_token, method, path, body=None):
    url = f"https://{CONFLUENCE_SITE}/wiki/api/v2{path}"
    auth = base64.b64encode(f"{email}:{api_token}".encode("utf-8")).decode("ascii")
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(
            f"HTTP error {e.code} calling Confluence API ({method} {path}): "
            f"{e.read().decode('utf-8', 'ignore')}"
        )
 
 
def fetch_meeting_tasks(parabol_token, meeting_id):
    data = gql(parabol_token, """
        query($meetingId: ID!) {
          viewer {
            meeting(meetingId: $meetingId) {
              ... on RetrospectiveMeeting {
                tasks {
                  id
                  title
                  plaintextContent
                  status
                  dueDate
                  user { preferredName }
                }
              }
            }
          }
        }
    """, {"meetingId": meeting_id})
    meeting = data["viewer"]["meeting"]
    if not meeting:
        return []
    return meeting.get("tasks") or []
 
 
def build_section_html(joint_date, tasks):
    date_label = joint_date.strftime("%B %-d, %Y") if hasattr(joint_date, "strftime") else str(joint_date)
    parts = [f"<h2>Action Items — {html.escape(date_label)}</h2>"]
    if not tasks:
        parts.append("<p>No action items were recorded for this retro.</p>")
        return "".join(parts)
    parts.append(
        "<table><thead><tr>"
        "<th>Action Item</th><th>Assigned To</th><th>Status</th>"
        "</tr></thead><tbody>"
    )
    for t in tasks:
        title = html.escape((t.get("plaintextContent") or t.get("title") or "").strip() or "(no content)")
        assignee = html.escape(t["user"]["preferredName"]) if t.get("user") else "Unassigned"
        status = html.escape(STATUS_LABELS.get(t.get("status"), t.get("status") or "unknown"))
        parts.append(f"<tr><td>{title}</td><td>{assignee}</td><td>{status}</td></tr>")
    parts.append("</tbody></table>")
    return "".join(parts)
 
 
def post_action_items(parabol_token, confluence_email, confluence_api_token, meeting_id, joint_date):
    tasks = fetch_meeting_tasks(parabol_token, meeting_id)
    print(f"Found {len(tasks)} action item(s) in Parabol for meeting {meeting_id}.")
 
    page = _confluence_request(
        confluence_email, confluence_api_token, "GET",
        f"/pages/{CONFLUENCE_PAGE_ID}?body-format=storage",
    )
    current_body = page.get("body", {}).get("storage", {}).get("value", "") or ""
    current_version = page["version"]["number"]
    title = page["title"]
 
    new_section = build_section_html(joint_date, tasks)
    updated_body = current_body + new_section
 
    _confluence_request(
        confluence_email, confluence_api_token, "PUT",
        f"/pages/{CONFLUENCE_PAGE_ID}",
        {
            "id": CONFLUENCE_PAGE_ID,
            "status": "current",
            "title": title,
            "body": {"representation": "storage", "value": updated_body},
            "version": {"number": current_version + 1, "message": f"Action items for {joint_date}"},
        },
    )
    print(f"Updated Confluence page {CONFLUENCE_PAGE_ID} (now version {current_version + 1}).")
 

