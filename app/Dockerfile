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

FROM pythonbase1 AS pythonbase2

USER u0
ENV PATH "$PATH:/home/u0/.local/bin"

WORKDIR /app

# Note that /app/requirements.txt etc. files are stored in the container image but not used.
# These are copied to a host directory by a transient container in docker-compose.override.yml
# for preservation in git.  Once this is more stable, this could use something like
#
#   pip install -r requirements.txt
#
# or
#
#   pipenv install --deploy # Use Pipfile.lock
# 


RUN \
    pip install  --upgrade pip \
    && pip install pipenv \
    && pip freeze  > /app/requirements.txt \
    && pipenv lock \
    && pipenv requirements > /app/requirements.pipenv.txt

FROM pythonbase2 AS appbase

WORKDIR /app
COPY --chown=u0:g0 bin  /app/bin/
COPY --chown=u0:g0 lib /app/lib/

FROM appbase AS app

# Force the shell to stop on a STOP
STOPSIGNAL SIGKILL

CMD ["sh"]

