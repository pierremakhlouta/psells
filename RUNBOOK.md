# PSells runbook

What to do, step by step: everyday tasks, routine care, incidents, and
rebuilding from nothing. ARCHITECTURE.md shows how the parts fit together;
README.md explains each part at length.

Every command runs from the project folder on the Mac unless it says
otherwise. Each procedure says whether it has been tried and how: "tried on
the sample stack" means it was followed exactly, on the invented records,
before it was written down. Nothing here is ever tried on the real records
first.

Two rules apply everywhere:

- **Never `docker compose down -v` on the real stack**, and never
  `docker volume rm` or `prune`: the real records live in the `pgdata` volume.
  `-v` is only for a throwaway project named with `-p`.
- **Back up before anything that changes the real database**: `./backup.sh`.

## Everyday

### Is it running?

```
docker compose ps
curl -sS --cacert ~/PSells-CA/ca.crt -o /dev/null -w '%{http_code}\n' https://psells.localhost/login
```

proxy, app, db and warehouse healthy (and db-test, when the tests' database
is running), and `200`. If not, see "The site does not answer on the Mac"
below.

### Start or stop the stack

Start whatever is stopped, changing nothing that runs (what the login job
does):

```
./start-stack.sh
```

Stop it, keeping every record:

```
docker compose stop
```

### After changing the code

The app's image holds the pages and the code, so a change reaches the Mac
only when the app is rebuilt, alone, which takes a few seconds:

```
docker compose up -d --build --wait --no-deps app
```

If the change touched `templates/base.html`'s style block, nginx's headers
carry a new hash; reload nginx after the rebuild, or pages lose their styles:

```
docker compose exec proxy nginx -t && docker compose exec proxy nginx -s reload
```

A change to `nginx/` itself needs only that reload. A change to the analytics
code needs the analytics image rebuilt:

```
docker compose -f compose.yaml -f compose.analytics.yaml run --rm --build etl
```

Tried: each of these on the real stack, 7 to 9 October 2026.

### Rebuild the analytics now

It rebuilds every hour; to have it now:

```
./refresh-analytics.sh && tail -1 ~/Library/Logs/psells-etl.log
```

### Use the terminal application, or set the login password

```
docker compose exec app python psells.py
docker compose exec app python set_password.py
```

Changing the password logs every browser out.

### Ship a change to the demonstration

Commit and push to `main`; nothing else. The five checks run, and Deploy
waits for all five on that commit, then deploys it. Watch it:

```
gh run list --limit 10
```

A red check means nothing is deployed and the demonstration keeps running
the last good commit.

### Roll the demonstration back

Deploy an earlier commit of `main`, by its full hash:

List the recent commits, choose the one to go back to, and run the second
command with its full hash in place of `HASH`; Deploy refuses anything that
is not a full commit hash of `main` whose checks passed:

```
git log --format='%H %s' -10 origin/main
```

```
gh workflow run deploy.yml -f commit=HASH
```

Not rehearsed for this runbook; it is the same path every deploy takes.

## Routine care

### Backups

`backup.sh` runs at 09:00 every day (launchd), keeps 30 days in
`~/PSells-Backups/daily/`, and proves each dump restores before keeping it.
Its log is `~/PSells-Backups/backup.log`; the last line should be today's and
say ok. A backup by hand, before a risky change:

```
./backup.sh && tail -1 ~/PSells-Backups/backup.log
```

Each backup is also encrypted and copied to iCloud Drive's `PSells-Backups`
folder, kept 30 days, and proved by decrypting it with the Keychain's key; the
log's second line for the day says `offsite ok`. The private key is also in
your password manager, as "PSells backup key (age)". The demonstration's
backups go to S3 and hold invented records only.

### Restore from the off-Mac copy

When the Mac and its backups are gone. On the new Mac, with age installed
(`brew install age`) and iCloud Drive signed in, copy the key from your
password manager to the clipboard, then unpack the newest copy into a folder
of its own:

```
mkdir -p ~/PSells-Restore && cd ~/PSells-Restore && ls -1t ~/Library/Mobile\ Documents/com~apple~CloudDocs/PSells-Backups/*.tar.age | head -1 | xargs -I{} sh -c 'pbpaste | age -d -i - "{}" | tar -xf -' && pbcopy < /dev/null && ls -1
```

It lists the dump and the configuration copy. Put the configuration in place
as `data/config.json`, then restore the dump as in "Restore a backup", with
`dump=~/PSells-Restore/psells-...dump`. Tried with invented files and a
throwaway key, 9 October 2026: the dump comes back identical.

### Restore a backup

Into a database that is truly empty. A new stack's database is not: its
first start builds the tables from `schema.sql`, and a restore on top of them
fails. So the database is emptied first, then the dump restored without its
grants (roles belong to the server, not to the dump) in one transaction, so
a failure leaves nothing half-restored. Then the ETL's role is made again.

