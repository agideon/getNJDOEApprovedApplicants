# Project Overview

This is a utility to acquire information about recently approved applicants
who have passed the New Jersey's Department of Education's background check.
It supports a PTAC effort to bring more volunteers into the buildings.

The `app` service is started via:
```
PWD=$HOST_PWD HOME=$HOST_HOME XDG_RUNTIME_DIR=$HOST_XDG_RUNTIME_DIR podman compose up -d --build
```
`HOST_PWD`, `HOST_HOME`, and `HOST_XDG_RUNTIME_DIR` are the host-side project root, home directory,
and runtime dir (set via `-e HOST_PWD=$PWD -e HOST_HOME=$HOME -e HOST_XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR`
on the Claude container launch). This is necessary because `podman compose` runs on the host daemon
and resolves volume paths against the host filesystem, but is invoked from inside the Claude
container, where `$PWD` is `/workspace`, `$HOME` is `/root`, and `$XDG_RUNTIME_DIR` is unset — none of
which exist on the host. `PWD=`/`HOME=`/`XDG_RUNTIME_DIR=` on the invocation itself remap those three
back to their host-side values (from `HOST_PWD`/`HOST_HOME`/`HOST_XDG_RUNTIME_DIR`) for the duration of
that one command; `docker-compose.override.yml` itself still just references the plain `${PWD}`, `~`,
and `${XDG_RUNTIME_DIR}` names, same as any compose file run directly on a host would.

This remapping is only needed when the command runs from inside a Claude Code session. A developer
working directly at a real host terminal (not through Claude) doesn't need any of this — `$PWD`,
`$HOME`, and `$XDG_RUNTIME_DIR` are already correct there, so the plain `podman compose --ansi never
up --build` documented in `README` is what applies.

Reports on the latest approvals by the state are generated via commands such as:
```
podman exec -it background-check-app bin/testGetForDate.0.py --days 20 --county 13 --district 3310
```
where
- `--days` indicates how many days into the past approvals should found and reported.
- `--county` indicates the county for which approvals will be checked ("13" being Essex County).
- `--district` indicates the district for which approvals will be checked ("3310" being Montclair).

To ease development, this does a little trickery in `docker-compose.override.yml`.
It mounts volumes containing the source code from the host.  This lets a developer
change and test code w/o rebuilding the container.  The application's Dockerfile
does do the proper COPYing to create a standalone/deployable stack, but I don't
believe I've tested that yet (so some needed components may still be missing).

`app/pip/Pipfile` and `app/pip/Pipfile.lock` are the source of truth for the app's Python
dependencies; the `app` image installs exactly what's pinned in `Pipfile.lock` (see
`app/Dockerfile`). To add/remove/re-pin a package, edit `Pipfile`, then re-lock it via the
`update-requirements` service in `docker-compose.override.yml` — kept out of normal `up`/`up -d
--build` behind a Compose profile, since it's only needed on the rare occasion dependencies
actually change:
```
podman compose --profile update-requirements run --rm update-requirements
```
This writes a new `Pipfile.lock` back to `app/pip/`, which should be committed like any other
source change.

Shared NJDOE fetch/filter logic lives in `app/lib/njdoe.py` (a dev-mounted, non-installed module —
each `bin/*.py` script does `sys.path.insert(0, ...)` to find it, since the scripts are run directly
via their `#!/usr/local/bin/python` shebang, not as an installed package). `bin/testGetForDate.0.py`
and `bin/matchApprovalsToSheet.py` both build on it.

## Cross-referencing the volunteer spreadsheet (`bin/matchApprovalsToSheet.py`)

Identifies which people on a Google Sheet of PTAC volunteers have any of one or more given NJDOE
approvals (job position(s) default to `SUBSTITUTE TEACHER`) and writes the result back into the
sheet:
```
podman exec -it background-check-app bin/matchApprovalsToSheet.py --days 30 --county 13 --district 3310 --sheet-id <sheet-id> --job-position "SUBSTITUTE TEACHER" "CLASSROOM TEACHER" "ADMINISTRATOR/SUPERVISOR"
```
- Matches on `YOUR FULL NAME: - First Name` / `YOUR FULL NAME: - Last Name` by default — **not**
  the sheet's `Name - First Name` / `Name - Last Name` columns, which are the volunteer's emergency
  contact, not the volunteer. Override with `--first-name-column`/`--last-name-column`, or
  `--full-name-column` for a single combined-name field, if pointed at a differently-shaped sheet.
