---
name: session-notes
description: Maintain SESSION_NOTES.md for cross-machine, cross-developer session continuity in this repo. Invoke to (1) initialize session notes in a project that doesn't have them yet, (2) update/wrap up notes at the end of a work session or when switching tasks, or (3) replicate this skill into another repository so the same practice can be used there. Triggers include "wrap up", "save state", "update session notes", "set up session notes", "replicate session notes".
---

# session-notes

Maintains `SESSION_NOTES.md`: a git-committed file that lets any developer,
on any machine, pick up a project's state without re-deriving it from git
history or relying on any single person's local Claude memory. This skill
is itself committed to `.claude/skills/session-notes/`, so every developer
who clones the repo gets it automatically — no separate install step.

## Modes

Parse `args` (if given) for one of: `init`, `update`, `replicate <path>`.
If no `args`, auto-detect:
- No `SESSION_NOTES.md` in the target repo → `init`
- `SESSION_NOTES.md` exists → `update`

## Step 0 — find the target repo root

Skill discovery is triggered per-subrepo by the **Read tool** specifically
reading any file in that subrepo — not by Bash commands that happen to
output file contents (`cat`, `head`, etc. do not trigger it), and not
specifically a file inside `.claude/skills/` itself; any file in the
subrepo does. This fires at most once per subrepo per running
process: it's the *first* Read-tool access to that subrepo in the current
session that triggers a scan of its `.claude/skills/`, adding whatever is
found there to the available-skills list for the rest of that session.

This was confirmed across two rounds of testing that at first looked
contradictory (see `SESSION_NOTES.md` "Decisions & rationale" for the
full history):

- Round 1 (single long-running session): this subrepo had already been
  Read from extensively from the start of the conversation, long before
  this skill existed on disk. Later reading the skill's own files
  repeatedly did not make it invocable — the one-time discovery trigger
  had already fired-and-found-nothing earlier, and did not refire.
- Round 2 (after exiting and starting a new session/process, skill
  already on disk by then): reading a file in this subrepo — not inside
  `.claude/skills/`, just `SESSION_NOTES.md` — immediately triggered
  discovery. Separately, in the same session, a sibling subrepo's
  `SESSION_NOTES.md` was read via Bash `head` first (no effect), then via
  the Read tool (triggered discovery for that subrepo too) — isolating
  the Read tool specifically as the trigger. This also directly confirmed
  discovery works from a session whose CWD was an ungit parent directory
  the entire time, holding both subrepos as siblings.

Practical implications:
- If this skill was just created, replicated, or pulled into a repo, and
  Claude has *not yet* used the Read tool on any file in that repo this
  session, the next Read-tool access to a file there should trigger
  discovery and make it invocable by name for the rest of the session.
- If that repo was *already* Read from earlier in the same session —
  before the skill existed on disk — by-name invocation will not become
  available in that session no matter how much more gets read afterward.
  The reliable fallback in that case: read
  `.claude/skills/session-notes/SKILL.md` directly with the Read tool and
  follow it manually. This fallback works regardless of discovery
  mechanics, so it's the reliable default whenever invoking by name fails
  for any reason.
- When more than one repo in the same session has a skill with this same
  name, all of them get disambiguated with a path prefix once more than
  one is discovered (confirmed: a single discovered skill first appeared
  as the bare `session-notes`; once a second, same-named skill was
  discovered in a sibling repo, *both* were re-listed with prefixes —
  `html:session-notes` and `wp-podman-dev:session-notes` — not just the
  second one). Invoke using the exact prefixed name shown in the
  available-skills listing once more than one exists, not the bare name.
- `claude --add-dir <subrepo>` or `/add-dir` as alternate triggers remain
  untested; `permissions.additionalDirectories` in `settings.json` is
  confirmed to grant file access only, not skill discovery.

**A separate caveat, once discovery has already happened:** within a
single session, after this skill has been discovered and invoked by name
at least once, a *later* by-name invocation in that same session cannot
be trusted to reflect edits made to its files earlier in that same
session — even if those edits were committed. Confirmed twice, with two
different symptoms of what appears to be the same underlying cause (see
`SESSION_NOTES.md` "Decisions & rationale" → Rounds 3 and 5 for the full
history):

- Once, a by-name invocation served an older draft of this very file's
  Step 0 text, even though a newer draft had already been committed
  earlier in that same session.
- A second, deliberate retest — editing this file, committing, then
  reinvoking by name again in the same session — instead saw the
  invocation decline to reload at all, reporting the skill "already
  loaded ... instructions unchanged," despite the file having in fact
  just changed.

The precise internal mechanism isn't known, but the practical rule is
the same either way: **within one session, once you've invoked this
skill by name, don't trust a later by-name invocation in that same
session to reflect any edit made to its files during that session.**
This is distinct from — and does not affect — the *cross-session* case:
a brand-new session's first discovery-and-invoke has been confirmed to
serve current on-disk content correctly. The fix, in the affected case,
is the same reliable fallback already given above for the
discovery-never-fired case: read the file directly with the Read tool
rather than relying on the by-name invocation.