This **replaces everything in the database**: on a stack that has records,
back up first and be sure. First list the dumps and choose one:

```
ls -1 ~/PSells-Backups/daily/
```

Then put its name in place of `psells-2026-10-09.dump` below and run it. It
is one chain: it does nothing unless that dump exists, stops the app and the
proxy so nothing writes meanwhile, and stops at the first step that fails, so
the database is never emptied without a dump to put in it:

```
dump=~/PSells-Backups/daily/psells-2026-10-09.dump && [ -s "$dump" ] && docker compose stop app proxy && docker compose exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\" OWNER \"$POSTGRES_USER\""' && docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-privileges --single-transaction --exit-on-error' < "$dump" && analytics/create-etl-role.sh && docker compose up -d --wait && ./refresh-analytics.sh && echo "restored from $dump"
```

Then log in and check the dashboard's figures. Tried on the sample stack, in
a throwaway project, 9 October 2026: the restore exits 0 and every row and the
corrections log's trigger come back.

### The certificates

Each morning's backup checks them (`check-certificates.sh`, also safe by
hand) and logs one `certificate` line each. A certificate within 30 days of
its end shows "PSells certificate expires soon", every morning until it is
renewed, naming the command below.

```
./check-certificates.sh
```

- **The Mac's**, `data/tls/psells.localhost.crt`, lasts 397 days. Renew it and
  restart nginx:

  ```
  ./make-certificate.sh && docker compose restart proxy
  ```

- **The cluster's**, in `~/PSells-Kind/tls`, the same way with
  `PSELLS_TLS_DIR=~/PSells-Kind/tls ./make-certificate.sh`, then `k8s/up.sh`.
- **The Mac's CA**, in `~/PSells-CA`, lasts five years. `make-certificate.sh`
  refuses to sign a certificate that would outlive it, so it is warned about
  30 days before it has 397 days left. Renew it in this order: put the old CA
  aside, make a new one with a new certificate, trust it (macOS asks for your
  password), and restart nginx.

  ```
  mv ~/PSells-CA ~/PSells-CA.old && ./make-certificate.sh && security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db ~/PSells-CA/ca.crt && docker compose restart proxy
  ```

  Then renew the cluster's certificate as above, if the cluster is used. Once
  `https://psells.localhost` opens without a warning, stop trusting the old
  CA and delete it:

  ```
  security remove-trusted-cert ~/PSells-CA.old/ca.crt && rm -r ~/PSells-CA.old
  ```

- **The demonstration's** is Let's Encrypt's, renewed by a timer twice a day.

### Rotate a password

