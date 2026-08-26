
Run joint cycle · PY
#!/usr/bin/env python3
"""
Runs on a daily schedule via GitHub Actions (see .github/workflows/quarterly-retro.yml).
 
Each run, it checks whether TODAY is the trigger date for the next joint retro
cycle (2 days before that cycle's reflection deadline). If it is, and this
cycle hasn't already been handled, it:
  1. Closes any stale/leftover active meeting for the retro template.
  2. Starts a fresh meeting for this cycle.
  3. Writes the result (invite link, topics, deadline) to state/latest.json
     and commits it back to the repo.
 
A separate scheduled task (running in Claude, not here) reads that state file
afterward and builds/sends the team survey email. This script's only job is
the Parabol side — starting/closing meetings — since that requires a real
internet connection that only a runner like this (not a chat sandbox) has.
 
On every other day, this script does nothing and exits quietly. It's safe
to run daily indefinitely; it does not need to be updated for future cycles.
"""
import json
import os
import sys
from datetime import date, timedelta
 
sys.path.insert(0, os.path.dirname(__file__))
from parabol_retro_automation import (  # noqa: E402
    DEFAULT_TEAM_NAME,
    DEFAULT_TEMPLATE_NAME,
    close_meeting,
    find_active_meeting,
    find_team,
    find_team_member_by_email,
    find_template,
    promote_facilitator,
    start_meeting,
)
 
# The underlying "Retrospective Data team" meeting happens every ~4 weeks on
# Thursday (confirmed against the actual recurring calendar series); every
# 3rd occurrence of that series is the joint retro (12 weeks apart), and the
# other two in between are the separate team-only retros this automation does
# NOT handle.
#
# The very first joint retro (Sept 8, 2026) was a one-off exception moved off
# the regular Thursday slot to a Tuesday, so it doesn't sit on the 12-week
# Thursday cadence that follows. From the NEXT joint retro onward (Dec 3,
# 2026, a Thursday -- confirmed on the calendar as the 3rd occurrence after
# Sept 8), the cadence is a clean 84 days (12 weeks) apart. So this uses two
# anchors: the one-off first date, then a regular anchor the 84-day math
# runs from after that.
FIRST_JOINT_DATE = date(2026, 9, 8)
REGULAR_JOINT_ANCHOR = date(2026, 12, 3)
JOINT_CYCLE_DAYS = 84  # 12 weeks
 
# Facilitator rotation: Tim goes first (the Sept 8, 2026 cycle), then Marijn,
# alternating every cycle after that -- continuing straight through the
# one-off date adjustment above. Facilitator = per-meeting control over
# advancing stages/ending the meeting in Parabol -- separate from Parabol's
# team-level "Team Lead" flag. See SKILL.md for the full explanation.
FACILITATOR_ROTATION = [
    "timvanhouten@prime-rts.com",
    "marijnbruggeman@prime-rts.com",
]
 
STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "state", "latest.json")
 
 
def next_joint_date(today):
    if today <= FIRST_JOINT_DATE:
        return FIRST_JOINT_DATE
    if today <= REGULAR_JOINT_ANCHOR:
        return REGULAR_JOINT_ANCHOR
    days_since_anchor = (today - REGULAR_JOINT_ANCHOR).days
    cycles_passed = days_since_anchor // JOINT_CYCLE_DAYS
    candidate = REGULAR_JOINT_ANCHOR + timedelta(days=cycles_passed * JOINT_CYCLE_DAYS)
    while candidate < today:
        candidate += timedelta(days=JOINT_CYCLE_DAYS)
    return candidate
 
 
def cycle_index(joint_date):
    """0 for the one-off Sept 8, 2026 date; 1 for the first regularly-cadenced
    joint retro (Dec 3, 2026); 2, 3, ... for each 84-day cycle after that."""
    if joint_date <= FIRST_JOINT_DATE:
        return 0
    return 1 + round((joint_date - REGULAR_JOINT_ANCHOR).days / JOINT_CYCLE_DAYS)
 
 
def facilitator_for(joint_date):
    """Which rotation slot is due for a given joint retro date. Cycle 0 (the
    Sept 8, 2026 one-off date) gets FACILITATOR_ROTATION[0] (Tim); every
    cycle after that alternates, continuing straight through the switch from
    the one-off date to the regular 84-day cadence."""
    return FACILITATOR_ROTATION[cycle_index(joint_date) % len(FACILITATOR_ROTATION)]
 
 
def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return {}
 
 
def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w") as f:
        json.dump(state, f, indent=2)
        f.write("\n")
 
 
def main():
    token = os.environ.get("PARABOL_TOKEN")
    if not token:
        raise SystemExit("PARABOL_TOKEN secret is not set for this workflow.")
 
    today = date.today()
    joint_date = next_joint_date(today)
    deadline = joint_date - timedelta(days=1)
    trigger_date = deadline - timedelta(days=2)
 
    print(f"Today: {today}. Next joint retro: {joint_date}. Deadline: {deadline}. Trigger date: {trigger_date}.")
 
    if today != trigger_date:
        print("Not the trigger date yet -- nothing to do today.")
        return
 
    state = load_state()
    if state.get("cycle_date") == str(joint_date):
        print("This cycle has already been started -- nothing to do.")
        return
 
    team = find_team(token, DEFAULT_TEAM_NAME)
    template = find_template(token, team["id"], DEFAULT_TEMPLATE_NAME)
 
    active = find_active_meeting(token, team["id"], template["id"])
    if active:
        print(f"Closing stale active meeting id={active['id']}")
        close_meeting(token, active["id"])
 
    meeting_id = start_meeting(token, team["id"], template["id"], f"Joint Quarterly Retro - {joint_date}")
    invite_link = f"https://action.parabol.co/meet/{meeting_id}"
    print(f"Started new meeting for {joint_date}: {invite_link}")
 
    # Assign this cycle's facilitator (rotates Tim -> Marijn -> Tim -> ...).
    # This only controls who can advance stages/end the meeting in Parabol --
    # it does not affect who can add reflections (everyone still can).
    facilitator_email = facilitator_for(joint_date)
    print(f"This cycle's facilitator (by rotation): {facilitator_email}")
    facilitator_assigned = False
    facilitator_note = None
    match = find_team_member_by_email(token, team["id"], facilitator_email)
    if not match:
        facilitator_note = (
            f"{facilitator_email} has not accepted their Parabol team invite yet -- "
            f"facilitator NOT set. Have them accept the invite, then re-run this "
            f"workflow manually (Actions tab -> Run workflow) or set the facilitator "
            f"by hand in Parabol for this meeting."
        )
        print(f"  ! {facilitator_note}")
    else:
        promote_facilitator(token, meeting_id, match["userId"])
        facilitator_assigned = True
 
    new_state = {
        "cycle_date": str(joint_date),
        "deadline_local": f"{deadline}T12:00:00+02:00",
        "meeting_id": meeting_id,
        "invite_link": invite_link,
        "topics": [p["question"] for p in template["prompts"]],
        "team_name": team["name"],
        "template_name": template["name"],
        "facilitator_email": facilitator_email,
        "facilitator_assigned": facilitator_assigned,
        "facilitator_note": facilitator_note,
    }
    save_state(new_state)
 
 
if __name__ == "__main__":
    main()
 

Unable to open file.
