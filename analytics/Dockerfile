# The analytics image: psells.py's own readers and pandas, for the ETL that
# builds the warehouse. Built from the project folder, so it can copy
# psells.py, and run as a one-off container of compose.analytics.yaml:
#
#     docker build --file analytics/Dockerfile .
#
# Its own image rather than the app's, so the image that serves the web
# carries none of pandas and numpy, and has nothing more to scan or patch.
# Like the app's, it holds code only: no records, no configuration and no
# password are ever copied in, and .dockerignore keeps data/ and .env out of
# the build altogether.

# The app's base image, pinned the same way; a test holds the two equal.
FROM python:3.14.7-slim@sha256:caaf356f40667c496d405780745b9ac25771c189a51dfcc42430d531ea09f8a2

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# The same Debian fixes as the app's Dockerfile, for the same base image; a
# test holds the two lines equal.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends --only-upgrade \
        libpcre2-8-0 libssl3t64 openssl openssl-provider-legacy \
    && rm -rf /var/lib/apt/lists/*

# Its own user, never root, and not the app's.
RUN useradd --create-home --uid 10002 analytics

WORKDIR /app

COPY requirements-analytics.txt .
RUN pip install --no-cache-dir -r requirements-analytics.txt

# psells.py for its readers, the ETL, and the warehouse's tables: the ETL asks
# psells for every figure rather than working one out.
COPY psells.py analytics/etl.py analytics/warehouse.sql ./

RUN chmod -R a+rX /app

USER analytics

CMD ["python", "etl.py"]
