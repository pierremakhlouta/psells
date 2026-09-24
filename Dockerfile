# PSells in a container: the web pages and the HTTP API, served by uvicorn.
#
# The image holds code only. The records live in the PostgreSQL service beside
# it and the configuration file is mounted at /config when the container
# starts; neither is ever copied in, so an image can be shared or pushed
# without carrying a single record. compose.yaml supplies both:
#
#     docker compose up --build -d --wait

# Python 3.14 to match CI. slim is Debian without compilers or documentation:
# smaller, and less installed software to carry vulnerabilities. Pinned to an
# exact version and to the digest of its contents, so every build starts from
# the same bytes and a republished tag cannot change them. Dependabot proposes
# the next one, and image.yml scans it before it is merged.
FROM python:3.14.7-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2

# No .pyc files written inside the image, and log lines reach `docker logs` as
# they are printed rather than when a buffer fills.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The server runs as an ordinary user, not root, so a compromised process gets
# no more than that user can do.
RUN useradd --create-home --uid 10001 psells

WORKDIR /app

# Requirements before code, so Docker's layer cache reinstalls them only when
# requirements.txt changes, not on every edit to a Python file. Runtime
# requirements only: no test runner and no spreadsheet library.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# The files the server needs, named one by one. "COPY . ." would take whatever
# is in the folder, and this folder holds the real data. Naming each file means
# a new data file can never reach an image by accident; .dockerignore keeps the
# data out of the build context as well. tests/test_container.py holds both.
COPY psells.py api.py web.py dependencies.py cross_site.py ./
COPY templates/ templates/

# COPY keeps each file's permissions from the machine that built the image and
# makes root its owner. A file that was readable only by its owner there is
# then readable only by root here, and the server, running as psells, cannot
# open it: it stops at startup with "Permission denied". This happened in
# Phase 04. Everyone may read every file, and enter every folder, so the image
# no longer depends on how the files were saved. Nothing here is writable by
# psells, which it never needs.
RUN chmod -R a+rX /app

USER psells

# Where compose.yaml mounts the configuration file. PSELLS_DATABASE_URL has no
# default here or anywhere: it names a host and a password, and Compose sets it.
ENV PSELLS_CONFIG=/config/config.json

EXPOSE 8000

# 0.0.0.0 inside the container, because Docker forwards a published port to the
# container's network interface, not to its loopback, so a server listening on
# 127.0.0.1 in here could never be reached. Who can reach it from outside is
# decided by how the port is published: -p 127.0.0.1:8000:8000 keeps it to this
# machine, the only safe choice while there is no authentication.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
