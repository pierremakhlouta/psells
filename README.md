# PSells

[![Tests](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/tests.yml)
[![Security](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/security.yml)
[![Lint](https://github.com/pierremakhlouta/psells/actions/workflows/lint.yml/badge.svg)](https://github.com/pierremakhlouta/psells/actions/workflows/lint.yml)

An inventory and profit tracker for my reselling business, used from a browser
or from the terminal.

PSells replaces the spreadsheet that used to run the business. It tracks the
products held, the sales made, stock returned to the supplying partner, and the
payouts made to that partner, and computes a live dashboard from all four.

## What it does

- Full inventory management: view, browse by category, search, add, edit, delete
- Records sales, returns to the partner, and partner payouts
- Does all of it from a browser, in server-rendered pages, or from the terminal
- Works out each item's partner cut from a rule set per item
- Computes stock levels, revenue, profit, and the balance owing to the partner
- Refuses to delete a product that has sales or returns against it
- Asks for a login before every page and endpoint, with a token in every form
- Runs as three containers, nginx in front of the application and a PostgreSQL
  database beside it, with one command
- Backs itself up daily, on a schedule, and proves each copy restores
- Runs a public demonstration on AWS, with invented records only, at
  `https://psells.lakeshorefreight.me`

Every figure that can be derived is computed on demand rather than stored, so no
total can drift out of sync with the records it came from. See
[DATA_MODEL.md](DATA_MODEL.md) for the structure and [DECISIONS.md](DECISIONS.md)
for why it is built this way.

## Requirements

Docker, with Compose. PSells runs as three containers: nginx, which is the only
one reachable from outside the stack and passes every request on; the
application behind it, which serves the web pages and the HTTP API and also
holds the terminal application; and a PostgreSQL 18 database beside that.
Everything the application needs is installed inside its image.

Working on it also needs Python 3 on the machine, for the tests:

    pip install -r requirements-dev.txt

`requirements.txt` lists what the application needs to run: FastAPI, uvicorn,
Jinja2 for the templates, python-multipart to read form posts, psycopg, the
PostgreSQL driver, and argon2-cffi, which hashes the login password. `requirements-dev.txt` adds pytest, httpx2 for the test
client, PyYAML so a test can read `compose.yaml`, and openpyxl for
`import_excel.py`, the one-time script that read the original spreadsheet.

## Running it

Settings, including the database password, live in `.env` beside
`compose.yaml`. It is gitignored and kept out of every image. Start from the
template, set a real password, and point `PSELLS_CONFIG_FILE` at the
configuration file holding the default partner percentage:

    cp .env.example .env
    openssl rand -hex 24      # paste the result as POSTGRES_PASSWORD in .env

The first time, make the HTTPS certificate and trust its CA, as described under
"The certificate" below:

    ./make-certificate.sh

Then:

    docker compose up --build -d --wait

The first start creates the database and builds its tables from `schema.sql`.
Then create the account, once. It asks for a username and for the password
twice, without showing it; the password must be at least fifteen characters:

    docker compose exec app python set_password.py

Open `https://psells.localhost/` and log in. The same command changes the
password later, and logs out every browser that was logged in. No web page can
change it. The terminal application runs inside the same container, against
the same database, and needs no login, because reaching it already takes
access to the containers:

    docker compose exec app python psells.py

    0: Quit
    1: View Dashboard
    2: View Inventory
    3: List Categories
    4: Search
    5: Add
    6: Edit
    7: Delete
    8: Record Sale
    9: Record Return
    10: Record Payment

Search matches a product name or a category, so typing a category returns
everything in it. Choosing a product to sell, edit or delete matches on the name
only, deliberately, so that an action is never offered against a whole category
at once.

`docker compose down` stops both containers and keeps the data.
`docker compose down -v` deletes it.

The application reads two settings from its environment, and Compose sets both:

    PSELLS_DATABASE_URL   the PostgreSQL database, with no default
    PSELLS_CONFIG         the JSON configuration file, mounted read-only

Without a database address, or with one that does not answer, the application
stops with a sentence saying so rather than a stack trace.

## Trying it with sample data

The real data is not in this repository. Everything under `data/` is gitignored,
because this tracks a real business and its prices, margins and commercial terms
do not belong in a public repository.

To see the application working, run a second copy of the stack under its own
project name, `psells-sample`, so it gets a database volume of its own and can
never touch the real one, load the invented records into it, and give it the
sample configuration. From the project folder, with `.env` in place:

    PSELLS_NETWORK=10.213.48 PSELLS_CONFIG_FILE=./sample_data/config.json docker compose -p psells-sample up --build -d --wait
    docker compose -p psells-sample exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" "$POSTGRES_DB"' < sample_data/seed.sql

Then create an account in it with
`docker compose -p psells-sample exec app python set_password.py`, open
`https://psells.localhost/` and log in, or run the terminal application with
`docker compose -p psells-sample exec app python psells.py`. When finished,
remove it and its database:

    docker compose -p psells-sample down -v

`PSELLS_CONFIG_FILE` is set on the command itself rather than in `.env`, so the
real stack goes on reading the real configuration. The percentage in
`sample_data/config.json` is a placeholder, not the real figure.
`PSELLS_NETWORK` gives the sample stack its own address range, because two
stacks cannot share one and the real stack keeps its network while it is
stopped. Only one of the two stacks can hold ports 443 and 80 at a time. Both
use the same certificate from `data/tls/`.

The sample set is small and invented, but it covers the cases worth seeing: all
three partner-share modes, a product discontinued at retail, one that has sold
out, a return, and two partner payments.

## The web interface

Served at `https://psells.localhost/`, through nginx, by the `app` container
behind it. One process serves the pages and the API.

- **Inventory**, the home page: the nine dashboard figures above a table of
  every product with its stock, listed price, partner cut and retail status, and
  a search box that matches name or category.
- **Add** and **Edit** a product. The edit form opens filled in; a field emptied
  there is cleared, unlike the command line, where Enter keeps the current value.
- **Sell**, **Return** and **Edit** from each row with stock, **Record payment**
  from the navigation, and **Delete** from a product's edit page.

The pages are a view, not a second implementation, and three rules keep them
one. A page route calls the same `psells` functions the command line calls and
does no arithmetic on money, stock or partner share. Wherever a page shows a
figure the API also serves, a test asserts the two agree. And templates format
and never compute, which a test enforces by parsing every template and failing
on any arithmetic or any filter other than the one that formats money.

Every form answers a successful save with a 303 redirect, so refreshing the page
afterwards cannot repeat it. A refusal shows the form again with a sentence
beside each field that is wrong and everything already typed kept: 422 when what
was typed is wrong in itself, 409 when it was fine and the stock disagrees.

### Logging in

Every page asks for a login first, except the login page itself. A wrong
password and an unknown username get the same sentence. A login lasts until two
hours pass without a request, or twelve hours after it began, whichever comes
first; **Log out**, in the header of every page, ends it at once. The password
is stored only as an Argon2id hash, and the session only as a hash of the
value in the browser's cookie, so neither the database nor a backup holds
anything that would log someone in. The cookie is `__Host-psells_session`:
sent over HTTPS only, unreadable by scripts, and not sent with another site's
form posts. nginx allows five login attempts a minute from one address, with a
burst of five, and answers 429 past that.

Every write is checked twice, independently. Every form carries a hidden token
belonging to the login session, and a write without it is refused with a 403.
And any write that a browser labels as coming from another site is refused with
a 403 before any route runs, including one sent from another server on the same
machine; that check is what covers the login form, which has no session yet.
See [DECISIONS.md](DECISIONS.md) for the reasoning behind each.

## The HTTP API

`api.py` serves the same data over HTTP. It is another way in, not another
application: every figure it returns comes from the functions the command line
uses, and it works nothing out for itself. It is served by the same uvicorn
process as the pages. `https://psells.localhost/openapi.json` describes every
endpoint with its fields and types, generated from the code. FastAPI's
interactive pages for it, `/docs` and `/redoc`, are turned off: they load their
JavaScript from a CDN pinned only to a major version, and would run it on the
same site as the forms.

    GET  /products    every product, with stock and the partner cut per unit
    GET  /dashboard   the nine dashboard figures
    POST /sales       record one sale
    GET  /session     the form token of the session asking

All money is sent and received as a whole number of cents, never as dollars and
never as a formatted string. That matches how it is stored, keeps every value
exact, and leaves formatting to whatever is showing it to a person.

The API takes the same login as the pages: the session cookie from logging in
at `/login`. Without it, every endpoint, `/openapi.json` included, answers 401
with `{"detail": "Log in first."}`. A write also needs the session's form token
in an `X-Form-Token` header, which `GET /session` returns. With curl:

    curl --cacert ~/PSells-CA/ca.crt -c jar -d username=... -d password=... https://psells.localhost/login
    TOKEN=$(curl -s --cacert ~/PSells-CA/ca.crt -b jar https://psells.localhost/session | python3 -c 'import json,sys; print(json.load(sys.stdin)["form_token"])')
    curl --cacert ~/PSells-CA/ca.crt -b jar -H "X-Form-Token: $TOKEN" -H 'Content-Type: application/json' \
        -d '{"item_id": 1, "quantity": 1, "sale_price_cents": 9000}' https://psells.localhost/sales

To try it against invented records rather than the real ones, use the sample
stack above.

## Changing the schema of an existing database

`schema.sql` builds the tables only when the database is first created, so a
table added to it later never reaches a database that already exists. Each
such change is also written as a file in `migrations/`, applied once, by hand,
after a backup:

    ./backup.sh
    docker compose exec -T db sh -c \
        'psql -v ON_ERROR_STOP=1 --single-transaction -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
        < migrations/0001_authentication.sql

`--single-transaction` makes it all or nothing and `ON_ERROR_STOP` stops it at
the first error, so running one twice stops at "already exists" and changes
nothing. `0001_authentication.sql` adds the `users` and `sessions` tables and
touches nothing else; a database created from the current `schema.sql` already
has them. `tests/test_schema.py` builds a database both ways and fails if the
two differ.

## Moving from SQLite

`migrate_to_postgres.py` moved the records out of the SQLite file PSells used
before PostgreSQL, once, in Phase 04. It reads a copy of that file read-only,
refuses a database that already holds records, and refuses a source that fails
SQLite's own integrity or foreign key checks. It copies every row with its id,
moves each table's sequence past the highest one, and then checks the result
against the source before committing anything: every row and column, every
product's derived stock and partner cut, and all nine dashboard figures, each
worked out by the same functions on both sides. Money is whole cents on both,
so the comparison is exact. Any difference rolls everything back.

It runs in a one-off container of the app service, because the database
publishes no port, with the script and the copy mounted read-only:

    docker compose run --build --rm \
        -v "$PWD/migrate_to_postgres.py:/app/migrate_to_postgres.py:ro" \
        -v "/path/to/copy-of-psells.db:/migrate/psells.db:ro" \
        app python migrate_to_postgres.py /migrate/psells.db

It prints row counts and a verdict, never a figure. `tests/test_migrate.py`
runs it against a SQLite file built from the old schema, kept in
`tests/sqlite_schema.sql` for that purpose only.

## How the containers are built

The `Dockerfile` builds an image holding the code and nothing else. The records
live in the database container, and the configuration file is mounted into the
application at `/config/config.json`, read-only, so an image never carries a
record. It names every file it copies rather than copying the folder, and
`.dockerignore` keeps `data/` and `.env` out of the build altogether.

nginx is the only service that publishes ports: 443 for HTTPS and 80, which
only redirects to it, both on `127.0.0.1`, forwarded to 8443 and 8080 inside
its container. Publishing them on `127.0.0.1` is what keeps them to this
machine. Leaving out the `127.0.0.1:` publishes them to the whole network, so
anyone on the same Wi-Fi could reach the login page and start guessing.
nginx runs the Docker Official Image, in its slim variant with none of the
add-on modules, as its own unprivileged user, never root,
with its whole configuration in `nginx/nginx.conf`, mounted read-only, and the
certificate and key mounted read-only from `data/tls/`.

What differs from one place PSells runs to another is not in `nginx.conf`: the
name it answers to, its certificate, and what plain HTTP does live in a folder
per place under `nginx/sites/`, `localhost` on the Mac and `aws` on the server,
and `nginx.conf` includes the two files of whichever folder is mounted. Every
header, limit and rule is in `nginx.conf` once, the same everywhere.

HTTPS ends at nginx, TLS 1.3 only. It answers for `psells.localhost` and no
other name: an HTTPS handshake for another name is refused, a request that
names another host only in its `Host` header gets 421, and plain HTTP for any
name is redirected to `https://psells.localhost` with the path kept. That is
what stops DNS rebinding, where a hostile site points its own name at
`127.0.0.1` so the browser reads these pages as if they were that site's. It
passes every request to the application over the private network Compose
creates, as plain HTTP, with the `Host` the browser sent and with
`X-Forwarded-Proto` and `X-Forwarded-For` set to what nginx itself saw, so a
client cannot supply its own.

Every response from PSells carries four headers set by nginx:
`Strict-Transport-Security` for a year, so a browser that has visited once
never tries plain HTTP for `psells.localhost` again; a `Content-Security-Policy`
that allows no scripts at all, only the one style block in `templates/base.html`
by the hash of its text, forms that post only to PSells, and no framing by
another site; `X-Content-Type-Options: nosniff`; and `Referrer-Policy:
same-origin`. nginx does not name its version, and refuses a request body over
64 KB with a 413. Changing the style block in `base.html` changes its hash, and
a test then fails with the new hash to put in `nginx/nginx.conf`.

`nginx/nginx.conf` is read from this folder, not from an image, so the running
nginx takes a change to it the next time it starts or reloads, whatever version
of the application is running. A change to the style block therefore reaches
the stack as one release: rebuild the application with it
(`docker compose up --build -d --wait`), rather than restarting nginx alone. A
change to `nginx.conf` only is applied with:

    docker compose exec proxy nginx -t && docker compose exec proxy nginx -s reload

`curl` does not use the macOS keychain, so it is told about the CA directly:

    curl --cacert ~/PSells-CA/ca.crt https://psells.localhost/

The application publishes no port. Inside its container uvicorn listens on
`0.0.0.0`, because traffic from another container arrives on the container's
network interface, not its loopback. It believes `X-Forwarded-Proto` and
`X-Forwarded-For` from nginx's address only, set as `FORWARDED_ALLOW_IPS`. That
is why the stack's network has a fixed range, `10.213.47.0/24`, with nginx at a
fixed address outside the part Docker hands out. If the range ever clashes
with a network the Mac is on, `PSELLS_NETWORK` in `.env` moves it.

The three services restart whenever Docker starts (`restart: unless-stopped`),
so PSells comes back after Docker Desktop restarts or the server reboots; a
container stopped on purpose with `docker compose stop` stays stopped.

`--wait` returns once every service reports healthy: the database when it
accepts connections, the web server when uvicorn does, and nginx when it
answers its own health check. Without it, a request
made straight after `up` can get an empty reply, because Docker accepts a
connection on the published port before the server inside is listening.

The database publishes no port at all: only the application reaches it, over
the private network Compose creates, and
`docker compose exec db psql -U psells psells` is the way to a SQL prompt. Its
files live in a Docker volume named `psells_pgdata`, not in this folder. The
application's address for it is assembled in `compose.yaml` from the same
values in `.env` the database is created with, so the password is written once.
`tests/test_container.py` holds all of this in place.

## The certificate

PSells is served over HTTPS at `https://psells.localhost`, with a
certificate from a certificate authority of its own rather than a public one,
because a public one needs a public name. `make-certificate.sh` makes both:

    ./make-certificate.sh

The first run creates the CA in `~/PSells-CA`, outside the project, readable by
you only. Its certificate can sign for `psells.localhost` and nothing else:
its name constraint permits that one name and excludes every IP address, so
its key could not be used to impersonate any other site even if it leaked. It
lasts five years. The script then prints the command that tells macOS to trust
it, once, for your user:

    security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db ~/PSells-CA/ca.crt

Safari and Chrome use that trust; Firefox keeps its own list.

Every run signs a new certificate for `psells.localhost` with that CA, into
`data/tls/`, which git and the Docker build both ignore. It lasts 397 days,
inside the limit browsers apply to public certificates, so renewing is
running the script again, with nothing to change in the keychain. nginx reads
both files when it starts, so after renewing:

    docker compose restart proxy

The script refuses to sign a certificate that would outlive its CA, and
replaces the old certificate only once the new one verifies.

`.localhost` names always mean this machine, and Safari, Chrome and curl find
`psells.localhost` without any change to `/etc/hosts`.

The AWS server has a certificate from Let's Encrypt instead, which every
browser trusts; see "The demonstration on AWS" below.

## Backups

`backup.sh` takes a `pg_dump` of the database in the Compose stack into
`~/PSells-Backups/daily/`, logs the result to `~/PSells-Backups/backup.log`, and
removes copies older than thirty days. It carries `data/config.json` along,
because the partner rate is in no repository and the application will not
start without it.

Every dump is proved before anything old is deleted: it is restored into a
throwaway database on the same server, its products are counted and compared
with the live database, and the throwaway is dropped. A dump that does not
restore, or restores empty, or disagrees, is logged as `FAILED` with the
reason, and nothing is removed. A backup that is valid and empty is worse than
no backup, because it looks fine in a listing.

If the database container is not running, the script starts it, and only it;
if Docker Desktop is not running, it waits two minutes and then logs that it
could not reach the database.

Run it by hand:

    ./backup.sh
    tail -1 ~/PSells-Backups/backup.log

Or daily at 09:00 through launchd, macOS's own scheduler. The job file is
`launchd/local.psells.backup.plist`, a template with its paths filled in on
install. From the project folder:

    sed -e "s|__PROJECT_DIR__|$PWD|" -e "s|__HOME__|$HOME|" \
        launchd/local.psells.backup.plist > ~/Library/LaunchAgents/local.psells.backup.plist
    launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/local.psells.backup.plist

launchd rather than cron because a Mac asleep at 09:00 runs the backup when it
wakes; cron skips the day. A Mac that is shut down still misses it.

To restore a dump into the stack's database, which must be empty:

    docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --exit-on-error' \
        < ~/PSells-Backups/daily/psells-<date>.dump

Every copy of the real database is on the same disk as it. The demonstration
server's backups go to S3, described below, but they hold invented records
only: the real data never leaves the Mac.

## The demonstration on AWS

A copy of PSells runs at `https://psells.lakeshorefreight.me`, on one small
EC2 server in AWS's Montreal region, holding the invented records from
`sample_data/seed.sql` and the placeholder partner percentage, never the real
ones. It exists to show the system running in the cloud, and it costs nothing:
the account is on AWS's free plan, which cannot be charged, and the server
lives inside that plan's six months.

It is the same stack, with `compose.aws.yaml` laid over `compose.yaml`. That
file holds everything that differs on the server: the application's image,
published by CI and pulled by digest rather than built there, ports 443 and 80
published on every address rather than `127.0.0.1`, the `aws` site folder for
nginx, a Let's Encrypt certificate in place of the Mac's own CA, the folder
Let's Encrypt's challenge is answered from, and a `certbot` service run only
when asked for. The Mac never reads it.

How it is put together:

- **No SSH.** The server's firewall lets in ports 80 and 443 and nothing else.
  A shell on it comes through AWS Systems Manager Session Manager, signed in
  with the same short-lived credentials as the AWS CLI, and nobody holds an
  SSH key.
- **No long-lived keys.** The CLI signs in with `aws login`, which gives
  credentials that last hours, not an access key. The server itself acts
  through its IAM role, which may read the database parameters and the backup
  bucket's name, add backups to that bucket, and do nothing else: it cannot
  read, list or delete what is already there.
- **Secrets in Parameter Store.** The database password is a `SecureString`
  under `/psells/postgres`, generated there and never written in the
  repository. `deploy/aws/deploy.sh` writes `.env` from it on each deploy,
  readable by root only.
- **The certificate.** certbot, pinned like every other image, gets it and
  renews it through the webroot nginx serves on port 80, twice a day from a
  systemd timer, and nginx reloads afterwards. certbot runs as nginx's own
  user, so the private key is readable by its owner only and its owner is the
  one process that reads it.
- **Backups.** Once a day `deploy/aws/backup-to-s3.sh` dumps the database,
  proves the dump restores, as `backup.sh` does, and only then copies it to a
  private, encrypted S3 bucket that deletes each copy after thirty days.

### Shipping from a push

A push to `main` goes live by itself, in about four minutes, once every check
has passed:

1. **Image** builds the application's image on amd64 and on arm64, the
   server's architecture, scans each, and publishes the scanned images to
   GitHub's container registry as `ghcr.io/pierremakhlouta/psells:<commit>`.
   The scanner runs in a job that can publish nothing; a separate job, which
   runs no third-party code, pushes each image only if its ID is the one that
   was scanned.
2. **Deploy** starts whenever Tests, Lint, Security or Image finishes on
   `main`, and its gate goes on only when all four have passed for that exact
   commit. A failed check means no deploy; a scheduled scan deploys nothing.
3. It signs in to AWS with GitHub's OpenID Connect token, which AWS trades for
   a role trusted only by `main` of this repository, for fifteen minutes. No
   AWS key is stored in GitHub.
4. That role can run one thing: the SSM document `psells-deploy`, on the
   server tagged `psells`. The document accepts a full commit hash and an image
   digest, each checked by AWS against a pattern before anything runs, checks
   out the commit and runs `deploy/aws/deploy.sh`, which pulls the image by
   digest and refuses one that is not that commit's own.
5. The workflow fails unless the server reports running exactly that digest
   and the site answers over trusted HTTPS.

Rolling back is the same workflow run by hand with an earlier commit on
`main`, which redeploys that commit's own scanned image, in under a minute:

    gh workflow run deploy.yml -f commit=<full hash of an earlier commit>

It refuses a commit whose checks did not all pass. By hand on the server, as
root through Session Manager, a deploy is:

    git -C /opt/psells fetch --quiet origin
    git -C /opt/psells checkout --quiet --detach <commit>
    PSELLS_IMAGE_DIGEST=<its digest> /opt/psells/deploy/aws/deploy.sh

`deploy.sh` and `backup-to-s3.sh` refuse to run where `data/config.json`
exists, which is only ever the Mac, so neither can overwrite the real `.env` or
send the real records anywhere.

### The server as code

Everything the demonstration uses in AWS is described in Terraform in
`infra/aws/`: the server and its fixed address, the firewall, the server's
role and its two policies, the backup bucket and its settings, the plain
parameters, the account's default of encrypted disks, and the budget. Only
the IAM user Terraform runs as, its group and the root user are left out, so
a mistake in a plan can never remove the access that runs it, and the
database password, because Terraform keeps a copy of every value it manages
in its state, in plain text.

The state lives in an S3 bucket of its own, private, encrypted, versioned and
locked while a plan runs. That bucket is made once by `infra/aws/bootstrap/`,
a small configuration whose own state stays on the machine that ran it. From
`infra/aws/`, signed in with `aws login`:

    AWS_PROFILE=psells terraform init
    AWS_PROFILE=psells terraform plan

A plan that reports no changes is the proof that the code describes what is
running. The address the budget's alerts go to is read from
`infra/aws/terraform.tfvars`, which git ignores:

    alert_email = "you@example.com"

A new server sets itself up. Terraform gives it `deploy/aws/first-boot.sh`,
which prepares the host, clones this repository and runs `deploy.sh`, which
now also fetches a certificate from Let's Encrypt when the server has none.
Rebuilding the server from code is therefore one command, and the address,
the name and the certificate's name survive it:

    AWS_PROFILE=psells terraform apply -replace=aws_instance.server

It takes about ten minutes, most of it installing Docker and pulling images;
the application's image is the one CI published for the head of `main`. A rebuilt server starts with the sample records and no
account, so the demonstration's password is set again through Session
Manager. `-var acme_staging=true` asks Let's Encrypt's staging service
instead, whose certificates no browser trusts and which has no weekly limit,
for trying a rebuild.

`terraform destroy` is the cost control: it removes everything above. It
stops at the backup bucket while the bucket holds backups, rather than
deleting them, and it leaves the state bucket and the database password,
which it does not manage.

The Lint workflow checks the formatting of every configuration and validates
each one against the provider the lock file pins, without reaching AWS. The
deploy role and the `psells-deploy` document are in `infra/aws/deploy.tf`.

## Running the tests

The suite needs a PostgreSQL to run against: `db-test` in `compose.yaml`, a
throwaway database that holds invented rows in memory, shares nothing with the
real one, and is published on `127.0.0.1:5433`. Start it once, then run pytest
as often as you like:

    pip install -r requirements-dev.txt
    docker compose --profile test up -d --wait db-test
    pytest
    docker compose --profile test stop db-test

Without it, pytest stops at once with one line saying how to start it, rather
than skipping the database tests and reporting a pass. The suite wipes the
database it is pointed at, so it refuses any whose name does not end in
`_test`. `PSELLS_TEST_DATABASE_URL` points it somewhere else.

Every warning is an error (`pytest.ini`), apart from one known deprecation in
Starlette's test client on Python 3.14, matched on its exact message.

Sixteen files, and the split is deliberate, so a red run says what kind of
thing broke before you read a line of it.

`test_domain.py` covers everything in `psells.py` that has no input or output:
partner-share in all three modes including its rounding, search, the dashboard
totals, the derived stock quantities, money formatting, and every write with its
rules (`create_product`, `update_product`, `create_sale`, `create_return`,
`create_payment`, `delete_product`) and the readers that turn a form's text into
their values.

`test_features.py` covers the ten menu functions end to end. They prompt and
print, so input is faked with pytest's `monkeypatch` and output is read back
with `capsys`. Each test queues one answer per question, which makes the length
of that queue a claim about how many questions the function asks: if it ever
asks one more, the queue runs dry and the test fails rather than hanging.

`test_api.py` drives the HTTP endpoints through FastAPI's test client, with the
connection dependency pointed at the test's own connection. That client is
logged in, with a session made directly, so tests about something else do not
depend on the login page.

`test_auth.py` covers `auth.py` and `set_password.py`: Argon2id hashing, a
refusal that takes as long for an unknown username, the upgrade of an old hash,
and a session's two limits, each tested to the second on both sides with a
fixed clock.

`test_login.py` asks the application for every route it has and calls each one
without a session, so a route added later is covered the day it is added, and
fails if any route sits outside the checks. It also covers the login page, the
cookie's attributes, and logging out.

`test_forms.py` does the same for the form token: it reads every template and
renders every page for a form without the token, and calls every write with no
token, a wrong one and another session's.

`test_web.py` drives the pages the same way, reading each page with small
parsers built on the standard library, so an assertion names a cell in a row
or a field in a form rather than finding a string somewhere on the page. Its
tests submit through the forms the pages actually serve, and compare what the
pages show with what the API serves.

`test_cross_site.py` covers the refusal of writes from another site, directly
and behind nginx, with uvicorn's own proxy-header handling wrapped around the
application as it is in the stack.

`test_schema.py` runs `schema.sql` on its own: every rule tried with a row that
breaks exactly that rule and refused by that rule's own constraint, ids never
reused, the view's derived stock, the Python types each column comes back as,
and that each file in `migrations/` builds exactly what `schema.sql` builds.

`test_connect.py` covers `psells.connect`: that a write through it is really
committed, and that a missing or silent database is a sentence.

`test_migrate.py` runs the one-time move out of SQLite against a SQLite file in
the old shape, including every way it can refuse.

`test_backup.py` holds the launchd job that runs `backup.sh`: that it parses,
runs the script daily at 09:00, and carries no personal paths.

`test_tls.py` runs `make-certificate.sh` into a temporary folder with the
`openssl` on the machine, and proves the CA's limit by having it sign
certificates for other names and for IP addresses, each of which must be
refused.

`test_deploy.py` runs copies of `deploy/aws/deploy.sh` and
`backup-to-s3.sh` in a temporary folder with stand-in `docker` and `aws`
commands, and fails if either would do anything where `data/config.json`
exists, or `deploy.sh` anywhere but the server's folder. It also checks the
server gets the sample configuration only, that a backup is proved before it
is sent, and that the systemd timers agree with `compose.aws.yaml` and with
the script that installs them. It also checks that a certificate is fetched
only when there is none, before the stack starts, and that `first-boot.sh`
deploys only after every step that prepares the host.

`test_infra.py` reads the Terraform in `infra/aws/` and fails if a state or
variables file could be committed, if the provider is not pinned to one exact
version the lock file agrees with, if the state bucket could be destroyed or
lose its versions, if the code holds a secret, an address, an account number,
a resource ID or a leftover import block, if the firewall would let in
anything but 80 and 443, if the server could have a key pair, reach IMDS from
a container or run up CPU charges, if its role could do more than it does, or
if the deploy role could be taken by another branch or repository, send
anything but the deploy document or reach any server but PSells'.

`test_container.py` reads the `Dockerfile`, `.dockerignore`, `compose.yaml`,
`compose.aws.yaml`, `nginx/nginx.conf` with each site's files, and the
workflows, and fails if the image could ever be
built from the whole folder or from `data/`, if it leaves out a module the
server imports, if any port is published beyond this machine, if the
application or the database publishes a port at all, if a password is written
into `compose.yaml`, if nginx stops passing the headers the application relies
on with the values it relies on, if the application would believe forwarded
headers from anyone but nginx, if nginx would run as root, if a response would
lack one of its security headers or the policy's style hash no longer matches
the page, if the login limit stops counting only login attempts, if an action or an
image is used by a tag rather than pinned to a commit or a digest, or if a
workflow can write to the repository. On the server's side it fails if
`compose.aws.yaml` stops replacing the ports, the site or the certificate, or
if certbot would write anywhere nginx does not read or as another user, if
any job but the one without third-party code could publish the image or it
could publish an image other than the scanned one, or if the Deploy workflow
could skip a check, hold a key, run an action, write an event's value into a
script, or pass without confirming the digest and the site. The
Lint workflow also runs `nginx -t` on the configuration, with each site, with
the image the stack uses, and `terraform fmt` and `validate` on every
configuration.

No test needs a data file. The suite builds its tables from `schema.sql` at the
start of every run, so a constraint added there is exercised automatically, and
every test runs inside a transaction that is rolled back at the end, so tests
never see each other's rows and nothing has to be cleaned up. On GitHub Actions
the test database is a service container of the same image, on the same
port. Everything runs on every push through GitHub Actions, alongside a
dependency vulnerability audit, a shellcheck pass and an `nginx -t` check, and
a scan with Grype of the built image, on both architectures, and of the nginx
image, which fails on a high or critical vulnerability that has a fix and
lists the rest, and a scan of every commit in the history with gitleaks, which
fails on anything that looks like a credential. On `main`, the scanned image is
then published and deployed, as described under "Shipping from a push".

Everything is pinned: Python packages to exact versions, every action in the
workflows to a commit, and the base images to a version and the digest of
their contents, so a tag moved after the fact cannot change what runs.
Dependabot checks every pin weekly and opens a pull request when one has a
newer release, which the same workflows then test and scan.

## Known limitations

Worth stating plainly rather than leaving to be discovered.

- **The login is a password and nothing else.** One account, a minimum of
  fifteen characters, no second factor. Argon2id makes each guess expensive and
  nginx limits how many arrive; a long passphrase is still the real
  protection. On the Mac it is published on `127.0.0.1` only; the
  demonstration server's login is public, in front of invented records.
- **Behind Docker Desktop, every browser on the Mac shares one login
  allowance.** nginx sees every connection as coming from Docker's gateway, so
  the five attempts a minute are counted for the machine, not for a browser.
  On a Linux server each visitor's own address is counted.
- **The Mac's certificate is trusted by the Mac only.** It comes from a CA of
  PSells' own, which other machines, and Firefox, do not trust. The
  demonstration server's certificate, from Let's Encrypt, is trusted everywhere.
- **On the server, nginx's user number is also a system account's.** The
  private key belongs to user 101, nginx's user inside its container, and on
  the Ubuntu host number 101 is the `uuidd` service's account, which could
  therefore read it. Worth closing with user-namespace remapping if the server
  ever held anything real.
- **The demonstration is temporary.** AWS's free plan ends six months after the
  account was opened, in March 2027, and the server with it. The repository,
  and the Terraform that rebuilds the server, are what last.
- **A rebuilt server forgets its account.** It starts from the sample records
  with no login, and the password is set again by hand, since it is typed and
  never stored.
- **The stack comes back only when Docker does.** The three containers restart
  whenever Docker starts, after Docker Desktop restarts or the server reboots,
  but on the Mac Docker Desktop itself has to be running: if it does not start
  at login, neither does PSells, and neither does the daily backup.
- **Behind Docker Desktop, the application never sees a client's address.**
  Every request reaches nginx from the Compose network's gateway, so that is the
  address logged and forwarded. Harmless while everything is on one machine.
- **The API can read and sell, and nothing else.** Every other write is in the
  web pages and the command line. More write endpoints wait for a program that
  needs them, and so do API keys; until then a program logs in with the same
  cookie as the browser.
- **Two rules live in the application rather than the database.** Available stock
  never going negative, and an intake quantity never being edited below what has
  already sold and returned, both span more than one table, and a `CHECK`
  constraint can only look at the row it is checking, in PostgreSQL as in
  SQLite.
- **Notes cannot be cleared from the command line.** In its edit, a blank answer
  means keep the current value, so a note that has text cannot be blanked there.
  The web edit page can clear it.
- **One prompt in edit does not accept a blank answer.** Every field takes Enter
  to keep the current value, except the question asking whether to change the
  partner share, which requires an explicit yes or no.
- **A partner share of zero is accepted.** Deliberate, because at least one real
  item is owned outright.
- **Corrupt input files are only partly handled.** A missing or malformed
  configuration file exits cleanly with a message, and so does a database that
  is missing or does not answer. A database that fails partway through does not.
- **`migrate_to_sqlite.py` no longer runs.** It is the one-time script that moved
  the data out of JSON files, kept as the record of how that was done. It was
  written against the code as it stood before the move and is not maintained.
  `migrate_to_postgres.py` is kept, and tested, for the same reason.

## Where this is going

PSells is built one layer at a time as a long-running project rather than a
finished product. It stores its data in PostgreSQL behind a schema that
enforces the business rules, runs as containers under Compose, is used through
server-rendered web pages, a terminal application and an HTTP API that all call
the same functions, is served over HTTPS behind nginx, asks for a login before
anything else, is covered by an automated test suite that runs on every push
against a real PostgreSQL, and is backed up on a schedule. A copy with
invented records runs on AWS behind a publicly trusted certificate, described
in Terraform and rebuilt from it, and a push to `main` ships itself there once
every check passes. Planned next is monitoring: a dashboard of the server and
the application, service level objectives, an alert, and a deliberate failure
written up as an incident, carrying the same data model and business rules
through each step.
