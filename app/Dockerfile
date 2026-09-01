# Note: This installs its python in /usr/local/bin.  There's
# also a /usr/bin/python3 which links to 3.11.  This is mentioned
# in https://hub.docker.com/_/python
#
FROM python:3 AS pythonbase0

FROM pythonbase0 AS pythonbase1

# Install required libraries for OpenCV & dependencies

RUN apt update

RUN groupadd -r g0 && useradd -r -g g0 --create-home u0
RUN mkdir /app && chown u0:g0 /app

FROM pythonbase1 AS pipenvbase

# pipenv itself is a build-time tool, used only to re-lock
# app/pip/Pipfile (see the update-requirements compose service), not a
# runtime dependency the script imports. It's still present in the
# final `app` image below, since `appbase`/`app` build FROM this stage
# rather than copying artifacts out of it (Docker's multi-stage FROM
# chains accumulate all ancestor layers) — that's unchanged from
# before this Dockerfile was split into stages. The split's purpose is
# narrower: it gives `update-requirements` its own build target that
# skips appbase's COPY/pip-install of the app's own code and
# dependencies, so re-locking doesn't require the whole app to build
# first. Installed here, as root (before the USER u0 switch below),
# into the system-wide site-packages: update-requirements runs as root
# (it needs to write into a root-owned bind-mounted host directory —
# see docker-compose.override.yml), and a root-owned, world-readable
# system install is usable by both root and u0, whereas installing it
# as u0 (into u0's own user-site) would be invisible to root.
RUN pip install --upgrade pip && pip install pipenv

FROM pipenvbase AS pythonbase2

USER u0
ENV PATH "$PATH:/home/u0/.local/bin"

WORKDIR /app

FROM pythonbase2 AS appbase

# Install exactly what's pinned in the committed Pipfile.lock (the
# source of truth for versions — see app/pip/Pipfile and the
# update-requirements compose service for how it gets updated).
# `pipenv install`/`sync` create their own virtualenv by default, which
# would be invisible to bin/*.py scripts run directly via their
# `#!/usr/local/bin/python` shebang (e.g. `podman exec ... bin/testGetForDate.0.py`).
# `--system` would avoid that, but fails here: u0 (non-root) can't write
# to the system-wide site-packages this base image ships. Exporting the
# lock to plain requirements format and installing with plain `pip`
# sidesteps both problems — pip already falls back to the per-user
# site-packages (on $PATH via the ENV PATH line above) when it can't
# write system-wide, which is exactly where bin/*.py's shebang looks.
COPY --chown=u0:g0 pip/Pipfile pip/Pipfile.lock ./pip/
RUN cd pip \
    && pipenv requirements > /tmp/requirements.lock.txt \
    && cd .. \
    && pip install --upgrade pip \
    && pip install -r /tmp/requirements.lock.txt

COPY --chown=u0:g0 bin  /app/bin/
#COPY --chown=u0:g0 lib /app/lib/

FROM appbase AS app

# Force the shell to stop on a STOP
STOPSIGNAL SIGKILL

CMD ["sh"]

