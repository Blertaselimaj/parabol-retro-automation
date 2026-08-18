#!/usr/bin/env python3
"""
Parabol Quarterly Retro automation.
What this does, end to end:
  1. Authenticates to Parabol's public GraphQL API with a Personal Access Token (PAT).
  2. Finds your team ("Team Clean Code or Bust" by default) and its retro templates.
  3. Checks whether a "Quarterly Team Retro" activity is already running this cycle
     (a resumable meeting) -- if so, uses it; if not, starts a new one from the template.
  4. Reads collected reflections from an external CSV (your export from whatever form
     tool you use to collect answers before the deadline) and pushes each one into the
     matching topic column in Parabol via the createReflection mutation.
  5. Prints the meeting's invite link (https://action.parabol.co/meet/<meetingId>).
IMPORTANT LIMITATION -- read before using for real (see README.md "Attribution caveat"):
  Every reflection created through this script's API calls is attributed, on Parabol's
  side, to the user who owns the Personal Access Token -- NOT to the person named in the
  CSV row. Parabol has no API concept of "create this reflection as if user X wrote it."
  This script works around that by prefixing each reflection's text with the person's
  name (e.g. "Alex Popescu: ..."), so names are visible in the content, but they will not
  show up as Parabol's native "authored by" avatar/identity the way a real non-anonymous
  submission would. Decide if that's acceptable before relying on this for a non-anonymous
  survey (see README.md).
Setup required before running (see README.md for full details):
  - Generate a Parabol Personal Access Token (from your Parabol profile settings) and
    grant it access to this team, with MEETINGS_READ and MEETINGS_WRITE scopes.
  - Set it as the PARABOL_TOKEN environment variable (never hardcode it in this file).
  - Have a CSV of collected responses with columns: name, topic, comment
    (topic must match one of the template's prompt questions/categories exactly).
Usage:
  # Step 1 -- discovery only. Confirms team id, lists templates (this also resolves
  # whether "Quarterly Team Retro" actually exists under that name), lists prompts,
  # and reports any already-active meeting. Makes NO changes in Parabol.
  PARABOL_TOKEN=pat_xxx python3 parabol_retro_automation.py --discover
  # Step 2 -- once discovery looks right, actually start/resume the meeting and push
  # reflections from a responses CSV.
  PARABOL_TOKEN=pat_xxx python3 parabol_retro_automation.py --run --responses responses.csv
"""
import argparse
import csv
import json
import os
import sys
import urllib.request
import urllib.error
GRAPHQL_URL = "https://action.parabol.co/graphql"
DEFAULT_TEAM_NAME = "Team Clean Code or Bust"
DEFAULT_TEMPLATE_NAME = "Quarterly Team Retro"
def gql(token, query, variables=None):
    """Send a GraphQL request to Parabol and return the `data` object, or raise on error."""
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise SystemExit(f"HTTP error {e.code} calling Parabol API: {e.read().decode('utf-8', 'ignore')}")
    if body.get("errors"):
        raise SystemExit(f"Parabol API returned errors: {json.dumps(body['errors'], indent=2)}")
    return body["data"]
def find_team(token, team_name):
    data = gql(token, """
        query {
          viewer {
            teams { id name }
          }
        }
    """)
    teams = data["viewer"]["teams"]
    wanted = team_name.strip().lower()
    for t in teams:
        actual = t["name"].strip().lower()
        if actual == wanted or wanted in actual:
            return t
    print(f"Could not find a team named '{team_name}'. Teams visible to this token:")
    for t in teams:
        print(f"  - {t['name']}  (id={t['id']})")
    raise SystemExit(1)
def find_template(token, team_id, template_name):
    data = gql(token, """
        query($teamId: ID!) {
          viewer {
            team(teamId: $teamId) {
              meetingSettings(meetingType: retrospective) {
                ... on RetrospectiveMeetingSettings {
                  teamTemplates { id name prompts { id question } }
                  reflectTemplates { id name prompts { id question } }
                }
              }
            }
          }
        }
    """, {"teamId": team_id})
    settings = data["viewer"]["team"]["meetingSettings"]
    all_templates = {t["id"]: t for t in settings["teamTemplates"] + settings["reflectTemplates"]}.values()
    wanted = template_name.strip().lower()
    for t in all_templates:
        actual = t["name"].strip().lower()
        if actual == wanted or wanted in actual:
            return t
    print(f"Could not find a retro template named '{template_name}' on this team.")
    print("Templates actually available to this team:")
    for t in all_templates:
        print(f"  - {t['name']}  (id={t['id']})")
    print("\nThis matches the issue already flagged in the quarterly reminder checklist --")
    print("resolve the template name/creation question with the team before automating further.")
    raise SystemExit(1)
def find_active_meeting(token, team_id, template_id):
    data = gql(token, """
        query($teamId: ID!) {
          viewer {
            team(teamId: $teamId) {
              activeMeetings {
                id
                name
                ... on RetrospectiveMeeting { templateId }
              }
            }
          }
        }
    """, {"teamId": team_id})
    for m in data["viewer"]["team"]["activeMeetings"]:
        if m.get("templateId") == template_id:
            return m
    return None
