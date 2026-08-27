

Readme · MD
Parabol joint-retro automation
This repo automatically starts each new joint-retro cycle's Parabol meeting on schedule -- no one needs to click anything in Parabol to start it.

What it does
Once a day, a GitHub Action checks two things:

Whether today is 2 days before the next joint retro's reflection deadline. On that day only, it closes any leftover/stale meeting for the "Quarterly Team Retro" template, starts a new meeting for this cycle, assigns that cycle's facilitator, and writes the invite link, topics, and deadline to state/latest.json (committed back to this repo).
Whether today is the day after the most recently started cycle's meeting date, and that cycle's action items haven't been posted to Confluence yet. If so, it reads the action items ("tasks") recorded in Parabol for that meeting and appends them as a new dated section on the team's Confluence action-items page -- so the page builds a running history across cycles.
Claude then reads state/latest.json on its own schedule and sends the team survey email -- that part isn't in this repo, it happens through your Claude session.

Joint retros only (every 12 weeks, starting September 8, 2026) -- the separate 4-week retros are not handled by this automation.

One-time setup
Create a new private GitHub repository (any name, e.g. parabol-retro-automation).
Upload these files into it, keeping the same folder structure:
scripts/parabol_retro_automation.py
scripts/run_joint_cycle.py
scripts/confluence_actions.py
.github/workflows/quarterly-retro.yml
state/latest.json (just contains {} to start) You can do this entirely in GitHub's web interface -- click "Add file" -> "Upload files" and drag them in; no command line needed.
Generate a brand new Parabol Personal Access Token (scoped to MEETINGS_READ, MEETINGS_WRITE, and teams:write on the team) -- don't reuse any token that's been pasted into a chat before.
In the repo: Settings -> Secrets and variables -> Actions -> "New repository secret". Add three secrets:
PARABOL_TOKEN -- the token from step 3.
CONFLUENCE_EMAIL -- the email you log into Atlassian/Confluence with.
CONFLUENCE_API_TOKEN -- an API token from id.atlassian.com/manage-profile/security/api-tokens.
In the repo: Settings -> Actions -> General -> under "Workflow permissions", select "Read and write permissions" and save. (Without this, the workflow can't commit the updated state file back to the repo.)
That's it. The workflow runs automatically every day at 07:00 UTC. You can also trigger it manually any time from the repo's "Actions" tab -> "Quarterly Retro Automation" -> "Run workflow", to test it without waiting.
What I need from you afterward
Once this is set up, tell me the repo's owner and name (e.g. blertaselimaj/parabol-retro-automation) so I can read state/latest.json from it and set up the scheduled task that turns it into the team survey email.
