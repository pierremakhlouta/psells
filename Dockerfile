# PSells in a container: the web pages and the HTTP API, served by uvicorn.
#
# The image holds code only. The database and the configuration file are
# mounted at /data when the container starts and are never copied in, so an
# image can be shared or pushed without carrying a single record.
#
# Build and run against sample data, from this folder (the README has the steps
# that build the sample data first):
#
#     docker build -t psells .
#     docker run --rm -p 127.0.0.1:8000:8000 -v /tmp/psells-sample:/data psells

# Python 3.14 to match CI. slim is Debian without compilers or documentation:
# smaller, and less installed software to carry vulnerabilities.
FROM python:3.14-slim

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

USER psells

# The same two variables the README uses to point the application at a copy.
ENV PSELLS_DB=/data/psells.db \
    PSELLS_CONFIG=/data/config.json

EXPOSE 8000

# 0.0.0.0 inside the container, because Docker forwards a published port to the
# container's network interface, not to its loopback, so a server listening on
# 127.0.0.1 in here could never be reached. Who can reach it from outside is
# decided by how the port is published: -p 127.0.0.1:8000:8000 keeps it to this
# machine, the only safe choice while there is no authentication.
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