- Adds three new columns on first run (`--status-column`/`--roles-column`/`--review-column`,
  extending whichever row-1 banner text trails into blank cells immediately before them) rather
  than writing into any of the sheet's existing HR/PTAC-tracking columns:
  - **Status** (confirmed matches only): an NJDOE approval date, written only for a clean,
    unambiguous, exact (punctuation/whitespace-insensitive) name match. A candidate can have
    multiple qualifying approvals — different `--job-position` roles and/or different dates — in
    which case only the single most recent date is written here (NJDOE's date format sorts
    correctly as a plain string, so no date parsing is needed to find the max). Never
    blanked/overwritten just because a later, narrower `--days` window didn't re-find it — absence
    of evidence in a limited lookback window isn't evidence of absence. Re-running with a wider
    window (or on a later day, as more NJDOE history accumulates) can only add matches, never
    remove one already recorded.
  - **Roles** (confirmed matches only): every *distinct* role (from `--job-position`) the candidate
    was found approved for anywhere in the lookback window — not just whichever role happens to be
    tied to the single most-recent date in Status. E.g. someone approved as both Substitute Teacher
    (an older date) and Classroom Teacher (the most recent date) shows `Status: <newer date>`,
    `Roles: CLASSROOM TEACHER, SUBSTITUTE TEACHER`.
  - **Needs Review** (candidates, not confirmed): two cases land here instead of Status —
    (a) more than one sheet row shares the exact same name, or (b) a NJDOE and sheet name are a
    known nickname pair (e.g. "Andy"/"Andrew" — via the `nicknames` package) rather than an exact
    match. Nickname relationships are inherently ambiguous (a nickname can map to several formal
    names) and aren't inferable from spelling the way typos are, so they're never auto-confirmed.
    A reviewer resolves a flagged row by either entering the date in Status themselves (confirmed —
    do this, don't just clear Review) or typing `no` in Review (rejected). Either way, once Review
    is non-blank for a row, the script leaves that cell alone on future runs — a human owns it until
    *they* clear it back to blank (clearing to fully blank means "pending" again, not "resolved").
    Filter the sheet on Review containing the flag text (not just non-blank) to see the live queue,
    since resolved-and-rejected rows hold `no`, not blank.
- `--sheet-id` defaults to the production PTAC sheet; pass a throwaway copy's ID while testing
  changes to this script.

### One-time Google Cloud setup (manual — needs a browser/Google account, can't be automated)
1. In Google Cloud Console, enable the **Google Sheets API** for the project (Drive API isn't
   needed — the script opens the sheet by its known ID via `open_by_key`, which only calls the
   Sheets API directly).
2. Create a **Service Account** (Sheets access is controlled entirely via the sheet's own Share
   dialog, not GCP IAM — no project role needs to be granted to it).
3. Create and download a **JSON key** for it.
4. **Share the target spreadsheet** with the service account's `client_email` (found in the
   downloaded JSON) as **Editor** — the script needs to write back the approval-date column, not
   just read.
5. Save the key as `app/secrets/google-service-account.json` (see `app/secrets/README.md`) and
   make sure it's at least group/world-**readable** on the host (`chmod 644`) — downloaded keys are
   often owner-only (`0600`), which would be unreadable by the container's non-root `u0` user once
   bind-mounted.



# Critical Development Constraints
- Never suggest `docker` commands.  This uses rootless Podman.


# Comment Style
- Write comments that explain concepts not derivable from the code itself: why something was done, what alternatives were considered, and why those alternatives were rejected. This applies to Python, SQL, shell scripts, and configuration files alike.

# Git Guidelines
- When Claude Code authors a commit in this repo, it must be attributed to whichever real person is actually driving that session — never a session-default placeholder identity (e.g. `claude0@tagonline.com`). This repo is worked on by more than one person over time, so this rule intentionally does not name a specific person.
  - First, just try `git commit` normally. If the machine running Claude Code already has `user.name`/`user.email` configured (globally or for this repo), git resolves the correct person automatically with no extra action needed — this is the common case on a developer's own properly-configured machine.
  - Only if that fails (git errors demanding an identity — typically means this session is running in an environment with no git config at all, e.g. a fresh sandbox) should Claude Code do anything further: stop and ask the current user for their name and email, then supply it for that commit only via `GIT_AUTHOR_NAME`/`GIT_AUTHOR_EMAIL`/`GIT_COMMITTER_NAME`/`GIT_COMMITTER_EMAIL` environment variables on the `git commit` invocation itself — never `git config` (global config must never be touched, per the user's own global CLAUDE.md), and never a guessed or hardcoded identity.
- After completing a distinct task or resolving an issue, ask the user if you should commit the changes.
- NEVER run `git commit` with the `-m` flag blindly without showing the user the proposed message first.
- Commit messages must follow clean formatting (e.g., a short imperative summary line, followed by bullet points explaining the technical details if necessary).  Commit messages can include narratives beyond the bullet points, explaining why something is being done and what alternatives were considered any why these were rejected.  Commit messages must be meaningful and descriptive.
- When referencing a commit in a commit message, always use the full 40-character digest rather than a shortened version to avoid ambiguity as the repository grows.
- Ignore files that `.gitignore` files tell git to ignore.

# Session continuity

This project preserves cross-session, cross-developer continuity via
`SESSION_NOTES.md` (git-committed) and the `session-notes` skill in
`.claude/skills/session-notes/`.

- Before starting any work, read `SESSION_NOTES.md`.  If it doesn't
  exist, invoke the `session-notes` skill (`init` mode) to create it.
- At the end of a session, or when asked to "wrap up", "save state", or
  switch to a new task, invoke the `session-notes` skill (`update` mode)
  to refresh it.
- See `.claude/skills/session-notes/SKILL.md` for the full read/write
  protocol, pruning rules, and how to replicate this setup into another
  repository.


