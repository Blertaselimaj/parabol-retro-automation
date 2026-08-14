# Parabol joint-retro automation

This repo automatically starts each new joint-retro cycle's Parabol meeting on
schedule -- no one needs to click anything in Parabol to start it.

## What it does

Once a day, a GitHub Action checks whether today is 2 days before the next
joint retro's reflection deadline. On that day only, it:

1. Closes any leftover/stale meeting for the "Quarterly Team Retro" template.
2. Starts a new meeting for this cycle.
3. Writes the invite link, topics, and deadline to `state/latest.json` and
   commits that file back to this repo.

Claude then reads that file on its own schedule and sends the team survey
email -- that part isn't in this repo, it happens through your Claude session.

Joint retros only (every 12 weeks, starting September 10, 2026) -- the
separate 4-week retros are not handled by this automation.

## One-time setup

1. Create a new **private** GitHub repository (any name, e.g. `parabol-retro-automation`).
2. Upload these files into it, keeping the same folder structure:
   - `scripts/parabol_retro_automation.py`
   - `scripts/run_joint_cycle.py`
   - `.github/workflows/quarterly-retro.yml`
   - `state/latest.json` (just contains `{}` to start)
   You can do this entirely in GitHub's web interface -- click "Add file" ->
   "Upload files" and drag them in; no command line needed.
3. Generate a **brand new** Parabol Personal Access Token (scoped to
   `MEETINGS_READ`, `MEETINGS_WRITE`, and `teams:write` on the team) -- don't
   reuse any token that's been pasted into a chat before.
4. In the repo: Settings -> Secrets and variables -> Actions -> "New repository
   secret". Name it `PARABOL_TOKEN` and paste the new token as the value.
5. In the repo: Settings -> Actions -> General -> under "Workflow permissions",
   select "Read and write permissions" and save. (Without this, the workflow
   can't commit the updated state file back to the repo.)
6. That's it. The workflow runs automatically every day at 07:00 UTC. You can
   also trigger it manually any time from the repo's "Actions" tab -> "Quarterly
   Retro Automation" -> "Run workflow", to test it without waiting.

## What I need from you afterward

Once this is set up, tell me the repo's owner and name (e.g.
`blertaselimaj/parabol-retro-automation`) so I can read `state/latest.json`
from it and set up the scheduled task that turns it into the team survey email.
