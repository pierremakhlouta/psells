# Postmortem: the demo's database stopped for fifteen minutes

**Date:** 5 October 2026, 02:13 to 02:28 UTC (4 October, 22:13 to 22:28 in
Toronto)
**Service:** the PSells demonstration at https://psells.lakeshorefreight.me,
invented records only
**Severity:** full outage of the demo; no data lost
**Status:** resolved; two of three action items done
**Kind:** a planned failure, run on purpose in Phase 10 to test the
monitoring. It is written up exactly as an unplanned one would be.

## Summary

The demo's PostgreSQL container was stopped for 15 minutes. Every page,
the login page included, answered 500 within five seconds. The outside
checks failed from all three locations, and the site-down alert fired
5 minutes 17 seconds after the database stopped and emailed the owner.
When the database was started again the application recovered by itself,
and the alert resolved 2 minutes 49 seconds later.

The monitoring did its job. The outage also showed three weaknesses in the
application around it: its health check said healthy throughout, every
failed request produced a bare 500 and a full traceback, and the cause was
visible only on the server. The first two are fixed and the fixes proved on
the demo; the third is open.

## Impact

- Every page and API request answered **500 Internal Server Error** for
  15 minutes 4 seconds (02:13:23 to 02:28:27 UTC).
- About 22 requests were answered 5xx, nearly all of them the outside checks
  themselves: the demo has few visitors.
- No data was lost or changed. The database's data stayed on its volume.
- The availability SLO (99.5% of checks passing over 7 days) took the
  failures against its budget of about 50 minutes a week. The SLO read 47.9%
  just afterwards, because the checks were then about an hour old; see
  "Reading an SLO on a young window" below.

## Timeline (UTC)

| Time | Event |
|---|---|
| 02:13:21 | `/login` answers 200. |
| 02:13:23 | The database container is stopped (`docker compose stop db`). |
| 02:13:28 | `/login` and `/out-of-stock` answer 500. |
| 02:14:27 | Outside checks passing over the last 5 minutes: 83%. |
| 02:15:18 | 33% passing; nginx's 5xx count starts to rise in Grafana. |
| 02:16:08 | 17% passing. The alert rule goes **pending**. |
| 02:16:59 | 0% passing. |
| 02:18:40 | The alert **fires**; the email reaches the owner. **Detected: 5 min 17 s.** |
| 02:18 to 02:20 | Investigation: Grafana shows nginx's 500s on `/login`; the server's app log shows the cause. |
| 02:28:24 | The database container is started. |
| 02:28:27 | The database is healthy. |
| 02:28:33 | `/login` answers 200. **Recovered: 3 s after the start, no restart of the app.** |
| 02:31:13 | The alert **resolves**; the resolved email follows. |

## Detection

Three outside checks of `/login` (Montreal, North Virginia, London, every
two minutes) failed as soon as their next runs came round. The alert fires
when under half of all checks pass over five minutes and that holds for two
more, so one location's own trouble never pages; it fired after 5 minutes 17
seconds, inside the 7 minutes it was designed for.

## Investigation

The dashboard showed the symptom, not the cause. Grafana had nginx's lines:
every request to `/login` answered 500 in about 7 ms, so nginx was reaching
the application and the application was failing quickly. Nothing in Grafana
said why. The cause was in the application's own log, which is not sent to
Grafana, and needed a shell on the server through Session Manager:

```
psycopg.OperationalError: failed to resolve host 'db': [Errno -3] Temporary failure in name resolution
ERROR:    Exception in ASGI application
Traceback (most recent call last):
```

## Root cause

The database container was stopped (on purpose, for this test). With the
container gone, Docker's network no longer resolved its name, `db`. Every
request needs a database connection, even the login page, which looks up
the visitor's session first, so every request failed at its first step.

## Contributing factors

1. **The app's health check said healthy throughout.** It only opened a
   socket to uvicorn, which kept accepting connections. Docker, the deploy's
   `--wait` and anyone reading `docker ps` saw a healthy application while
   it answered nothing but 500s. Only the outside checks knew.
2. **A missing database was an unhandled exception.** Each request ended in
   a bare 500 "Internal Server Error", which told a visitor nothing, and a
   full traceback in the log, which buried the one line that mattered.
3. **The cause was not where the alert pointed.** Grafana receives nginx's
   access lines and the server's health, not the application's errors, so
   finding the cause took a shell on the server.

## What went well

- The alert fired inside its designed time, from what visitors feel rather
  than from a cause, and reached the owner by email, as did the resolution.
- No location's own network was mistaken for an outage: all three failed
  together.
- The application recovered without a restart, because it opens a database
  connection per request.
- nginx's log carried exactly what the investigation needed (path, status,
  time) and nothing about visitors.

## What went poorly

- Docker reported the application healthy for the whole outage.
- Visitors got an unexplained 500.
- The investigation needed shell access to the server.

## Action items

| # | Action | Status |
|---|---|---|
| 1 | Make the app's health check ask the database (`SELECT 1` through `psells.connect`), not only uvicorn. | **Done**, commit 3877ad7 |
| 2 | Answer a missing or lost database with **503 Service Unavailable**, a sentence and `Retry-After: 60`, and log one line instead of a traceback. | **Done**, commit 3877ad7 |
| 3 | Send the application's error lines (not its access lines) to Grafana, so the cause is visible next to the symptom, after checking that nothing private can reach them. | Open |

## Verifying the fixes

The demo's database was stopped again for 106 seconds at 02:41:30 UTC with
both fixes deployed:

- A visitor received `503 Service Unavailable`, `Retry-After: 60` and "PSells
  cannot reach its database right now. Please try again in a minute."
- The application's log held one line per request and no traceback.
- The health check failed at 02:42:02, 02:42:33 and 02:43:04, and Docker
  marked the application **unhealthy** at the third, 94 seconds after the
  stop. It passed again at 02:43:35, after the database was back.

That last point corrected an expectation written before the test: Docker
needs three failed checks in a row (its default `retries`), so at 30-second
intervals "unhealthy" takes about 90 seconds, not one interval.

## Lessons

- **A health check that does not test what the service needs is a liveness
  check, not a readiness one.** Ask the dependency the service cannot work
  without.
- **Alert on the symptom, investigate from the cause.** The alert was right
  to watch what visitors feel; the investigation needed the application's
  own errors, which should sit beside the symptom.
- **Reading an SLO on a young window.** Thirty-five failed checks out of an
  hour's worth reads as 47.9% "over 7 days" when only an hour of data
  exists. Over a full week the same failures are about 99.8%, inside the
  99.5% objective. An SLO's figure means what its window says only once the
  window is full.
- **A new check and "no data alerts" race at the start.** When the checks
  were first created, the alert went pending on no data before the second
  runs made a rate computable, and returned to normal with seconds to spare.
  Worth knowing before trusting "no data alerts" on a brand-new check.
