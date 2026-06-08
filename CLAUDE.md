# Project Overview

This is a utility to acquire information about recently approved applicants
who have passed the New Jersey's Department of Education's background check.
It supports a PTAC effort to bring more volunteers into the buildings.

The `app` service is started via:
```
podman compose --ansi never up -d --build
```
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
