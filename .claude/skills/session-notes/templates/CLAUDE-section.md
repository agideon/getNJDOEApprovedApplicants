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

## If this repo sits under a shared, non-git parent directory

Some setups run Claude Code from a parent directory that is not itself a
git repo and holds several independent repos as subdirectories, with a
lightweight parent-level `CLAUDE.md` pointing into each one. This is
confirmed to work fine for skill discovery: reading a file in each of two
sibling repos, from a session whose CWD was the ungit parent the entire
time, triggered independent discovery for each repo in turn (each becoming
invocable by name, disambiguated with a path prefix once more than one
same-named skill existed — e.g. `html:session-notes` and
`wp-podman-dev:session-notes`).

The one real caveat isn't specific to the parent-directory setup at all:
discovery for a given repo fires at most once per session, on the first
time the **Read tool** (not Bash `cat`/`head`) reads any file in that repo.
If this repo was already Read from earlier in the *same* session — before
this skill existed on disk here — that one-time trigger already fired and
found nothing, and by-name invocation will not become available later in
that session no matter how much more gets read. The reliable fallback,
regardless of cause: read `<this-repo>/.claude/skills/session-notes/SKILL.md`
directly with the Read tool and follow its instructions for init/update/
replicate actions manually. This works regardless of discovery mechanics,
so treat it as the default whenever invoking by name isn't working — don't
spend effort retrying the by-name invocation first.

(`claude --add-dir <subrepo>` or `/add-dir <subrepo>` mid-session broadens
file access to the subrepo — confirmed for `permissions.additionalDirectories`
in `settings.json`, which grants file access only. Whether either one also
triggers skill discovery is untested; don't rely on it without checking.
`/add-dir` can only be invoked by a human typing it; it cannot be
triggered from `CLAUDE.md` text.)
