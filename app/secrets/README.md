# app/secrets/

Holds locally-provided credential files that get bind-mounted into the
`app` container. Nothing in this directory except this README is tracked
by git (see `.gitignore`) — these are real secrets, not sample/fixture
data.

Currently expected:

- `google-service-account.json` — a Google Cloud service-account key with
  Editor access to the target Google Sheet (see `CLAUDE.md` for the setup
  steps and how it's used). Must be readable by the container's non-root
  `u0` user once bind-mounted (`chmod 644` after downloading a fresh key).