- **The ETL's or the page's read-only role**: change the line in `.env`
  (`PSELLS_ETL_PASSWORD` or `PSELLS_READER_PASSWORD`, and the reader's inside
  `PSELLS_WAREHOUSE_URL` too), run the role's script, and rebuild the
  warehouse at once, since the script takes the role's grants away until the
  next build:

  ```
  analytics/create-reader-role.sh && ./refresh-analytics.sh
  docker compose up -d --wait --no-deps app
  ```

  (`analytics/create-etl-role.sh` for the ETL's; the app needs recreating
  only for the reader's.) Tried on the sample stack, 9 October 2026: the old
  password refused, the new one reading the views.
- **The demonstration's**: change the parameter under `/psells/postgres` in
  Parameter Store, then deploy; the deploy writes `.env` and the roles again.
- **The login**: `set_password.py`, above.

### Weekly

- **Dependabot** opens pull requests that raise a pinned version; the checks
  run on them. Merge one whose checks pass and whose version is newer than
  the pin (it has proposed an older nginx before; do not merge that).
- **The scan exception** for the monitoring agent's OpenSSL expires on the
  date in `monitoring/grype-exceptions.yaml`; from then the Image workflow
  fails until a fixed agent image is pinned or the exception renewed with its
  reason.
- **AWS**: the free plan's credits, and that the code still matches what
  runs:

  ```
  aws freetier get-account-plan-state --region us-east-1 --profile psells --query 'accountPlanRemainingCredits.amount'
  (cd infra/aws && AWS_PROFILE=psells terraform plan)
  ```

  Sign in first with `aws login --profile psells --remote` as the IAM user,
  never root.

## Incidents

Each is what you see, what to check, and what to do.

### A PSells notification appears

The Mac's three background jobs show a notification, with a sound, when they
fail, saying why, and the backup when a certificate nears its end:

- **"PSells backup failed"**: the local backup or its off-Mac copy. The log
  is `~/PSells-Backups/backup.log`. Fix the reason, then `./backup.sh` by hand
  and check its last lines say ok and offsite ok.
- **"PSells did not start"**: the login job. See "The site does not answer on
  the Mac" below.
- **"PSells certificate expires soon"**, **"expired"** or **"unreadable"**:
  from the morning backup's check, which the backup itself never fails on. The
  notification names the certificate and its renewal; see "The certificates"
  above.
- **"PSells analytics refresh failed"**: shown once, on the first failure
  after a run that worked, not every hour. See "The analytics page says the
  warehouse is more than two hours old" below.

A notification never carries a figure, only the job's reason.

### The site does not answer on the Mac

- **See**: the browser cannot reach `https://psells.localhost`.
- **Check**: Docker Desktop is running; `docker compose ps`;
  `tail ~/Library/Logs/psells-start.log`.
- **Do**: `./start-stack.sh`. If every container is healthy but the
  connection is reset, recreate nginx alone, which has fixed that before:
  `docker compose up -d --force-recreate --no-deps proxy`.

### Pages say the database cannot be reached (503)

- **See**: a page with a sentence that the database cannot be reached.
- **Check**: `docker compose ps db`; `docker compose logs --tail 50 db`.
- **Do**: `docker compose up -d --wait db`. The app reconnects by itself; it
  needs no restart.

### The analytics page says the warehouse is more than two hours old

- **See**: the warning above the figures.
- **Check**: `tail ~/Library/Logs/psells-etl.log` on the Mac, or on the
  server `journalctl -u psells-analytics.service --since -3h`. Each line says
  ok or the reason.
- **Do**: fix the reason (Docker down, the database unhealthy, the warehouse
  down), then `./refresh-analytics.sh`. "does not add up" means the
  warehouse and the dashboard disagreed and nothing was changed: report it;
  never edit the warehouse by hand.

### The demonstration's alert email arrives

- **See**: "site down" from Grafana: under half of the checks of `/login` are
  passing.
- **Check**: open the site; then a shell on the server, through Session
  Manager (no SSH exists):

  ```
  aws ssm start-session --profile psells --region ca-central-1 --target "$(cd infra/aws && AWS_PROFILE=psells terraform output -raw instance_id)"
  ```

  and there `cd /opt/psells && sudo docker compose -f compose.yaml -f
  compose.aws.yaml ps`, and the app's logs with `logs --tail 50 app` in place
  of `ps`.
- **Do**: as on the Mac, start what is stopped. The postmortem in
  `postmortems/` walks through one such outage. The resolved email follows
  by itself.

### A check is red for a reason outside the code

- **See**: a workflow failed on a commit that changed nothing near it, with
  an HTTP 500 or a download error in its log (GitHub has failed this way
  while the scanner downloaded itself).
- **Do**: rerun the failed jobs, by the run's number, which
  `gh run list --limit 10` shows; put it in place of `NUMBER`. Deploy follows
  when all five pass.

  ```
  gh run rerun NUMBER --failed
  ```

### A push is refused

- **See**: `ssh: connect to host github.com port 22`, often on a public
  network or a VPN.
- **Do**: push through GitHub's SSH on port 443 instead:

  ```
  git push ssh://git@ssh.github.com:443/pierremakhlouta/psells.git main
  ```

  A passphrase prompt after a restart means the key is not in the agent:
  `ssh-add --apple-use-keychain ~/.ssh/id_ed25519_2026`.

### The Kubernetes cluster misbehaves

It holds invented records only, so it is simply made again:

```
k8s/down.sh && k8s/up.sh
```

Tried: many times, 7 to 9 October 2026.

## Rebuilding from nothing

### A new Mac

1. Install Docker Desktop, Python 3.14, and from Homebrew OpenSSL, `gh`, the
   AWS CLI and its `session-manager-plugin`, Terraform, `kind` and `kubectl`;
   clone the repository; `python3 -m venv venv && venv/bin/pip install -r
   requirements-dev.txt`.
2. Put back what is not in the repository: `.env`, from `.env.example` with
   new passwords, and `data/config.json`, the real partner percentage, whose
   copy every backup carries beside its dump (`config-STAMP.json`; from the
   off-Mac copy, see "Restore from the off-Mac copy").
3. Make the CA and the certificate and trust the CA, as README's "The
   certificate" says: `./make-certificate.sh`.
4. Start the database alone, restore the latest dump as in "Restore a
   backup", then start the rest: `docker compose up -d --wait`.
5. Install the three launchd jobs (README: backups, "Starting the stack at
   login", Analytics), set up the warehouse and its roles (README:
   "Analytics"), and log in.

### The demonstration server

Terraform makes a new server, which sets itself up from `first-boot.sh` and
deploys the head of `main` with the invented records:

```
cd infra/aws && AWS_PROFILE=psells terraform apply -replace=aws_instance.server
```

It takes about ten minutes. The address and the certificate's name survive
it; the login does not, and is set again through Session Manager. Tried in
Phase 07, twice.

### The cluster

`k8s/down.sh && k8s/up.sh`, above.
