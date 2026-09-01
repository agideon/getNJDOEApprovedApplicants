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
and reports on the latest approvals by the state are generated via
commands such as:
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

There's also a service in `docker-compose.override.yml` called
`lock-requirements` which will store the latest requirements used to
build the container image.  These can be stored and used later, if
needed, to revert to previous versions of requirements if future
versions cause problems.



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