Once this skill's instructions are being followed (whether invoked by
name or read directly), resolving the target repo root is rarely
ambiguous in practice:

1. Run `git rev-parse --show-toplevel` from the current shell CWD.
   - **Succeeds** → that's the target repo root. Proceed.
   - **Fails** (shell CWD is an ungit parent directory) → re-run
     `git rev-parse --show-toplevel` from the directory containing
     whichever file made it clear which repo is meant (e.g. the
     `SKILL.md` that was just read directly, or the file whose Read
     triggered discovery).
2. If it's still unclear which repo is meant (e.g. more than one subrepo
   is plausibly relevant), ask — via AskUserQuestion or plain text —
   rather than guessing.
3. If `replicate <path>` was requested with an explicit path, skip this
   detection entirely — the path names the target directly (see Replicate
   mode; it need not be a git repo yet).

All subsequent steps operate relative to the resolved target repo root.

## Init mode

1. Confirm `SESSION_NOTES.md` doesn't already exist at the target repo
   root. If it does, stop and ask before overwriting.
2. Copy `templates/SESSION_NOTES.md` (next to this file) to
   `<repo-root>/SESSION_NOTES.md`, verbatim — it's a placeholder
   skeleton, not meant to be filled in blindly. Don't invent content for
   the placeholder fields at this step.
3. Check `<repo-root>/CLAUDE.md`:
   - Doesn't exist → create it containing just
     `templates/CLAUDE-section.md`.
   - Exists, no `# Session continuity` heading → append
     `templates/CLAUDE-section.md`.
   - Exists, already has a `# Session continuity` heading → leave it
     alone and tell the user so (don't clobber project-specific wording
     someone already wrote).
4. Tell the user what was created. Do not commit automatically — offer
   to show a commit message and wait for approval, same as any other
   change.
5. If there's meaningful project state worth recording right away (e.g.
   the user is mid-session, or asks explicitly), continue straight into
   Update mode to fill the skeleton in — don't leave it as inert
   placeholder text when real state already exists to capture.

## Update mode ("wrap up" / "save state")

1. Read the existing `SESSION_NOTES.md` and `CLAUDE.md` at the target
   repo root.
2. Gather ground truth — don't rely on conversational memory alone:
   - `git log -1 --format="%H %aI" --date=iso-local` for the exact
     current commit hash and date (never guess or reuse a stale value).
   - `git log -15 --oneline` and `git status` to see what has actually
     landed versus what's still uncommitted.
3. Rewrite each section:
   - **Current goal** — one sentence on what's actively being worked
     toward right now (or "no active feature work" if between tasks).
   - **State as of [date, full 40-char hash]** — what's done, what's in
     progress (specific: file/function/line), what's broken or blocked
     and why.
   - **Next steps** — concrete, actionable, unchecked items only.
   - **Planned tasks** — proposed-but-not-implemented work. Keep
     `declined`/`deferred` entries rather than deleting them (they
     record what was considered and prevent re-proposing the same idea
     without new information); remove an entry only once truly obsolete.
   - **Decisions & rationale** — append notable decisions made this
     session, each with a one-line reason.
   - **Open questions** — add anything unresolved; remove ones that got
     resolved.
4. Prune rather than accumulate: this file reflects current state, not a
   dated log. If the user wants a historical log instead, that belongs in
   a separate file — don't conflate the two.
5. Show the diff to the user. Do not commit automatically — follow the
   standing rule of always showing the commit message first and waiting
   for approval, even for a "just documentation" change.

## Replicate mode

Use when the user wants this same practice set up in a different
repository: `replicate <path>`.

1. Resolve `<path>` (it may not exist as a git repo yet — this step only
   touches files, it doesn't run git commands there).
2. Copy this entire skill directory (`.claude/skills/session-notes/`,
   including `SKILL.md` and `templates/`) to
   `<path>/.claude/skills/session-notes/`. This directory is the single
   source of truth for the practice — copy it wholesale rather than
   hand-transcribing pieces, so future edits to the protocol only need
   to be made once and re-propagated by copying again.
3. Run Init mode (steps 2–3 above) against `<path>` as the target repo
   root.
4. Report what was copied/created in `<path>` and remind the user those
   files are new/uncommitted there — whoever owns that repo should
   review and commit them there themselves.

## Guardrails

- Never commit on behalf of the user — this applies to `SESSION_NOTES.md`
  updates exactly as it does to code changes.
- Never fabricate "State as of" details — if something is unclear, ask
  rather than guess, especially the commit hash and date.
- `SESSION_NOTES.md` is the project-shared, git-tracked source of truth
  for in-progress/proposed work. It is distinct from Claude's own local
  per-machine memory, which is for longer-lived reference facts (e.g.
  "which years of data are imported") rather than session-to-session
  task handoff.