def start_meeting(token, team_id, template_id, meeting_name):
    select_data = gql(token, """
        mutation($templateId: ID!, $teamId: ID!) {
          selectTemplate(selectedTemplateId: $templateId, teamId: $teamId) {
            error { message }
          }
        }
    """, {"templateId": template_id, "teamId": team_id})
    select_error = select_data["selectTemplate"].get("error")
    if select_error:
        raise SystemExit(f"selectTemplate failed: {select_error['message']}")
    data = gql(token, """
        mutation($teamId: ID!, $name: String) {
          startRetrospective(teamId: $teamId, name: $name) {
            ... on StartRetrospectiveSuccess { meetingId }
            ... on ErrorPayload { error { message } }
          }
        }
    """, {"teamId": team_id, "name": meeting_name})
    result = data["startRetrospective"]
    if "error" in result and result.get("error"):
        raise SystemExit(f"startRetrospective failed: {result['error']['message']}")
    return result["meetingId"]
def tiptap_doc(text):
    """Wrap plain text in the minimal TipTap JSON document shape Parabol expects."""
    return json.dumps({
        "type": "doc",
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
    })
def push_reflection(token, meeting_id, prompt_id, text):
    data = gql(token, """
        mutation($meetingId: ID!, $promptId: ID!, $content: String) {
          createReflection(input: {meetingId: $meetingId, promptId: $promptId, content: $content}) {
            error { message }
            reflectionId
          }
        }
    """, {"meetingId": meeting_id, "promptId": prompt_id, "content": tiptap_doc(text)})
    result = data["createReflection"]
    if result.get("error"):
        print(f"  ! failed: {result['error']['message']}")
        return False
    return True
def close_meeting(token, meeting_id):
    data = gql(token, """
        mutation($meetingId: ID!) {
          endRetrospective(meetingId: $meetingId) {
            ... on ErrorPayload { error { message } }
            ... on EndRetrospectiveSuccess { meeting { id } }
          }
        }
    """, {"meetingId": meeting_id})
    result = data["endRetrospective"]
    if result.get("error"):
        raise SystemExit(f"endRetrospective failed: {result['error']['message']}")
    print(f"Closed meeting id={meeting_id}")
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--team", default=DEFAULT_TEAM_NAME)
    ap.add_argument("--template", default=DEFAULT_TEMPLATE_NAME)
    ap.add_argument("--meeting-name", default=None, help="Name for a newly started meeting (optional)")
    ap.add_argument("--responses", help="CSV file with columns: name, topic, comment")
    ap.add_argument("--close-meeting", metavar="MEETING_ID", help="End/close an existing (e.g. stale) meeting by id before doing anything else")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--discover", action="store_true", help="Read-only: report team/template/active-meeting state, make no changes")
    mode.add_argument("--run", action="store_true", help="Start/resume the meeting and push reflections from --responses")
    args = ap.parse_args()
    token = os.environ.get("PARABOL_TOKEN")
    if not token:
        raise SystemExit("Set the PARABOL_TOKEN environment variable to your Parabol personal access token.")
    if args.close_meeting:
        close_meeting(token, args.close_meeting)
    team = find_team(token, args.team)
    print(f"Team: {team['name']} (id={team['id']})")
    template = find_template(token, team["id"], args.template)
    print(f"Template: {template['name']} (id={template['id']})")
    print("Prompts/topics on this template:")
    prompt_by_topic = {}
    for p in template["prompts"]:
        print(f"  - {p['question']}  (id={p['id']})")
        prompt_by_topic[p["question"].strip().lower()] = p["id"]
    active = find_active_meeting(token, team["id"], template["id"])
    if active:
        print(f"Active meeting already running this cycle: {active['name']} (id={active['id']})")
    else:
        print("No active meeting for this template right now.")
    if args.discover:
        print("\nDiscovery complete -- no changes made.")
        return
    # --run mode
    if active:
        meeting_id = active["id"]
        print(f"Resuming meeting id={meeting_id}")
    else:
        meeting_id = start_meeting(token, team["id"], template["id"], args.meeting_name)
        print(f"Started new meeting id={meeting_id}")
    invite_link = f"https://action.parabol.co/meet/{meeting_id}"
    print(f"Invite link: {invite_link}")
    if args.responses:
        if not os.path.exists(args.responses):
            raise SystemExit(f"Responses file not found: {args.responses}")
        pushed, skipped = 0, 0
        with open(args.responses, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = (row.get("name") or "").strip()
                topic = (row.get("topic") or "").strip()
                comment = (row.get("comment") or "").strip()
                if not (name and topic and comment):
                    print(f"  skipping incomplete row: {row}")
                    skipped += 1
                    continue
                prompt_id = prompt_by_topic.get(topic.strip().lower())
                if not prompt_id:
                    print(f"  ! no matching topic/prompt for '{topic}' (row for {name}) -- skipped")
                    skipped += 1
                    continue
                # NOTE: name is prefixed into the text itself -- see the attribution
                # caveat at the top of this file and in README.md. All reflections are
                # actually owned, on Parabol's side, by the PARABOL_TOKEN's user.
                text = f"{name}: {comment}"
                ok = push_reflection(token, meeting_id, prompt_id, text)
                if ok:
                    pushed += 1
                else:
                    skipped += 1
        print(f"\nPushed {pushed} reflection(s), skipped {skipped}.")
    print(f"\nFinal invite link for the meeting: {invite_link}")
if __name__ == "__main__":
    main()
