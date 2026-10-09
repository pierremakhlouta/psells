# Decisions

PSells is an application for tracking a reselling business: the products held,
the sales made, items returned to suppliers, and payouts to a partner. This file
records the notable design choices and why; see the README for what the project
is and DATA_MODEL for how the data is structured. Kept short, the interesting
calls only, not every detail, and no specific business figures.

## Index by area

Every decision below, grouped by what it concerns. The decisions themselves
follow in the order they were made, which is kept because the reasoning
often depends on what came before. One later replaced, in whole or in
part, says so in its last line and points to what replaced it.

### Data and business rules

- [Store facts, compute the rest](#store-facts-compute-the-rest)
- [People use names, the program uses IDs](#people-use-names-the-program-uses-ids)
- [History stays fixed](#history-stays-fixed)
- [Discontinued items are marked, not inferred](#discontinued-items-are-marked-not-inferred)
- [The spreadsheet was cleaned before it was imported](#the-spreadsheet-was-cleaned-before-it-was-imported)
- [Money is stored as whole cents](#money-is-stored-as-whole-cents)
- [Money is compared with a tolerance only where it is still a fraction](#money-is-compared-with-a-tolerance-only-where-it)
- [Nothing derived is stored, including how many units have sold](#nothing-derived-is-stored-including-how-many-units-have)
- [The retail-discontinued flag says what it means](#the-retail-discontinued-flag-says-what-it-means)
- [The partner-share value became two columns](#the-partner-share-value-became-two-columns)
- [Deleting a product with history is refused](#deleting-a-product-with-history-is-refused)
- [The schema carries the rules it can carry, and says which it cannot](#the-schema-carries-the-rules-it-can-carry-and)
- [Browsing matches widely, choosing a product does not](#browsing-matches-widely-choosing-a-product-does-not)
- [In stock and out of stock are two lists of one set of products](#in-stock-and-out-of-stock-are-two-lists)
- [Why a product ran out is worked out, not recorded](#why-a-product-ran-out-is-worked-out-not)
- [A confirmation finds its product wherever it now is](#a-confirmation-finds-its-product-wherever-it-now-is)
- [The history shows each sale as it was recorded](#the-history-shows-each-sale-as-it-was-recorded)
- [A wrong record is corrected, and the correction is kept](#a-wrong-record-is-corrected-and-the-correction-is)
- [A corrected quantity follows the rule entering it followed](#a-corrected-quantity-follows-the-rule-entering-it-followed)
- [A correction is confirmed, and an empty one is not logged](#a-correction-is-confirmed-and-an-empty-one-is)

### Storage and the database

- [JSON, then SQLite](#json-then-sqlite)
- [Ids may be reused, until PostgreSQL](#ids-may-be-reused-until-postgresql)
- [PostgreSQL only, and the tests run on it](#postgresql-only-and-the-tests-run-on-it)
- [The application's connection commits every write](#the-applications-connection-commits-every-write)
- [The types were chosen to change nothing](#the-types-were-chosen-to-change-nothing)
- [The move from SQLite was one transaction, checked before it committed](#the-move-from-sqlite-was-one-transaction-checked-before)
- [Schema changes to an existing database are migration files, applied by hand](#schema-changes-to-an-existing-database-are-migration-files)
- [PostgreSQL is ready when it answers over TCP](#postgresql-is-ready-when-it-answers-over-tcp)

### Code structure and tests

- [The application became importable](#the-application-became-importable)
- [Calculations were separated from printing](#calculations-were-separated-from-printing)
- [Tests fake the commercial terms rather than reading them](#tests-fake-the-commercial-terms-rather-than-reading-them)
- [Tests and the dependency audit are separate automated workflows](#tests-and-the-dependency-audit-are-separate-automated-workflows)
- [The test runner is pinned, the security scanner is not](#the-test-runner-is-pinned-the-security-scanner-is)
- [The sample data is a SQL seed file, not JSON](#the-sample-data-is-a-sql-seed-file-not)
- [The features were tested before any of them was taken apart](#the-features-were-tested-before-any-of-them-was)
- [The shared function re-checks what the prompts already guarantee](#the-shared-function-re-checks-what-the-prompts-already)
- [Runtime and development dependencies are separate files](#runtime-and-development-dependencies-are-separate-files)
- [Every write was separated from its prompts before a page used it](#every-write-was-separated-from-its-prompts-before-a)
- [Warnings fail the tests](#warnings-fail-the-tests)
- [The sample records are tested like code](#the-sample-records-are-tested-like-code)
- [The sample data is generated, by the application's rules](#the-sample-data-is-generated-by-the-applications-rules)

### The API and the web pages

- [The API is a second way in, not a second implementation](#the-api-is-a-second-way-in-not-a)
- [Recording a sale is one function, and asking the questions is not part of it](#recording-a-sale-is-one-function-and-asking-the)
- [A malformed request and an impossible one get different answers](#a-malformed-request-and-an-impossible-one-get-different)
- [Money crosses the wire as whole cents](#money-crosses-the-wire-as-whole-cents)
- [The API declares its own response shape](#the-api-declares-its-own-response-shape)
- [The endpoints are synchronous on purpose](#the-endpoints-are-synchronous-on-purpose)
- [The data location comes from the code, not from the shell](#the-data-location-comes-from-the-code-not-from)
- [The web pages call the application's functions directly, not the API](#the-web-pages-call-the-applications-functions-directly-not)
- ["Templates never compute" is enforced by reading them](#templates-never-compute-is-enforced-by-reading-them)
- [A save redirects; a refusal shows the form again](#a-save-redirects-a-refusal-shows-the-form-again)
- [On the web edit page, an emptied field means cleared](#on-the-web-edit-page-an-emptied-field-means)
- [A page does not invent a default the business does not have](#a-page-does-not-invent-a-default-the-business)
- [Deleting is further away than every other action](#deleting-is-further-away-than-every-other-action)
- [The API grows no write endpoints until there is authentication](#the-api-grows-no-write-endpoints-until-there-is)
- [Money shown to people groups its thousands; money read back does not](#money-shown-to-people-groups-its-thousands-money-read)
- [The interactive API pages are turned off](#the-interactive-api-pages-are-turned-off)
- [Delete stays on the edit page, from either list](#delete-stays-on-the-edit-page-from-either-list)
- [Every list is one function, served three ways](#every-list-is-one-function-served-three-ways)
- [An empty list says so](#an-empty-list-says-so)
- [Correcting is the same in all three ways in](#correcting-is-the-same-in-all-three-ways-in)

### Security and the login

- [Real data stays out of the repo](#real-data-stays-out-of-the-repo)
- [Commercial terms live outside the repository](#commercial-terms-live-outside-the-repository)
- [Writes from another site are refused by checking where the browser says they came from](#writes-from-another-site-are-refused-by-checking-where)
- [HTTPS on this machine before there is a server](#https-on-this-machine-before-there-is-a-server)
- [The private CA can sign for one name and no address](#the-private-ca-can-sign-for-one-name-and)
- [nginx is the only way in, and the application believes nobody else](#nginx-is-the-only-way-in-and-the-application)
- [One name is answered, and every other refused](#one-name-is-answered-and-every-other-refused)
- [TLS 1.3 only, and HTTPS remembered for a year](#tls-1-3-only-and-https-remembered-for-a)
- [No scripts on any page](#no-scripts-on-any-page)
- [The proxy runs as its own user, from the slim image](#the-proxy-runs-as-its-own-user-from-the)
- [Authentication comes before anything is public](#authentication-comes-before-anything-is-public)
- [One account, logged into with a password](#one-account-logged-into-with-a-password)
- [Passwords are hashed with Argon2id, and only length is required](#passwords-are-hashed-with-argon2id-and-only-length-is)
- [Sessions live in the database, and the database keeps only their hash](#sessions-live-in-the-database-and-the-database-keeps)
- [Every route needs a session, and one check says so](#every-route-needs-a-session-and-one-check-says)
- [The cookie is host-only, HTTPS-only and hidden from scripts](#the-cookie-is-host-only-https-only-and-hidden)
- [A form token alongside the browser-label check, not instead of it](#a-form-token-alongside-the-browser-label-check-not)
- [The API takes the same login as the pages](#the-api-takes-the-same-login-as-the-pages)
- [Guessing is slowed at the proxy, with no lockout](#guessing-is-slowed-at-the-proxy-with-no-lockout)
- [The password is set from inside the stack, never from a page](#the-password-is-set-from-inside-the-stack-never)
- [Passwords are at least fifteen characters, since the login went public](#passwords-are-at-least-fifteen-characters-since-the-login)
- [Every commit is scanned for secrets on every push](#every-commit-is-scanned-for-secrets-on-every-push)

### Containers and the Mac

- [The image holds code and nothing else](#the-image-holds-code-and-nothing-else)
- [Nothing is reachable beyond this machine](#nothing-is-reachable-beyond-this-machine)
- [A backup is a dump that has been restored](#a-backup-is-a-dump-that-has-been-restored)
- [Everything CI runs is pinned to its contents](#everything-ci-runs-is-pinned-to-its-contents)
- [The proxy's configuration and the application ship together](#the-proxys-configuration-and-the-application-ship-together)
- [The stack restarts with Docker, unless stopped on purpose](#the-stack-restarts-with-docker-unless-stopped-on-purpose)
- [A fixed package goes into the image before the base image has it](#a-fixed-package-goes-into-the-image-before-the)
- [An unfixable scan finding gets a dated exception, for the image it is in](#an-unfixable-scan-finding-gets-a-dated-exception-for)
- [On the Mac, a login job starts the stack](#on-the-mac-a-login-job-starts-the-stack)
- [PSells builds its own nginx image](#psells-builds-its-own-nginx-image)
- [Each backup leaves the Mac, encrypted, and is proved](#each-backup-leaves-the-mac-encrypted-and-proved)
- [The Mac says when a job fails](#the-mac-says-when-a-job-fails)
- [A certificate is warned about while it can still be renewed](#a-certificate-is-warned-about-while-it-can-be-renewed)

### AWS and Terraform

- [The cloud phases cost nothing, ever](#the-cloud-phases-cost-nothing-ever)
- [The cloud holds invented records only](#the-cloud-holds-invented-records-only)
- [No long-lived keys, and no SSH](#no-long-lived-keys-and-no-ssh)
- [The person has broad rights; the server has narrow ones](#the-person-has-broad-rights-the-server-has-narrow)
- [Secrets live in Parameter Store and are written out at deploy](#secrets-live-in-parameter-store-and-are-written-out)
- [The server is laid over the Mac's stack, not written again](#the-server-is-laid-over-the-macs-stack-not)
- [certbot runs as nginx's own user](#certbot-runs-as-nginxs-own-user)
- [The deploy builds on the server, by hand, this once](#the-deploy-builds-on-the-server-by-hand-this)
- [Terraform's state is kept in S3, and made by a bootstrap](#terraforms-state-is-kept-in-s3-and-made-by)
- [What existed was adopted, not rebuilt, and then rebuilt on purpose](#what-existed-was-adopted-not-rebuilt-and-then-rebuilt)
- [Terraform does not manage the access it runs with, or any secret](#terraform-does-not-manage-the-access-it-runs-with)
- [A new server sets itself up; a running one is left alone](#a-new-server-sets-itself-up-a-running-one)
- [Bucket names are in the code](#bucket-names-are-in-the-code)
- [Terraform is checked on every push without reaching AWS](#terraform-is-checked-on-every-push-without-reaching-aws)
- [The managed database and the load balancer run on a switch](#the-managed-database-and-the-load-balancer-run-on)
- [While on, the demo really runs on RDS](#while-on-the-demo-really-runs-on-rds)
- [RDS's password never reaches the state](#rdss-password-never-reaches-the-state)
- [The app checks RDS's certificate](#the-app-checks-rdss-certificate)
- [The load balancer reaches nginx, not the app, and has a name of its own](#the-load-balancer-reaches-nginx-not-the-app-and)
- [The demo's database is changed by hand, from a script that proves it ran](#the-demos-database-is-changed-by-hand-from-a)

### CI/CD

- [Pinned versions are checked weekly](#pinned-versions-are-checked-weekly)
- [CI reaches AWS with OpenID Connect, not a stored key](#ci-reaches-aws-with-openid-connect-not-a-stored)
- [The pipeline can deploy and do nothing else on the server](#the-pipeline-can-deploy-and-do-nothing-else-on)
- [What runs is what was scanned](#what-runs-is-what-was-scanned)
- [A deploy waits for every check](#a-deploy-waits-for-every-check)
- [A deploy is checked from outside, and rolled back by hand](#a-deploy-is-checked-from-outside-and-rolled-back)
- [A deploy reloads nginx](#a-deploy-reloads-nginx)

### Monitoring

- [Monitoring runs on Grafana Cloud's free tier, with an agent on the server](#monitoring-runs-on-grafana-clouds-free-tier-with-an)
- [Only the demo is watched](#only-the-demo-is-watched)
- [Two SLIs, one from each side](#two-slis-one-from-each-side)
- [Three check locations every two minutes](#three-check-locations-every-two-minutes)
- [One alert, on the symptom](#one-alert-on-the-symptom)
- [nginx's log carries only what the SLOs need](#nginxs-log-carries-only-what-the-slos-need)
- [The agent reads the journal, never Docker's socket](#the-agent-reads-the-journal-never-dockers-socket)
- [The agent's scan has a dated exception, as nginx's does](#the-agents-scan-has-a-dated-exception-as-nginxs)
- [Grafana is Terraform too](#grafana-is-terraform-too)
- [The failure was planned, real and written up as if it were not](#the-failure-was-planned-real-and-written-up-as)
- [What the failure found was fixed in the phase](#what-the-failure-found-was-fixed-in-the-phase)

### Kubernetes

- [Kubernetes runs on the Mac, with kind, and the sample records only](#kubernetes-runs-on-the-mac-with-kind-and-the)
- [nginx and the app share one pod](#nginx-and-the-app-share-one-pod)
- [The cluster runs CI's published images, by digest](#the-cluster-runs-cis-published-images-by-digest)
- [Plain YAML with kustomize, rendered from the repository's own files](#plain-yaml-with-kustomize-rendered-from-the-repositorys-own)
- [One copy of the database password](#one-copy-of-the-database-password)
- [The cluster's certificate is its own, from the Mac's CA](#the-clusters-certificate-is-its-own-from-the-macs)
- [The app's probes ask uvicorn, not the database](#the-apps-probes-ask-uvicorn-not-the-database)
- [A real cluster in CI, and Deploy waits for it](#a-real-cluster-in-ci-and-deploy-waits-for)

### Analytics

- [Analytics runs on the real records, on the Mac, and publishes nothing real](#analytics-runs-on-the-real-records-on-the-mac)
- [The analytics live in a database of their own](#the-analytics-live-in-a-database-of-their-own)
- [Analytics has its own Compose file](#analytics-has-its-own-compose-file)
- [The ETL reads as a read-only role](#the-etl-reads-as-a-read-only-role)
- [pandas gets an image of its own](#pandas-gets-an-image-of-its-own)
- [The ETL asks psells for every figure](#the-etl-asks-psells-for-every-figure)
- [In the warehouse, a discontinued product has no retail price](#in-the-warehouse-a-discontinued-product-has-no-retail)
- [The analysis is shown on a page in PSells, not in Power BI](#the-analysis-is-shown-on-a-page-in-psells)
- [Each analytics figure is worked out once, in a warehouse view](#each-analytics-figure-is-worked-out-once-in-a)
- [Margin is summed profit over summed revenue; sell-through is units sold over units received](#margin-is-summed-profit-over-summed-revenue-sell-through)
- [No average sale price, for now](#no-average-sale-price-for-now)
- [No inventory aging, for now](#no-inventory-aging-for-now)
- [The analysis is read from the warehouse's views](#the-analysis-is-read-from-the-warehouses-views)
- [The reader's grant is given again with every rebuild](#the-readers-grant-is-given-again-with-every-rebuild)
- [Charts are SVG drawn on the server](#charts-are-svg-drawn-on-the-server)
- [Ratios are shown by one formatter](#ratios-are-shown-by-one-formatter)
- [The style block and its hash are checked where they meet](#the-style-block-and-its-hash-are-checked-where)
- [The analytics rebuild themselves every hour](#the-analytics-rebuild-themselves-every-hour)
- [A stale warehouse is said on the page](#a-stale-warehouse-is-said-on-the-page)
- [The demonstration got its warehouse inside its memory](#the-demonstration-got-its-warehouse-inside-its-memory)
- [The server's analytics settings are a file of their own](#the-servers-analytics-settings-are-a-file-of-their)

### Documents

- [The architecture is drawn from text, and checked against the repository](#the-architecture-is-drawn-from-text-and-checked-against-the)
- [A runbook procedure is tried before it is written down](#a-runbook-procedure-is-tried-before-it-is-written-down)
- [A destructive command is one guarded chain](#a-destructive-command-is-one-guarded-chain)
- [Decisions keep their order, with an index by area](#decisions-keep-their-order-with-an-index-by-area)

## The decisions, in the order they were made

- <a id="json-then-sqlite"></a>**JSON, then SQLite.** Started with JSON storage because it maps directly onto
  Python's lists and dicts, preserves value types, and keeps the early model
  simple while the data structure is being worked out. The move to SQLite
  happened once querying and relationships became the point: items, sales,
  returns and payments needed reliable links, real queries, and a storage layer
  able to refuse bad data rather than one trusting the application to be careful
  every time.
  *Later replaced, in whole or in part: [PostgreSQL only, and the tests run on it](#postgresql-only-and-the-tests-run-on-it).*

- <a id="store-facts-compute-the-rest"></a>**Store facts, compute the rest.** Only raw facts are saved (an item exists, a
  sale happened, a payment was made). The stored data is the source of truth, and
  everything derived (available stock, revenue, profit, partner totals, the
  dashboard) is calculated from it, never stored. Storing derived values just
  lets them drift out of sync with the facts.

- <a id="people-use-names-the-program-uses-ids"></a>**People use names, the program uses IDs.** Each item gets an internal ID it
  never has to show, so existing physical stock needs no relabeling. Sales and
  returns link to items by ID under the hood while the user works by name; if
  multiple items share a name, the app asks the user to choose the correct one.

- <a id="history-stays-fixed"></a>**History stays fixed.** Each sale records its own figures at the moment it
  happens, so later changes to an item never rewrite the numbers on past sales.
  For example, changing an item's price later does not change the price recorded
  on an earlier sale. A record entered wrongly can still be corrected, but
  only as itself and never by a change elsewhere; see "A wrong record is
  corrected, and the correction is kept" below.

- <a id="real-data-stays-out-of-the-repo"></a>**Real data stays out of the repo.** Actual inventory and financials are never
  committed, preventing accidental exposure of business data. Everything under
  the data folder is ignored with no exceptions, so no rule has to be trusted to
  tell real records from fake ones. Invented sample data lives in its own folder
  and is copied into place by anyone who wants to run the app.

- <a id="discontinued-items-are-marked-not-inferred"></a>**Discontinued items are marked, not inferred.** Some stock is no longer sold
  at retail and has no retail price to work from. Rather than letting a zero
  price quietly stand for that, items carry an explicit flag, so the meaning
  lives in the data instead of in the owner's head. A discontinued item takes a
  fixed per-unit partner amount and the application refuses the other modes,
  because a percentage of a price the item no longer has is not a number worth
  computing.

- <a id="commercial-terms-live-outside-the-repository"></a>**Commercial terms live outside the repository.** The default partner
  percentage is a real business term, so it is read from a configuration file
  under the ignored data folder rather than written into the source. The code
  ships with a placeholder sample instead. This keeps the figure private in a
  public repository, and it means renegotiating the rate is a one-line edit in
  one file rather than a code change.

- <a id="the-spreadsheet-was-cleaned-before-it-was-imported"></a>**The spreadsheet was cleaned before it was imported.** The original workbook
  carried the partner's terms in three different places, including free text
  inside a condition column and inside notes. Rather than write parsing logic
  against inconsistent prose, the source was given explicit columns first, so the
  one-time import became a straight mapping with nothing inferred. The importer
  builds every record in memory, validates the whole result, and writes both
  files or neither, because a half-finished import gives no way to tell which
  half is real.

- <a id="the-application-became-importable"></a>**The application became importable.** The menu loop used to run at the top
  level of the file, so merely importing it started the interactive menu. That is
  why the one-time import script could not reuse a single helper and had to
  duplicate its validation instead. The loop now sits behind an entry-point
  guard, so the file can be read as a library or run as a program. The same
  startup path checks the configuration file once and exits with a sentence if it
  is missing or unusable, rather than raising a stack trace later, the first time
  a product happens to be displayed. Failing immediately with an explanation
  beats failing halfway through a task.

- <a id="calculations-were-separated-from-printing"></a>**Calculations were separated from printing.** The dashboard used to read four
  files, work out nine figures, and print them, all in one function, so there was
  no way to check the arithmetic except by reading terminal output. The figures
  now come from a function that takes the four datasets and returns them as a
  set of named values; the dashboard only fetches and displays. This was done to
  make the totals testable, but the same separation is what a future web
  interface needs, since that interface must call the same logic rather than work
  the totals out a second time for itself. The change was confirmed to alter
  nothing by comparing the dashboard output against real data before and after.

- <a id="tests-fake-the-commercial-terms-rather-than-reading-them"></a>**Tests fake the commercial terms rather than reading them.** Because the
  default partner percentage lives in an ignored configuration file, a test that
  exercised the default mode for real would depend on a private figure and would
  fail anywhere that file does not exist, which includes every automated run on a
  build server. Tests replace the function that reads the configuration with one
  returning an invented number. That keeps the real term out of a public
  repository and keeps the tests independent of the machine running them.

- <a id="money-is-stored-as-whole-cents"></a>**Money is stored as whole cents.** Floating-point arithmetic cannot represent
  most decimal fractions exactly, so the same formula returns an exact result for
  one price and a value trailing a string of nines for another, with nothing
  about a case to say in advance which it will be. Real sale records were already
  carrying that damage. SQLite offers no decimal or money type, and its floating
  type reproduces the problem inside the database, so monetary values are stored
  as integers counting cents. They then sum and compare exactly, which is what
  makes a storage migration verifiable as an exact match rather than a match
  within a tolerance. The cost is that cents and dollars look alike in code, so
  the conversion happens in two helpers and nowhere else. Rounding is applied at
  one point only, where a partner cut is computed from a percentage, and it
  rounds to the nearest cent rather than truncating, because truncation loses a
  cent on exactly the values that carry the floating-point damage.

- <a id="money-is-compared-with-a-tolerance-only-where-it"></a>**Money is compared with a tolerance only where it is still a fraction.** Test
  assertions against stored money are exact, because stored money is an integer
  number of cents. The tolerance remains only for a figure computed from a
  percentage before it has been rounded to a cent. Quantities, being whole
  numbers, are compared exactly and always were.

- <a id="tests-and-the-dependency-audit-are-separate-automated-workflows"></a>**Tests and the dependency audit are separate automated workflows.** Run as a
  single unit, a failing test would end the run before the audit executed, so a
  broken test would also hide whether the dependencies were safe. Kept apart,
  each reports its own result. The audit additionally runs on a weekly schedule,
  because vulnerabilities get discovered in dependencies that have not changed,
  and a check that only runs when code is pushed would never find them.

- <a id="the-test-runner-is-pinned-the-security-scanner-is"></a>**The test runner is pinned, the security scanner is not.** Pinning the test
  runner means every run uses the version the tests were written against, so a
  failure is a real failure rather than a change in the tool. The scanner is the
  opposite case: an older version simply knows about fewer vulnerabilities, so it
  is deliberately left to update itself.
  *Later replaced, in whole or in part: [Everything CI runs is pinned to its contents](#everything-ci-runs-is-pinned-to-its-contents).*

- <a id="nothing-derived-is-stored-including-how-many-units-have"></a>**Nothing derived is stored, including how many units have sold.** The rule
  above had one exception: units sold was a stored number that recording a sale
  incremented, and units received was reduced whenever stock went back to the
  partner. Both are now computed from the sales and returns tables, and the
  stored intake figure means what its name says. Recording a sale or a return
  became a single insert with no second value to keep in step, and the original
  intake quantity, which the old behaviour overwrote and lost, is now kept. This
  reverses an earlier decision to document the old meaning of that field rather
  than change it. The reversal was taken because the storage layer was being
  rebuilt anyway and because no return had ever been recorded, so there was
  nothing to reconstruct; the same change made later would mean recovering intake
  figures from partial history.

- <a id="the-retail-discontinued-flag-says-what-it-means"></a>**The retail-discontinued flag says what it means.** The field was renamed to make
  clear that it describes the retail market and not this business. It records
  that a product is no longer sold at major retailers, so no retail price exists
  to take a percentage of. It does not mean the product was dropped here: this is
  a reselling business, and such a product is still held, still listed, still
  sold, and still counted in stock. The old name carried a strong conventional
  meaning that contradicted the actual one, which is a different problem from a
  field whose name is merely imprecise, and a column name is read by every future
  query rather than only by the person who wrote it.

- <a id="the-partner-share-value-became-two-columns"></a>**The partner-share value became two columns.** One column held a percentage
  for one mode and a cash amount for another, with a second column deciding which
  it was. That cannot be range-checked, since a percentage stops at one hundred
  and an amount does not, and once money counts cents the column would hold two
  different units with nothing to tell them apart. Splitting it lets the database
  state the rule directly: each mode allows exactly one shape, and the mode is
  still stored rather than inferred from which column is filled, for the same
  reason the retail flag is explicit.

- <a id="deleting-a-product-with-history-is-refused"></a>**Deleting a product with history is refused.** Deleting a product used to
  leave its sales pointing at nothing. Cascading the delete was rejected because
  it would remove those sales along with the product, silently changing revenue,
  profit and the balance owed to a real person, with no error and no way back
  except a backup; that also contradicts the rule that history stays fixed, which
  is the reason each sale freezes its own figures. Marking products deleted
  rather than removing them was considered and deferred, because hiding a product
  from a list is a different question from what a delete should do to history,
  and it can be added later. Refusing is the option that loses nothing and can
  still be changed; the other two are harder to walk back.

- <a id="the-schema-carries-the-rules-it-can-carry-and"></a>**The schema carries the rules it can carry, and says which it cannot.** A
  declared column type in SQLite is close to advisory, so enforcement lives in
  constraints rather than in the type names: required fields, bounded
  percentages, valid modes, the shape each mode allows, real calendar dates, and
  foreign keys that refuse to create an orphan. Foreign keys are off by default
  in SQLite and are switched on per connection, which means a schema can look
  protected while enforcing nothing. Two rules cannot be expressed this way at
  all, because they span more than one row and constraints may not contain
  subqueries: that available stock never goes negative, and that an intake figure
  is never edited below what has already sold and returned. Those stay in the
  application, and saying so plainly is better than assuming the database is
  covering them.

- <a id="browsing-matches-widely-choosing-a-product-does-not"></a>**Browsing matches widely, choosing a product does not.** Search covers a
  product's name and its category, because forgetting the exact name of one of
  several hundred items is normal while the category is usually easy to
  remember. Selecting a product to sell, edit or delete still matches on the
  name alone. The two look like the same operation and are not: one shows a
  list, the other leads straight into an action on whichever id is typed, and a
  category match there would offer an entire category at once. The asymmetry is
  deliberate and has a test holding it in place, so widening it later has to be
  a decision rather than a slip.

- <a id="the-sample-data-is-a-sql-seed-file-not"></a>**The sample data is a SQL seed file, not JSON.** The invented records used to
  be copied into place as files the application read directly. They are now
  statements applied to a database built from the real schema, so anyone trying
  the project exercises the same constraints the real data does, and a sample
  record that would break a rule cannot be shipped by accident.
  *Later replaced, in whole or in part: [The sample data is generated, by the application's rules](#the-sample-data-is-generated-by-the-applications-rules).*

- <a id="the-features-were-tested-before-any-of-them-was"></a>**The features were tested before any of them was taken apart.** Ten functions
  prompted and printed and none had an automated test, which is why building an
  HTTP layer started with writing those tests rather than with writing an
  endpoint. Input is faked and output captured, so a test drives a menu function
  the way a person does. Written first, they pin what the application already
  does and prove an extraction changed nothing. Written afterwards they would
  only describe code that had already moved, and the one thing worth knowing,
  whether it still behaves the same, would be unknowable.

- <a id="the-api-is-a-second-way-in-not-a"></a>**The API is a second way in, not a second implementation.** Every figure the
  endpoints return comes from the functions the command line already uses:
  stock from the products view, the partner cut from the one function that
  computes it, the dashboard from the one function that totals it. Two copies of
  a business rule do not stay equal, and the failure is silent, because both
  answers look reasonable. Tests assert that the API's figures equal a direct
  call to those same functions, so the rule is checked on every run rather than
  remembered.

- <a id="recording-a-sale-is-one-function-and-asking-the"></a>**Recording a sale is one function, and asking the questions is not part of
  it.** The menu version is a conversation: search, choose, quantity, price,
  date, with context carried between the steps. HTTP has no conversation. A
  request arrives complete and the server remembers nothing, so an endpoint
  cannot drive a function built out of prompts. What both callers share is
  everything that happens once the answers exist, and that is now its own
  function: check the rules, compute the cut, insert one row. The prompts feed
  it and so does a request body.

- <a id="the-shared-function-re-checks-what-the-prompts-already"></a>**The shared function re-checks what the prompts already guarantee.** A
  prompt that refuses a quantity above the stock on hand makes the same check
  further down look redundant. It is not. The prompts are one caller, and the
  other is a request from outside that has guaranteed nothing at all. Several of
  the refusals now tested cannot be produced from the menu, which is exactly why
  they need to exist.

- <a id="a-malformed-request-and-an-impossible-one-get-different"></a>**A malformed request and an impossible one get different answers.** The
  request model refuses a body that is wrong in itself, a missing field or a
  negative price or a date that is not a date, before the endpoint runs, and
  says which field. The shared function refuses a request that is well formed
  and that the stock disagrees with. A missing product answers 404, meaning
  correct the id; a stock conflict answers 409, meaning correct the sale. The
  two are carried by separate exception types rather than by matching on message
  text.

- <a id="money-crosses-the-wire-as-whole-cents"></a>**Money crosses the wire as whole cents.** The same reasoning that put
  integers in the database: exact, no rounding in transit, and no decision about
  presentation made in a layer that has no business making one. Field names say
  so, so a value cannot be mistaken for dollars. Formatting belongs to whatever
  is showing a figure to a person, which is the interface that comes next.

- <a id="the-api-declares-its-own-response-shape"></a>**The API declares its own response shape.** Returning database rows directly
  would have been shorter and would have made the columns of a view into the
  published contract by accident, so renaming one would silently change what
  every caller receives. Declared shapes also document themselves, which is
  where the generated API documentation comes from, and they convert the 0 or 1
  SQLite stores for a flag into a real boolean.

- <a id="the-endpoints-are-synchronous-on-purpose"></a>**The endpoints are synchronous on purpose.** The obvious style for this
  framework is asynchronous, and it would be wrong here. Asynchronous code helps
  only when a function waits on something that can yield while waiting, and the
  database driver in use cannot: it blocks. An asynchronous endpoint calling it
  would hold up every other request on the server. Plain functions are run on a
  thread pool instead, which suits blocking work. The consequence is that one
  request can touch two threads, and the driver refuses a connection used from a
  thread other than the one that opened it, so each request opens its own
  connection and closes it at the end.

- <a id="the-data-location-comes-from-the-code-not-from"></a>**The data location comes from the code, not from the shell.** The database
  and the configuration file used to be found by paths relative to whatever
  directory a process was started in. That produced three separate failures: a
  test suite that passed locally and failed in automation, a server that served
  nothing unless launched from one particular folder, and a sandbox copy that
  worked only as a side effect of changing directory. They now resolve beside
  the source file, with environment variables to override them, so pointing the
  application at a copy is a deliberate act and a deployment can point it at a
  mounted volume.

- <a id="runtime-and-development-dependencies-are-separate-files"></a>**Runtime and development dependencies are separate files.** What the
  application needs in order to run is now listed apart from what is needed to
  work on it, so a deployment installs neither a test runner nor a spreadsheet
  library. The automated checks install both, and the vulnerability audit reads
  both files.

- <a id="the-web-pages-call-the-applications-functions-directly-not"></a>**The web pages call the application's functions directly, not the API.** The
  pages and the API run in one process, and a page could have fetched its data
  from the API over the network instead. That would have doubled the work for
  every page, needed an HTTP client and a configured address, risked one request
  waiting on another inside the same small pool of threads, and made every page
  test depend on a running server. Calling the same functions the command line
  calls satisfies the rule that matters, one implementation of every business
  rule, and three narrower rules keep it honest: a page route does no arithmetic
  on money, stock or partner share; wherever a page shows a figure the API also
  serves, a test asserts the two agree; and templates format and never compute.

- <a id="templates-never-compute-is-enforced-by-reading-them"></a>**"Templates never compute" is enforced by reading them.** A test comparing
  page and API only catches a figure that disagrees, and a template recomputing
  profit correctly would pass it. So the tests parse every template the way the
  template engine does and fail on any arithmetic, and on any formatting filter
  other than the one that renders money. Adding a filter is therefore a decision,
  and the question to ask is whether it formats or computes.

- <a id="every-write-was-separated-from-its-prompts-before-a"></a>**Every write was separated from its prompts before a page used it.** Adding,
  editing, selling, returning, paying and deleting were each conversations the
  terminal holds with a person, which a web request cannot. Each was split into
  the prompting and a function that does the work and checks every rule again,
  because a caller that is not a prompt has guaranteed nothing. Each split was
  made against the existing tests of the terminal behaviour and changed none of
  them, and bugs found while moving code were fixed in commits of their own.

- <a id="a-save-redirects-a-refusal-shows-the-form-again"></a>**A save redirects; a refusal shows the form again.** Every form answers a
  successful save by sending the browser to another page to load, so refreshing
  cannot repeat it, which matters most for a sale: a repeated sale is a second
  sale with a second partner cut. A refusal writes nothing and shows the same
  form with a sentence beside each field that is wrong and everything already
  typed kept. Input that is wrong in itself and input the stock disagrees with
  are answered differently, the same distinction the API makes.

- <a id="writes-from-another-site-are-refused-by-checking-where"></a>**Writes from another site are refused by checking where the browser says
  they came from.** Any page open in the same browser could otherwise submit a
  form to the running server, and binding it to this machine does not stop that.
  Every current browser labels each request with its origin in a way a page
  cannot change, and writes labelled as coming from anywhere else are refused
  before anything runs, including from another server on the same machine. The
  alternative, a secret token in every form, needs a secret stored somewhere and
  belongs with logins and sessions; it is the thing to add when authentication is
  decided. Authentication added it, and this check stays beside it (below).

- <a id="on-the-web-edit-page-an-emptied-field-means"></a>**On the web edit page, an emptied field means cleared.** The terminal treats
  a blank answer as "keep the current value". A web form opens already filled
  in, so a field that arrives empty was emptied on purpose, and treating it as
  "keep" would make it impossible to clear anything from a browser. The rule
  underneath is the same, notes may be empty; the two interfaces express it
  differently, and the terminal still cannot clear a note.

- <a id="a-page-does-not-invent-a-default-the-business"></a>**A page does not invent a default the business does not have.** A sale form
  starts at one unit and today's date, but with the price left blank, because
  the terminal has never assumed a price either. The listed price is shown
  beside the field instead.

- <a id="deleting-is-further-away-than-every-other-action"></a>**Deleting is further away than every other action.** It is offered from a
  product's edit page rather than from each row, the page that offers it is the
  confirmation, and only its button deletes: a link alone never does, so no
  browser prefetch or link preview can. A product with sales or returns is told
  why it cannot be deleted instead of being offered a button that would then be
  refused.

- <a id="ids-may-be-reused-until-postgresql"></a>**Ids may be reused, until PostgreSQL.** Deleting the newest product frees its
  id for the next one. The original reasoning for allowing that, that products
  with history can never be deleted, still holds for the records. The web pages
  add one case it did not cover: a browser tab left open on a deleted product's
  form would post to the new product that inherited its id. Rebuilding the table
  to prevent reuse was judged not worth doing on live data at the end of a phase,
  because the planned move to PostgreSQL removes the case entirely. It did: ids
  now come from sequences, which never reuse a value.
  *Later replaced, in whole or in part: [PostgreSQL only, and the tests run on it](#postgresql-only-and-the-tests-run-on-it).*

- <a id="the-api-grows-no-write-endpoints-until-there-is"></a>**The API grows no write endpoints until there is authentication.** The pages
  need the work separated from the prompts, and it has been. Putting HTTP
  endpoints on top of it now would add unauthenticated ways to change the
  records that nothing yet calls. Authentication now exists; more write
  endpoints still wait, now for a program that needs them. Correcting a sale,
  return or payment was the exception, chosen so the three ways in stay equal
  for it; see below.
  *Later replaced, in whole or in part: [Authentication comes before anything is public](#authentication-comes-before-anything-is-public), [Correcting is the same in all three ways in](#correcting-is-the-same-in-all-three-ways-in).*

- <a id="pinned-versions-are-checked-weekly"></a>**Pinned versions are checked weekly.** Pinning makes a build repeatable and
  then goes quiet forever. The vulnerability audit answers whether a pinned
  version is known to be unsafe; a weekly automated check answers whether it has
  aged, and opens a pull request that the same checks then test. Its pull
  requests appear on the repository under a bot's name, which was accepted
  knowingly before it was set up.

- <a id="money-shown-to-people-groups-its-thousands-money-read"></a>**Money shown to people groups its thousands; money read back does not.** A
  figure is easier to read as 12,345.67 than as 12345.67, so everything displayed
  is grouped. The text an edit form holds for typing over is not, because it has
  to read back as exactly the amount that is stored.

- <a id="postgresql-only-and-the-tests-run-on-it"></a>**PostgreSQL only, and the tests run on it.** The move off SQLite could have
  kept SQLite for the tests, in memory and with nothing to start, while
  production ran PostgreSQL. That would mean two schemas and two dialects, and
  every test passing against an engine that never runs the business. So SQLite
  was retired after the one-time move, and the suite runs against a real
  PostgreSQL: a throwaway one of its own, never the real one, each test inside a
  transaction that is rolled back. The price is that running the tests needs
  Docker.

- <a id="the-applications-connection-commits-every-write"></a>**The application's connection commits every write.** With PostgreSQL's
  driver a transaction opens at the first statement of any kind, and a write
  block inside an open transaction is only a savepoint: the write looks done and
  is lost when the connection closes. The application's connections run in
  autocommit, so each write block is a real transaction, and a test checks from
  a second connection that a write has landed, because nothing else in the suite
  can see the difference.

- <a id="the-types-were-chosen-to-change-nothing"></a>**The types were chosen to change nothing.** Money stays whole cents in
  integer columns, not `numeric` and not `bigint`, because both would come back
  into Python as `Decimal`. The partner percentage is the same eight-byte float
  SQLite used; PostgreSQL's smaller one would lose digits. Dates became real
  dates, which the type itself checks. The retail flag stays 0 or 1. Categories
  sort by character code, as they did, rather than by the server's language,
  which can differ from one machine to the next.

- <a id="the-move-from-sqlite-was-one-transaction-checked-before"></a>**The move from SQLite was one transaction, checked before it committed.**
  Every row was copied with its id, and nothing was kept until the result
  matched the source in every row and column, every product's stock and partner
  cut, and every dashboard figure, each worked out by the same functions on both
  sides. Money being whole cents made that an exact comparison rather than one
  within a tolerance. A verified copy of the SQLite database was archived first,
  and the first PostgreSQL backup was restored before it was trusted.

- <a id="the-image-holds-code-and-nothing-else"></a>**The image holds code and nothing else.** The records live in the database
  container and the configuration file is mounted read-only when the
  application starts, so an image can be shared without carrying a record. The
  Dockerfile names every file it copies rather than copying the folder, which
  holds the real data, and the build context leaves that data out as well.
  Every file is made readable before the server's own unprivileged user takes
  over, so the image does not depend on how the files happened to be saved on
  the machine that built it.

- <a id="nothing-is-reachable-beyond-this-machine"></a>**Nothing is reachable beyond this machine.** Inside a container the server
  must listen on every interface, so the protection moved to how the port is
  published, which is to this machine only. The database publishes no port at
  all; only the application reaches it, and the terminal application runs inside
  the application's container rather than on the host. Its password lives in a
  file kept out of the repository and out of every image, and every setting is
  required, so a missing one stops the stack with a sentence instead of starting
  a database with no password.

- <a id="a-backup-is-a-dump-that-has-been-restored"></a>**A backup is a dump that has been restored.** Each daily dump is restored
  into a throwaway database and its products counted against the live database
  before any older copy is deleted. The schedule moved from cron to macOS's own
  scheduler, which runs a missed job when the machine wakes; cron skipped every
  morning the laptop slept through. Every copy of the real database is still on
  the same disk as the database, which is the largest risk left. The cloud
  phases did not solve it, because the real records do not go to the cloud;
  the copy off the machine needs a free home that outlasts them.
  *Later replaced, in whole or in part: [Each backup leaves the Mac, encrypted, and is proved](#each-backup-leaves-the-mac-encrypted-and-proved).*

- <a id="warnings-fail-the-tests"></a>**Warnings fail the tests.** A deprecation printed in a summary is read once
  and then ignored until the thing it warns about is removed. As an error it
  fails the day it appears. One known warning is allowed, matched on its exact
  text. On its first run the setting found a real leak: test connections that
  were never closed.

- <a id="everything-ci-runs-is-pinned-to-its-contents"></a>**Everything CI runs is pinned to its contents.** A tag names a version and
  can be moved to different code after it is published, which is how a widely
  used scanning action was turned against its users in March 2026. Every action
  is pinned to a commit and every image to a digest, every workflow can only
  read the repository, and the built image is scanned for known
  vulnerabilities, failing on a serious one that has a fix and listing the rest.
  Pins age, so Dependabot proposes each update and the same checks judge it.

- <a id="https-on-this-machine-before-there-is-a-server"></a>**HTTPS on this machine before there is a server.** A certificate every
  browser trusts has to name a public address its issuer can check, and there
  is no server or domain yet. Holding HTTPS back until there is one would have
  put two new layers, a server and TLS, into one step, so that a failure had
  two possible causes. PSells is served over HTTPS on this machine now, with a
  certificate from a certificate authority of its own that this machine
  trusts, and a publicly trusted certificate arrives with the server. Everything
  else about serving it, the proxy, the redirect, the headers and which names
  are answered, carries over unchanged.

- <a id="the-private-ca-can-sign-for-one-name-and"></a>**The private CA can sign for one name and no address.** Trusting a CA of
  one's own normally means trusting it for every site, so its key would be as
  valuable as any file on the machine. Its certificate carries a name
  constraint that permits only the one name PSells is served on and excludes
  every IP address, marked critical so that software unable to enforce it must
  refuse the certificate. A constraint limits only the kinds of name it lists,
  which is why the addresses are excluded explicitly. The tests prove the limit
  the only convincing way: they have the CA sign certificates for other names
  and for addresses and check each is refused, beside one for the permitted
  name that is accepted. The CA's key lives outside the project; the server's
  key lives under the ignored data folder, and neither reaches the repository
  or an image. Server certificates last just under the limit browsers apply to
  public ones, so renewing is routine, and the script refuses to sign one that
  would outlive its CA, judged by the sentence openssl prints rather than its
  exit status, which one version gets wrong.

- <a id="nginx-is-the-only-way-in-and-the-application"></a>**nginx is the only way in, and the application believes nobody else.** The
  application publishes no port, so every request passes through the proxy's
  configuration. The application takes the scheme and client address from
  forwarded headers only when the connection comes from the proxy's one fixed
  address, which needed a fixed address range for the stack's network. The
  proxy sets those headers from what it saw rather than adding to what the
  client sent, and passes the browser's host unchanged, because the server
  reads the host from that header and the cross-site check compares it with
  the page's origin. A wider trust, the whole network or everyone, was
  considered and refused: whoever is trusted can claim a request arrived over
  HTTPS.

- <a id="one-name-is-answered-and-every-other-refused"></a>**One name is answered, and every other refused.** A request for any other
  name is refused in the handshake, answered 421 if it names another host only
  inside the request, or redirected to the one name if it arrives over plain
  HTTP. The cross-site check only ever guarded writes; answering any name left
  pages readable by a hostile site that points its own name at this machine,
  which is called DNS rebinding. The redirect names its target in full rather
  than echoing the host it was sent, so it can only ever lead to PSells. Each
  place PSells runs answers its own one name: the name, its certificate and
  the redirect live in a small folder per place, and the proxy's configuration
  includes whichever is mounted, so every other rule is written once for all.

- <a id="tls-1-3-only-and-https-remembered-for-a"></a>**TLS 1.3 only, and HTTPS remembered for a year.** Every client is a current
  browser or command-line tool on this machine, so older protocol versions
  would only add handshakes nothing uses. Browsers are told to use nothing but
  HTTPS for this name for a year after one visit, for this name alone and on no
  preload list, which is undone by sending a zero lifetime over HTTPS.

- <a id="no-scripts-on-any-page"></a>**No scripts on any page.** The pages use none, so the
  Content-Security-Policy allows none, and allows the one style block by the
  hash of its exact text rather than allowing inline styles in general. Forms may post only to
  PSells, and no other site may frame it. A hash covers exact bytes, so a test
  renders a page, hashes its style block and fails, naming the new hash, if the
  template and the policy drift apart. Headers are added on error responses too,
  and all in one place, because the proxy silently drops a server's headers
  from any location that adds one of its own.

- <a id="the-interactive-api-pages-are-turned-off"></a>**The interactive API pages are turned off.** FastAPI builds them from
  JavaScript fetched from a CDN and pinned only to a major version, the same
  kind of floating reference that had been hijacked in the scanning action,
  and they would run it on the same origin as the forms, which the cross-site
  check trusts. The strict policy would refuse that code anyway. The same
  description of the API is still served as plain JSON.

- <a id="the-proxy-runs-as-its-own-user-from-the"></a>**The proxy runs as its own user, from the slim image.** Nothing in the
  stack runs as root, so the proxy listens above port 1024 inside its container
  and keeps its working files where its own user can write. The first scan of
  the full image failed on a library that only its optional add-on modules
  need, and PSells loads none of them; the slim variant is the same server
  without them. A test fails if the configuration ever asks for a module.
  *Later replaced, in whole or in part: [PSells builds its own nginx image](#psells-builds-its-own-nginx-image).*

- <a id="authentication-comes-before-anything-is-public"></a>**Authentication comes before anything is public.** Logins, sessions and a
  token in every form were left for this phase and are their own phase
  instead, built on this machine before a server puts PSells on a public
  address. Sessions need the HTTPS now in place. Built next, as below.

- <a id="one-account-logged-into-with-a-password"></a>**One account, logged into with a password.** PSells has one user. The
  account lives in a table rather than a setting, so a second person later is a
  row rather than a redesign, but there are no roles and no second account
  until that is decided; the command that sets the password refuses to create
  one under another name, so a typing mistake cannot. A form and a session
  cookie were chosen over the browser's own password dialog, which has no
  logout and resends the password with every request. Passkeys were deferred:
  they need JavaScript in the page, which the no-scripts policy forbids.

- <a id="passwords-are-hashed-with-argon2id-and-only-length-is"></a>**Passwords are hashed with Argon2id, and only length is required.** Argon2id
  is the current first choice for password storage, deliberately slow and
  memory hungry so a copied table is expensive to guess against. A maintained
  library does it, rather than a hand-written format around the standard
  library's scrypt, because the salt, the stored parameters, the constant-time
  comparison and the upgrade path are all easy to get subtly wrong. Its
  parameters travel inside each hash, so a hash made with weaker ones is
  replaced at the next login. A password must be at least fifteen characters
  and nothing else: rules demanding digits or symbols push people towards
  predictable patterns. Fifteen is what NIST SP 800-63B asks of a password
  that is the only factor; the first version allowed ten, raised when Phase 06
  put the login on a public address. A shorter password set before then still
  logs in; the rule applies when a password is set. An unknown username still costs one full check, so a
  refusal takes as long whether or not the name exists.

- <a id="sessions-live-in-the-database-and-the-database-keeps"></a>**Sessions live in the database, and the database keeps only their hash.**
  The cookie carries a long random value; the table keeps its SHA-256 digest,
  so neither the database nor a backup holds anything a browser could present.
  A plain hash suffices because the value is random, with nothing to guess.
  Logging out deletes the row, so a copied cookie stops working at once, which
  a signed cookie holding the session itself could not do before it expired,
  and a table needs no signing secret. A session ends two hours after it was
  last used or twelve after it began; that is worked out from the two times
  rather than stored, like every other derived figure, in the same statement
  that marks the session used, so two requests at once cannot disagree.
  Changing the password ends every session.

- <a id="every-route-needs-a-session-and-one-check-says"></a>**Every route needs a session, and one check says so.** The check is a
  dependency set on the router, not on each route, so a route added later
  cannot be added without it; the login page is alone on a router without one.
  A test does not list the protected routes: it asks the application for every
  route it has, calls each without a session, and fails if any route sits
  outside the checked routers. Pages without a session are sent to the login
  page; the API answers 401. The machine-readable description of the API is
  behind the login too. The check reads the database, so it is a plain function
  rather than middleware, which would have to be asynchronous.

- <a id="the-cookie-is-host-only-https-only-and-hidden"></a>**The cookie is host-only, HTTPS-only and hidden from scripts.** Its name
  carries the `__Host-` prefix, which makes the browser refuse it unless it is
  Secure, set by this host with no domain, and for the whole site, so no other
  name can set or overwrite it. `SameSite=Lax` keeps it off other sites' form
  posts while still sending it when a link to PSells is followed; `Strict`
  would show the login page to anyone following a link while logged in. A login
  ends whatever session the browser already had, so a value planted beforehand
  is worthless after it.

- <a id="a-form-token-alongside-the-browser-label-check-not"></a>**A form token alongside the browser-label check, not instead of it.** Each
  session has its own token, which every form carries in a hidden field and
  every write must send back; a program sends it in a header, and learns it
  from an endpoint whose answer another site cannot read. The label check stays
  in front: either stops a forged write alone, the token does not depend on the
  browser's labels, and the labels are what cover the login form, which has no
  session and so no token. The token is compared in constant time.

- <a id="the-api-takes-the-same-login-as-the-pages"></a>**The API takes the same login as the pages.** One credential, one way to
  revoke it. API keys for programs were considered and wait until a program
  needs one, rather than adding a second kind of secret to issue, store and
  rotate with nothing using it.

- <a id="guessing-is-slowed-at-the-proxy-with-no-lockout"></a>**Guessing is slowed at the proxy, with no lockout.** nginx allows each
  address five login attempts a minute, with a burst of five, and answers 429
  past that, before a guess reaches the application. Only posts to the login
  are counted, so no page is ever slowed. Locking the account after a number
  of failures was rejected, because anyone could then lock the one account
  out on purpose; many addresses guessing at once are left to the password's
  length and Argon2id's cost.

- <a id="the-password-is-set-from-inside-the-stack-never"></a>**The password is set from inside the stack, never from a page.** A script
  run in the application's container creates the account or changes its
  password. Whoever can reach the containers already has the database, so
  nothing new is exposed, and no web page can change the password, so a stolen
  session cannot lock its owner out.

- <a id="schema-changes-to-an-existing-database-are-migration-files"></a>**Schema changes to an existing database are migration files, applied by
  hand.** The schema file builds tables only when a database is first created.
  A change is also written as a file that only adds, applied once after a
  backup, in a single transaction that stops at the first error. The same
  statements then live in two places, so a test builds a database both ways and
  compares every column, constraint, index and view. A migration tool that
  records which files have run was considered and waits for the managed
  database later on, when there will be more than one change to track.

- <a id="the-proxys-configuration-and-the-application-ship-together"></a>**The proxy's configuration and the application ship together.** nginx
  reads its configuration from the project folder, while the application runs
  from an image, so restarting only nginx can pair a new policy with an old
  page. That happened once in this phase: a new style hash met the old style
  block and every page lost its styling. A change that touches the style block
  is released by rebuilding the application with it; a change to the proxy
  alone is applied with a reload.

- <a id="the-cloud-phases-cost-nothing-ever"></a>**The cloud phases cost nothing, ever.** PSells is for learning and for job
  applications; the cloud does not help run the business. AWS no longer gives
  new accounts a year of free use but a free plan that cannot be charged and
  closes after six months, or when its credits run out. The account stays on
  that plan and is never upgraded, so no bill is possible, and the cloud
  phases are done inside those six months. What lasts is the repository and
  the code that rebuilds the server, not a permanent public address.

- <a id="the-cloud-holds-invented-records-only"></a>**The cloud holds invented records only.** The server runs the sample data
  and the placeholder partner percentage. The real records stay on the Mac,
  where the business is run, and a script that finds the real configuration
  refuses to deploy or back up. Putting the real business on a public server
  would have meant real figures behind a password-only login on the internet,
  for no benefit to the business.

- <a id="no-long-lived-keys-and-no-ssh"></a>**No long-lived keys, and no SSH.** The daily AWS login is a user with its
  own passkey, and the command line signs in through the browser for hours at
  most, rather than holding an access key that works until someone deletes it.
  AWS's usual answer for people, Identity Center, needs an organisation, and
  joining one upgrades the account to paid. The server has no SSH port and no
  key pair: a shell on it comes through AWS's Session Manager, over the same
  short-lived login, and the firewall admits 80 and 443 only.

- <a id="the-person-has-broad-rights-the-server-has-narrow"></a>**The person has broad rights; the server has narrow ones.** The one person
  using the account is an administrator, protected by a passkey and short
  sessions, because limits there would mostly slow the learning. Least
  privilege goes where a program acts alone: the server's role may read the
  database's parameters and the backup bucket's name, add backups, and nothing
  else. It cannot read, list or delete a backup, so a compromised server can
  neither read old copies nor erase them. Each permission was checked by
  asking for something just outside it and being refused.

- <a id="secrets-live-in-parameter-store-and-are-written-out"></a>**Secrets live in Parameter Store and are written out at deploy.** The
  database password is generated inside AWS as an encrypted parameter, free on
  the standard tier, and the deploy script writes it into a root-only settings
  file. Secrets Manager's rotation was more than a demonstration database
  needs.

- <a id="the-server-is-laid-over-the-macs-stack-not"></a>**The server is laid over the Mac's stack, not written again.** One extra
  Compose file names only what differs on the server: the ports on every
  address, the server's name and certificate, and certbot. Everything else,
  every header, limit and rule, is the same file the Mac runs. A second full
  configuration would have let the two drift, one security header at a time.

- <a id="certbot-runs-as-nginxs-own-user"></a>**certbot runs as nginx's own user.** A certificate's private key has to be
  readable by nginx, which is not root. certbot usually runs as root and
  writes a key only root can read; running it as nginx's user instead leaves a
  key readable by its owner only, and its owner is the one process that reads
  it, with no permissions to widen after each renewal. nginx's module that
  fetches certificates itself was not used, because it is in the full image,
  whose extra libraries failed a scan in Phase 05.

- <a id="the-deploy-builds-on-the-server-by-hand-this"></a>**The deploy builds on the server, by hand, this once.** The server checks
  out a commit and builds it there, as the Mac does. A registry and deploys
  that happen on every push are the next phase but one, and doing them now
  would have taken that phase's lesson.
  *Later replaced, in whole or in part: [CI reaches AWS with OpenID Connect, not a stored key](#ci-reaches-aws-with-openid-connect-not-a-stored), [The pipeline can deploy and do nothing else on the server](#the-pipeline-can-deploy-and-do-nothing-else-on), [What runs is what was scanned](#what-runs-is-what-was-scanned).*

- <a id="passwords-are-at-least-fifteen-characters-since-the-login"></a>**Passwords are at least fifteen characters, since the login went public.**
  Fifteen is what NIST asks of a password that is the only factor. The first
  version allowed ten while the login was reachable from one machine only.

- <a id="every-commit-is-scanned-for-secrets-on-every-push"></a>**Every commit is scanned for secrets on every push.** The history was
  scanned once before the phase ended, and the same scanner now runs in CI
  over every commit on every branch, because a secret removed in a later
  commit is still in the history anyone can clone.

- <a id="terraforms-state-is-kept-in-s3-and-made-by"></a>**Terraform's state is kept in S3, and made by a bootstrap.** State records
  every value of everything Terraform manages, so it lives in a bucket that is
  private, encrypted, versioned and locked while a plan runs, not in the
  repository and not on one laptop. That bucket cannot hold the state that
  creates it, so a small configuration of its own makes it once and keeps its
  own state locally; it can be rebuilt from the bucket's name. A hosted
  service was free too, but it would have been another account holding
  credentials to this one.

- <a id="what-existed-was-adopted-not-rebuilt-and-then-rebuilt"></a>**What existed was adopted, not rebuilt, and then rebuilt on purpose.**
  Everything made by hand in the previous phase was imported, and the first
  plan changed nothing but four missing tags. A plan with no changes is the
  proof that the code describes what runs. Then the server alone was
  destroyed and rebuilt from code twice, first with test certificates, keeping
  its address so the name and the certificate's name survived. Tearing
  everything down would have proved slightly more and cost the backups.

- <a id="terraform-does-not-manage-the-access-it-runs-with"></a>**Terraform does not manage the access it runs with, or any secret.** The
  IAM user it runs as, its group and the root user are left out, so no plan
  can remove the way back in. The database password stays a parameter made by
  hand, because a managed value is copied into the state in plain text; only
  its path is written in the code. The address the budget's alerts go to is
  read from a file git ignores.

- <a id="a-new-server-sets-itself-up-a-running-one"></a>**A new server sets itself up; a running one is left alone.** The host
  setup, the clone and the deploy run from the server's first-boot script, and
  the deploy fetches a certificate when there is none. A newer image or an
  edited script does not replace a running server; both are used when it is
  rebuilt. A rebuilt server starts from the sample records, which cost nothing
  to reload, rather than from a disk kept aside or a backup it would need
  permission to read.

- <a id="bucket-names-are-in-the-code"></a>**Bucket names are in the code.** They are not secrets: both buckets are
  private, refuse plain HTTP and hold no account number. Hiding them would have
  made the code unreadable without a local file.

- <a id="terraform-is-checked-on-every-push-without-reaching-aws"></a>**Terraform is checked on every push without reaching AWS.** Formatting and
  validation run against the provider the lock file pins, from a pinned image,
  on a copy of the whole repository, since the server's user data is read from
  outside the Terraform folder.

- <a id="the-stack-restarts-with-docker-unless-stopped-on-purpose"></a>**The stack restarts with Docker, unless stopped on purpose.** The
  containers had no restart policy, and when Docker Desktop restarted one
  morning PSells stayed down until someone noticed; a reboot of the AWS server
  would have done the same to the demonstration. The proxy, the application and
  the database now restart whenever Docker starts. "unless-stopped" rather than
  "always", so a container stopped deliberately is not brought back behind
  its owner's back. The test database has none: it is a throwaway.
  *Later replaced, in whole or in part: [On the Mac, a login job starts the stack](#on-the-mac-a-login-job-starts-the-stack).*

- <a id="ci-reaches-aws-with-openid-connect-not-a-stored"></a>**CI reaches AWS with OpenID Connect, not a stored key.** A workflow run
  presents a token GitHub signs, naming the repository and branch; AWS trades
  it for a role for fifteen minutes. The role trusts one exact subject: main of
  this repository, by name and by the numeric IDs GitHub now includes, so a
  recycled name cannot match. A key stored as a secret would have worked until
  someone deleted it, from any branch that could read it.

- <a id="the-pipeline-can-deploy-and-do-nothing-else-on"></a>**The pipeline can deploy and do nothing else on the server.** The role may
  send one SSM document, which takes a commit hash and an image digest checked
  against patterns before anything runs, to the server tagged psells. AWS's
  generic shell document would have been simpler and would have let anyone who
  could change a workflow run anything as root.

- <a id="what-runs-is-what-was-scanned"></a>**What runs is what was scanned.** The image is built for amd64 and arm64 on
  native runners, scanned, and published to GHCR, free for a public image; the
  server pulls it by digest and stops building. The scanner runs where nothing
  can be published, and the job that publishes runs no third-party code and
  refuses an image whose ID differs from the scanned one. A deploy takes
  seconds instead of ten minutes.

- <a id="a-deploy-waits-for-every-check"></a>**A deploy waits for every check.** It runs only when Tests, Lint, Security,
  Image and Kubernetes have all passed for that exact commit on main. Keeping
  the five workflows separate, each with its badge, meant a gate that asks
  GitHub for their results rather than one workflow that does everything.

- <a id="a-deploy-is-checked-from-outside-and-rolled-back"></a>**A deploy is checked from outside, and rolled back by hand.** It fails
  unless the server reports the digest it was sent and the site answers over
  trusted HTTPS. Rolling back is the same workflow with an earlier commit,
  which reuses that commit's scanned image. An automatic rollback was more
  logic to test, and could not undo a change to the database anyway.

- <a id="the-managed-database-and-the-load-balancer-run-on"></a>**The managed database and the load balancer run on a switch.** Priced
  before anything was built, RDS and an Application Load Balancer come to
  about USD 50 a month together, against credits that had to last six months
  for everything else. Running them all the time would have closed the free
  account early. So both are described in Terraform behind one variable,
  switched on while they were built and proved, and switched off again; the
  code is the evidence, and the switch shows them again when needed. RDS on
  its own all the time, or skipping the phase, were the alternatives.

- <a id="while-on-the-demo-really-runs-on-rds"></a>**While on, the demo really runs on RDS.** A copy that only held a restored
  backup would not have proved the application on a managed database. The
  deploy finds RDS's address in Parameter Store, builds the tables from the
  schema on an empty database and loads the sample records; without the
  address it uses the database container, as before, so switching off needs
  nothing but a deploy after the address is removed.

- <a id="rdss-password-never-reaches-the-state"></a>**RDS's password never reaches the state.** Terraform reads the existing
  Parameter Store secret ephemerally and passes it write-only, so the state,
  which keeps every other value in plain text, never holds it. Letting RDS
  generate and rotate its own password in Secrets Manager was rejected: it
  costs, and a rotation mid-run would have cut the demo's connection.

- <a id="the-app-checks-rdss-certificate"></a>**The app checks RDS's certificate.** The connection uses verify-full
  against AWS's authorities for the region, fetched on every deploy, so the app
  cannot be talking to anything but RDS; encrypted without checking would have
  been easier and would not have known.

- <a id="the-load-balancer-reaches-nginx-not-the-app-and"></a>**The load balancer reaches nginx, not the app, and has a name of its own.**
  TLS ends at the load balancer with AWS's free certificate, and it forwards to
  a listener of nginx's own, open to the load balancer alone, so every header,
  limit and rule still applies. That listener believes the visitor's address
  only from the VPC's range and only the last one given, so the login limit
  counts visitors; the application still believes nginx alone. The load
  balancer answers its own name, set by hand when it is switched on, so the
  main demo address never moves. nginx's shared rules moved into snippets first,
  so the two servers use one copy.


- <a id="in-stock-and-out-of-stock-are-two-lists"></a>**In stock and out of stock are two lists of one set of products.** The
  inventory page, View Inventory and Search show the products with at least one
  unit available, and the out-of-stock page and View Out of Stock show the
  rest. One condition decides, in psells, and the second list is its negation,
  so no product can fall between them or appear in both; a test checks every
  product is in exactly one. The dashboard still covers every product, because
  it describes the business, not one list.

- <a id="why-a-product-ran-out-is-worked-out-not"></a>**Why a product ran out is worked out, not recorded.** "Sold out",
  "Returned", or a mix such as "2 sold, 1 returned of 3" follows from the
  quantities products_view already derives, so nothing new is stored and the
  reason cannot disagree with the stock. It is one psells function, which the
  page, the API and the terminal all call.

- <a id="a-confirmation-finds-its-product-wherever-it-now-is"></a>**A confirmation finds its product wherever it now is.** The notice after a
  form looks the product up among every product, not only those in stock, so
  selling the last unit is still confirmed; the inventory then says the
  product has none left and links to the out-of-stock page. Without that, the
  sale that empties a product would be the one sale with no confirmation.

- <a id="delete-stays-on-the-edit-page-from-either-list"></a>**Delete stays on the edit page, from either list.** Out-of-stock rows offer
  Edit only, as in-stock rows do, so deleting is still one step further away
  than everything else. Most out-of-stock products have sales or returns and
  would be refused anyway.

- <a id="the-history-shows-each-sale-as-it-was-recorded"></a>**The history shows each sale as it was recorded.** A sale's total, partner
  cut and profit are worked out from its own frozen quantity, price and
  per-unit cut, never from its product as it is now, so editing a product
  never changes a past sale; tests edit a product and compare. Summed, the
  history equals the dashboard's revenue, partner share, profit and units
  sold, and the payments equal total paid; tests check both.

- <a id="every-list-is-one-function-served-three-ways"></a>**Every list is one function, served three ways.** Each list is a psells
  function. The page, the API route and the menu option each call it and only
  format the answer, and tests compare the page with the API and the terminal
  with the API, row by row. The API's existing routes are unchanged; the lists
  are new routes with response models of their own. The pages are at
  /out-of-stock, /sales-history, /returns-history and /payments-history,
  because /sales and /payments already belonged to the API and a form.

- <a id="an-empty-list-says-so"></a>**An empty list says so.** Each new page shows a sentence, such as "No
  returns recorded yet.", instead of a table with no rows, and the terminal
  prints the same sentence.

- <a id="a-fixed-package-goes-into-the-image-before-the"></a>**A fixed package goes into the image before the base image has it.** In
  October 2026 the pinned Python image still carried a libpcre2 with a
  high-severity flaw that Debian had already fixed, and the newest digest of
  that image carried it too. The Dockerfile upgrades those packages, and only
  those, from Debian's security updates. Waiting would have blocked every
  deploy for as long as the image took to be rebuilt.

- <a id="an-unfixable-scan-finding-gets-a-dated-exception-for"></a>**An unfixable scan finding gets a dated exception, for the image it is in.**
  The nginx image's pcre2 had a high-severity flaw for which no nginx image
  had a fix. nginx uses pcre2 only to evaluate the regular expressions in its
  configuration, and PSells' has none. So nginx's failing scan skips that one
  flaw, in that one version, with the reason written beside it, until a date;
  from that date the job fails until someone looks again. A test fails if a
  regular expression is ever added, if the exception reaches the app's scan,
  or if it outlives its date. Turning the scan off for nginx, or moving to an
  older nginx that Dependabot proposed, were the alternatives, and both were
  worse.
  *Later replaced, in whole or in part: [PSells builds its own nginx image](#psells-builds-its-own-nginx-image).*

- <a id="the-sample-records-are-tested-like-code"></a>**The sample records are tested like code.** They are what the demo shows
  and what every screenshot is taken from, so a test loads them and fails if
  any list is left empty, if a sale froze a cut its product would not give, if
  more was sold or returned than received, or if a sequence would hand out an
  id already used.

- <a id="a-wrong-record-is-corrected-and-the-correction-is"></a>**A wrong record is corrected, and the correction is kept.** "History stays
  fixed" means a record's figures are never rewritten by something else: a
  product edit never touches a past sale, and a sale's partner cut is frozen
  when it sells. It never meant a typo had to stay forever. So a sale, return
  or payment can be edited, for a mistake in it, or deleted, for one that
  should never exist, and the rule is kept in three ways. A correction changes
  only that record, and only what it was entered with: a sale's date,
  quantity and price, never its product or its frozen per-unit cut, so its
  partner cut is still the quantity times the cut agreed at the time; a
  return's date, quantity and notes, never its product; a payment's date,
  amount and notes. Moving a record to another product is a delete and a new
  entry. Every correction writes the whole record before, and after for an
  edit, to a corrections table in the same transaction, so the figures are
  corrected and what they were is still known. And that table only grows: a
  trigger refuses any change to it. The alternatives were delete-and-re-enter
  only, which would have re-frozen a sale's cut at today's share, and keeping
  no record of the change, which would have left the daily backup as the only
  trace.

- <a id="a-corrected-quantity-follows-the-rule-entering-it-followed"></a>**A corrected quantity follows the rule entering it followed.** A sale's or
  return's new quantity may be anything from 1 up to what is available plus
  its own units, the stock entering it would have seen, so no product is ever
  left with less than none. Zero is a delete. Deleting gives the units back,
  which can never break the rule. A product whose last sale or return is
  deleted has no history left, so it becomes deletable; the log keeps what was
  deleted and the product it belonged to.

- <a id="a-correction-is-confirmed-and-an-empty-one-is"></a>**A correction is confirmed, and an empty one is not logged.** A delete has a
  confirmation page that says what it changes, from the record's own figures,
  and the terminal asks yes or no after saying the same; only the API's DELETE
  is its own confirmation, as any API call is. A save that changes nothing
  writes nothing to the log, because nothing was corrected. The notice after a
  delete is confirmed against the log, so an id typed into the address cannot
  claim one.

- <a id="correcting-is-the-same-in-all-three-ways-in"></a>**Correcting is the same in all three ways in.** The pages, PUT and DELETE in
  the API, and the terminal's Fix options call the same psells functions,
  which hold every rule above. The API gained write routes for this, against
  the earlier rule that it only reads and sells, so that no way in is missing
  a correction the others can make. Each needs a session and the form token,
  as every write does. A PUT body holds exactly the fields that can change, and
  a test pins that, so the published description never offers a field that
  would be ignored.

- <a id="the-demos-database-is-changed-by-hand-from-a"></a>**The demo's database is changed by hand, from a script that proves it ran.**
  A deploy applies no migrations, and loads the sample records only into an
  empty database. So the corrections table, and the new sample records, reached
  the demo through one Run Command script: a backup to S3 first, the
  migration, then emptying the four record tables and loading the seed in one
  transaction, keeping the login. The first attempt reported success after the
  backup alone: the script had been piped into bash, and a command inside it
  read the rest of the script from the same input. It now runs from a file,
  and the caller fails unless the script printed its last line.


- <a id="monitoring-runs-on-grafana-clouds-free-tier-with-an"></a>**Monitoring runs on Grafana Cloud's free tier, with an agent on the
  server.** The server has about 350 MB free, less than Prometheus, Grafana
  and Loki need together. The hosted free tier costs nothing, needs no card
  and has no end date, keeps alerting when the Mac is asleep, and checks the
  site from outside. A stack on the Mac would stop whenever the Mac sleeps and
  could not see the server without a port opened; a minimal stack on the
  server would have risked its memory.

- <a id="only-the-demo-is-watched"></a>**Only the demo is watched.** The real business's records and activity never
  leave the Mac, and even a request log carries paths, record ids and timing
  about the business. The Mac keeps its backup check.
  *Later replaced, in whole or in part: [The Mac says when a job fails](#the-mac-says-when-a-job-fails), [A certificate is warned about while it can still be renewed](#a-certificate-is-warned-about-while-it-can-be-renewed).*

- <a id="two-slis-one-from-each-side"></a>**Two SLIs, one from each side.** Availability is measured from outside, as a
  visitor meets the site: 99.5% of checks of the login page pass over seven
  days. Latency is measured from inside, from every request nginx answers: 99%
  in under 500 ms. One that only the outside could see and one that only the
  server could; the stricter 99.9% was turned down because one small server
  with deploys would miss it.

- <a id="three-check-locations-every-two-minutes"></a>**Three check locations every two minutes.** Three, so the alert can need a
  majority and one location's network never pages; every two minutes, so the
  checks use 65% of the free 100,000 runs a month. Two locations every minute
  used 86%, five every five minutes took ten minutes to notice.

- <a id="one-alert-on-the-symptom"></a>**One alert, on the symptom.** It fires when the site is down for visitors,
  not on a cause such as memory, and by email, which needs nothing new. No data
  alerts too, because silence is not health. Burn-rate alerting on the error
  budget was turned down for now as harder to explain and to prove.

- <a id="nginxs-log-carries-only-what-the-slos-need"></a>**nginx's log carries only what the SLOs need.** On the server it leaves for
  Grafana Cloud, so each line holds time, host, method, path without its query
  string, status, bytes and timings, and never a visitor's address, a search
  term, a browser string or a referrer. Keeping the visitor's address would have
  helped trace a brute-force attempt, at the cost of sending visitors' addresses
  to a third party.

- <a id="the-agent-reads-the-journal-never-dockers-socket"></a>**The agent reads the journal, never Docker's socket.** On the server the
  proxy logs to journald, which rotates itself, and the agent reads it with
  only the journal group. Docker's socket, the usual way, is Docker's whole
  API even mounted read-only, which is root on the server. The cost is no
  per-container panels, which the SLOs do not need.

- <a id="the-agents-scan-has-a-dated-exception-as-nginxs"></a>**The agent's scan has a dated exception, as nginx's does.** Its newest image
  carries an OpenSSL with a high flaw that the agent, a Go program, never
  loads; the scan skips that one flaw until 30 November, and CI fails if the
  agent ever links OpenSSL. Building a patched image of our own would have
  meant a second image to publish and deploy; not scanning it would have let
  something ship that nothing checked.

- <a id="grafana-is-terraform-too"></a>**Grafana is Terraform too.** The checks, the SLOs, the alert, its email and
  the dashboard are in `infra/grafana/`, so a plan with no changes proves the
  live setup matches the code. The tokens stay in the Mac's Keychain and reach
  Terraform through the environment for one command, never in a file or the
  state.

- <a id="a-deploy-reloads-nginx"></a>**A deploy reloads nginx.** Compose recreates a container when its
  definition changes, not when a file mounted into it does, so a change to
  nginx's configuration alone used to wait for the next restart. The deploy
  now checks the configuration and reloads it; a configuration nginx refuses
  stops the deploy with the old one still running.

- <a id="the-failure-was-planned-real-and-written-up-as"></a>**The failure was planned, real and written up as if it were not.** The
  demo's database was stopped for fifteen minutes. A database stop was chosen
  over stopping the app, whose cause is obvious at once, and over exhausting
  memory, which could have taken the way into the server down with it. The
  postmortem is in `postmortems/`.

- <a id="what-the-failure-found-was-fixed-in-the-phase"></a>**What the failure found was fixed in the phase.** The app's health check
  said healthy while every page failed, so it now asks the database too. A
  missing database ended in a bare 500 and a traceback per request, so it is
  now a 503 with a sentence and Retry-After, and one log line. Sending the
  application's own errors to Grafana is left open, until what its log can
  contain has been checked for anything private.

- <a id="on-the-mac-a-login-job-starts-the-stack"></a>**On the Mac, a login job starts the stack.** Docker's restart policy
  brings the containers back on the server, but on 7 October 2026 Docker
  Desktop came back after a boot and restarted none of them, and the site
  stayed down until someone looked. A launchd job runs at login, waits for
  Docker Desktop and runs `docker compose up -d --wait --no-recreate`, which
  starts what is stopped and changes nothing that runs. Changing backup.sh to
  start everything was turned down: it runs at 09:00 only, so a later boot
  would wait until the next morning.

- <a id="psells-builds-its-own-nginx-image"></a>**PSells builds its own nginx image.** On 7 October 2026 nginx's image failed
  the scan on a second flaw, in zlib, after the pcre2 one, and nginx had not
  rebuilt its images in three weeks, though Alpine already had both fixes and
  OpenSSL's. Rather than collect dated exceptions for someone else's schedule,
  `nginx/Dockerfile` builds on the pinned official image and upgrades those
  packages only, and CI builds, scans and publishes it beside the app's image,
  in the same package under `nginx-<commit>`, so nothing new had to be made
  public or granted. The server runs it by digest as it runs the app, and both
  nginx exceptions are gone. The zlib exception stood for one deploy, while
  this was built. The agent keeps its exception: PSells does not build it.


- <a id="kubernetes-runs-on-the-mac-with-kind-and-the"></a>**Kubernetes runs on the Mac, with kind, and the sample records only.**
  Nothing is ever paid for, so not EKS; kind is a real cluster in Docker
  containers, the same on the Mac and in CI, created and deleted in seconds.
  It never holds the real records: those stay in the Compose stack, which is
  what the business runs on, and the cluster has its own database built from
  `schema.sql` and the seed. It answers on `127.0.0.1:9443`, so it can never
  collide with the real stack on 443.

- <a id="nginx-and-the-app-share-one-pod"></a>**nginx and the app share one pod.** The app trusts forwarded headers from
  nginx's one fixed address only; in a pod the two share a network, so that address is `127.0.0.1` and fixed by construction, where a
  separate nginx Deployment would reach the app from addresses that change
  with every restart. uvicorn listens on the pod's loopback only, so nothing
  else in the cluster can reach the app past nginx. nginx stays rather than
  an Ingress controller, because it carries PSells' headers, limits and name
  rules, which an Ingress would have to restate. A host alias maps `app` to
  the loopback, so nginx's snippet is the same file in Compose, on the server
  and in the pod.

- <a id="the-cluster-runs-cis-published-images-by-digest"></a>**The cluster runs CI's published images, by digest.** The images that run
  were scanned in CI, as on the server, and the cluster needs no build of its
  own. Each is written with its commit's tag beside the digest, and a test
  holds the app and nginx to the same commit. They move by hand.

- <a id="plain-yaml-with-kustomize-rendered-from-the-repositorys-own"></a>**Plain YAML with kustomize, rendered from the repository's own files.**
  No Helm: one application in one place has nothing to template. kustomize
  makes the ConfigMaps from `schema.sql`, the seed, nginx's files and the
  sample partner share where they are, so nothing is copied and nothing can
  drift; that needs `--load-restrictor LoadRestrictionsNone`, which
  `kubectl apply -k` cannot pass, so `up.sh` renders with `kubectl kustomize`
  and applies the output. Server-side apply, because client-side apply
  reported the database changed on every run when it had not.

- <a id="one-copy-of-the-database-password"></a>**One copy of the database password.** `up.sh` makes it once with
  `openssl rand`, passes it to kubectl on standard input and keeps it if it
  exists, since the database on its volume was made with it. The app gets it
  as `PGPASSWORD`, which libpq reads, and an address without a password, so no
  second Secret holds a copy built from it.

- <a id="the-clusters-certificate-is-its-own-from-the-macs"></a>**The cluster's certificate is its own, from the Mac's CA.** The browser
  trusts it with nothing new to install, and its key is not the real stack's,
  so a cluster's etcd never holds the key that serves the real records. It
  lives in `~/PSells-Kind/tls`, outside the repository, and `up.sh` refuses to
  run without it. nginx reads a certificate only when it starts, so `up.sh`
  restarts the pod when, and only when, the Secret changed.

- <a id="the-apps-probes-ask-uvicorn-not-the-database"></a>**The app's probes ask uvicorn, not the database.** With the database down
  the app answers every page with a 503 and a sentence. A probe that asked the
  database would take the only pod out of the Service, and the browser would
  get no answer at all, or restart an app that was not broken. Compose's health
  check still asks the database, because there it is what `--wait` and the
  proxy's start wait for.

- <a id="a-real-cluster-in-ci-and-deploy-waits-for"></a>**A real cluster in CI, and Deploy waits for it.** Every push builds the
  cluster from nothing with `up.sh` and a throwaway CA and checks it as a
  browser would, so a manifest that only looks right fails before it ships.
  kind is the release binary checked against a hash written in the workflow,
  rather than a community action, so no third-party code runs. A pod is ready
  a moment before its Service routes to it, so CI first waits, up to twenty
  seconds, until anything answers, then asks each question once. curl's own
  `--retry` was used at first and dropped: it also retries a 503 or a 504,
  which are answers to report, not to wait out.

- <a id="postgresql-is-ready-when-it-answers-over-tcp"></a>**PostgreSQL is ready when it answers over TCP.** On a new volume the image
  first runs a temporary server on its socket alone while it loads the init
  files, and `pg_isready` over the socket passed against that. On 8 October
  2026 CI's first request reached the app while the cluster's database was
  restarting into the real server, and got a 503. Every check now asks
  `pg_isready -h 127.0.0.1`: the cluster's probes, Compose's db and db-test,
  and the Tests workflow's service. The real database was recreated once for
  it, for about two seconds, with its volume kept.

- <a id="analytics-runs-on-the-real-records-on-the-mac"></a>**Analytics runs on the real records, on the Mac, and publishes nothing
  real.** The point of the analysis is the business, so the ETL reads the
  real database; everything it makes stays on the Mac, and the tests, CI and
  anything shown use invented records, as everywhere else.

- <a id="the-analytics-live-in-a-database-of-their-own"></a>**The analytics live in a database of their own.** An analysis table holds
  revenue and profit per sale, which are derived figures, and the business
  database stores facts only, with no exceptions. So the derived tables go in
  a separate PostgreSQL, the warehouse, rebuilt in full by every run and
  never edited, and whatever reads them later never touches the real
  records' database. Files under `data/` were turned down because the SQL
  views and the page that come next want a database; a schema inside the
  business database because it would have put derived figures beside the
  facts.

- <a id="analytics-has-its-own-compose-file"></a>**Analytics has its own Compose file.** Compose reads every variable in a
  file it is given, even for a service whose profile is not active, so a
  warehouse password required in `compose.yaml` would have stopped the real
  stack, its login job, its backup and the AWS deploy until each `.env` had
  one. `compose.analytics.yaml` is laid over `compose.yaml` only for
  analytics, as `compose.aws.yaml` is on the server, and a test keeps every
  analytics variable out of `compose.yaml`.

- <a id="the-etl-reads-as-a-read-only-role"></a>**The ETL reads as a read-only role.** `psells_etl` can SELECT the four
  business tables and the products view, which is what psells' own readers
  use, and nothing else: not the login's tables, not the corrections log, no
  write. Its transactions are read-only by default, and the grants stop a
  write even when that is switched off, so a bug or a compromised package in
  the analytics image cannot change a record. It cost one change to the real
  database, a role and its grants, made after a backup.

- <a id="pandas-gets-an-image-of-its-own"></a>**pandas gets an image of its own.** pandas and numpy are most of an
  image; the app's image, which serves the web, carries none of them, so
  there is nothing more there to scan or patch. The analytics image starts
  from the app's base, holds psells.py and the ETL, is built and scanned in
  CI on both architectures, and is not published, because only the Mac runs
  it.

- <a id="the-etl-asks-psells-for-every-figure"></a>**The ETL asks psells for every figure.** It reads through psells' own
  readers, never its own SQL against the business tables, and works out no
  business figure, so the warehouse cannot hold a second version of a rule.
  It reads in one repeatable-read snapshot, so the rows and the totals come
  from the same moment, and it commits only if the warehouse adds up to all
  nine of the dashboard's figures. The sums it checks with are a comparison,
  never a figure the warehouse serves.

- <a id="in-the-warehouse-a-discontinued-product-has-no-retail"></a>**In the warehouse, a discontinued product has no retail price.** The
  business rules store 0 for it, which an average or a comparison with the
  listed price would read as free. The warehouse leaves it empty, keeps the
  flag beside it, and a constraint holds the two together; the business
  database keeps its 0.

- <a id="the-analysis-is-shown-on-a-page-in-psells"></a>**The analysis is shown on a page in PSells, not in Power BI.** The plan
  had a Power BI dashboard, but Power BI Desktop does not run on a Mac, and a
  page in PSells can be seen on the demonstration. No page runs scripts, so
  its charts will be SVG drawn on the server.

- <a id="each-analytics-figure-is-worked-out-once-in-a"></a>**Each analytics figure is worked out once, in a warehouse view.** Margin,
  sell-through, shares and ranks are new figures psells has no answer for, so
  `analytics/views.sql` is their one implementation, and whatever shows them
  reads the views and works out nothing. A view that needs one of psells'
  own rules, such as whether a product is in stock, takes psells' answer,
  carried in by the ETL, rather than restating it in SQL.

- <a id="margin-is-summed-profit-over-summed-revenue-sell-through"></a>**Margin is summed profit over summed revenue; sell-through is units sold
  over units received.** A month's or a category's margin is its total
  profit over its total revenue, never an average of each sale's, which
  would weigh a small sale like a large one. A unit returned to the partner
  counts as not sold, the usual retail meaning. Ratios are left as unrounded
  fractions and are empty where there is nothing to divide by; rounding is
  for whatever displays them.

- <a id="no-average-sale-price-for-now"></a>**No average sale price, for now.** It would be a fractional number of
  cents, and PSells rounds money in one place only, where a percentage
  becomes a cut. It waits until something that shows the analysis needs it
  and the rounding can be decided.

- <a id="no-inventory-aging-for-now"></a>**No inventory aging, for now.** It needs the date each product came in,
  and products have none; working it out from sales would be wrong for
  exactly the products it is about, the ones that never sold. An intake date
  is a change to the business data model, left for later.

- <a id="the-analysis-is-read-from-the-warehouses-views"></a>**The analysis is read from the warehouse's views.** The page shows figures
  the views are the one home of, so the app reads them, as `psells_reader`, a
  role that can read the five views and nothing else. Moving the views' logic
  into psells.py would have let the page work everywhere today, at the price
  of a second copy of every figure. Where no warehouse is set up the page says
  so with a 200; where one is set up and does not answer, a 503, as a page
  without its database is. The address is optional in `compose.yaml`, so a
  stack without analytics needs nothing in `.env`.

- <a id="the-readers-grant-is-given-again-with-every-rebuild"></a>**The reader's grant is given again with every rebuild.** A grant goes with
  the view it is on, and the ETL drops and makes the views on every run, so
  the grant is at the end of `views.sql`, in the same transaction, only if the
  role exists. The role's own file only makes the role.

- <a id="charts-are-svg-drawn-on-the-server"></a>**Charts are SVG drawn on the server.** No page runs scripts and no style
  attribute is allowed, so a chart library was out. `charts.py` works out the
  geometry, the template places it, and colours come from classes in the one
  style block; a bar's exact figure is its tooltip, which needs no script.
  The cumulative revenue is a small chart of its own rather than a second
  axis on the monthly bars, which reads badly.

- <a id="ratios-are-shown-by-one-formatter"></a>**Ratios are shown by one formatter.** `psells.format_ratio`, the `percent`
  filter, turns a view's fraction into one decimal place, half away from
  zero, and shows "n/a" where there was nothing to divide by, as
  `format_cents` is the one place cents become text.

- <a id="the-style-block-and-its-hash-are-checked-where"></a>**The style block and its hash are checked where they meet.** The block is in
  the app's image and its hash in nginx's files, which ship separately: the
  demo's deploy brings both together, the Mac needs the app's rebuild followed
  by a reload of the proxy, and the cluster's pinned image fell behind the
  repository's nginx files without any status code changing. The Kubernetes
  workflow now hashes the served block and compares it with the policy.

- <a id="the-analytics-rebuild-themselves-every-hour"></a>**The analytics rebuild themselves every hour.** On the Mac a launchd job runs
  `refresh-analytics.sh` on the hour and at login; on the server a systemd
  timer runs the ETL. A run takes seconds and only reads the records, so an
  hour behind at most costs nothing. The Mac's job waits for a healthy
  database and never starts it, since starting the stack is the login job's,
  and never builds, so it runs only an image someone built on purpose.

- <a id="a-stale-warehouse-is-said-on-the-page"></a>**A stale warehouse is said on the page.** The Mac is unmonitored and the
  server's agent reads only nginx's journal, so a failing refresh would show
  only as old figures. The kpis view marks the warehouse stale when it is
  more than two hours old, two missed runs, and the page says so above the
  figures; each run's line, with the reason for a failure, is in the
  refresh's log or journal.

- <a id="the-demonstration-got-its-warehouse-inside-its-memory"></a>**The demonstration got its warehouse inside its memory.** Measured first:
  about 361 MiB available, the warehouse idling at about 34 MiB and the ETL
  peaking at about 97 MiB. Each runs under a hard ceiling, 128 MiB and
  192 MiB, so neither can squeeze the database or the app. The ETL's image is
  published by CI and pulled by digest like the others, its address follows
  the app's to RDS when that switch is on, and the three new passwords live
  in Parameter Store beside the database's, made by hand and never in
  Terraform's state.

- <a id="the-servers-analytics-settings-are-a-file-of-their"></a>**The server's analytics settings are a file of their own.** The backup and
  the certificate renewal lay `compose.aws.yaml` over `compose.yaml` alone;
  settings there for the warehouse or the ETL would name services those two
  never load, and break them. `compose.aws-analytics.yaml` is used only by
  the deploy and the hourly service.

- <a id="the-sample-data-is-generated-by-the-applications-rules"></a>**The sample data is generated, by the application's rules.** A business big
  enough for the charts, 80 products and a year of sales, is too much to
  write by hand correctly. `sample_data/generate_seed.py` writes it from a
  fixed random seed, so it is the same every time; it checks each product
  with psells' own rules and takes each sale's cut from psells' own function,
  so the invented records cannot break a rule the real ones must keep, and a
  test fails if the file is ever edited by hand. Its tests state what the
  seed must show as properties rather than naming its rows.

- <a id="the-architecture-is-drawn-from-text-and-checked-against-the"></a>**The architecture is drawn from text, and checked against the repository.** ARCHITECTURE.md's diagrams are Mermaid, which GitHub draws from text in the
  file, so they are reviewed and versioned like the code instead of being
  pictures that drift. A test fails if the document names a file the
  repository no longer holds, or holds a diagram Mermaid would not draw.

- <a id="a-runbook-procedure-is-tried-before-it-is-written-down"></a>**A runbook procedure is tried before it is written down.** A procedure nobody has followed tends to be wrong in the step that matters.
  Every one that can be tried safely was followed on the sample stack or a
  throwaway project first, and each says whether and how. Following README's
  restore that way found it broken on a new stack: the database was not
  empty, since its first start builds the tables, and the dump carried grants
  to a role a new server lacks. The restore now empties the database, goes in
  without grants in one transaction, and makes the role again. Rotating a
  read-only role's password, tried the same way, showed that the role's script
  takes its grants away until the next build, so the procedure rebuilds at
  once.

- <a id="a-destructive-command-is-one-guarded-chain"></a>**A destructive command is one guarded chain.** The runbook's commands are copied and run as they stand. The restore, which
  empties the database, is therefore one chain that starts by checking the
  named dump exists and stops at the first step that fails, so a mistyped name
  changes nothing; a placeholder is never inside a command that acts, but in
  one of its own beside the command that lists its value. A test keeps the
  restore one chain, and keeps every volume-removing command to the sample
  stack.

- <a id="decisions-keep-their-order-with-an-index-by-area"></a>**Decisions keep their order, with an index by area.** DECISIONS.md is kept in the order the decisions were made, because the
  reasoning often depends on what came before, and an index by area at the
  top links to each one. A decision later replaced is not rewritten but ends
  with a line linking to what replaced it. A test fails if a decision is
  missing from the index or a link lands nowhere.

- <a id="each-backup-leaves-the-mac-encrypted-and-proved"></a>**Each backup leaves the Mac, encrypted, and is proved.** Every copy of the real records was on
  the Mac's own disk, so one lost or broken Mac would have lost the
  business. Each morning's proved dump and its configuration now go to iCloud
  Drive as one archive encrypted with age, so iCloud only ever holds
  ciphertext. The Mac keeps only the public key, which can lock and not
  unlock. The private key is in the Keychain, so each copy is decrypted the
  morning it is made and compared byte for byte with the original before it
  takes its name, and in a password manager, so a lost Mac loses nothing.
  A copy that fails the comparison is never kept, and the backup reports it.

- <a id="the-mac-says-when-a-job-fails"></a>**The Mac says when a job fails.** Nothing watches the Mac, so a backup that stopped working
  would be found only on the day it was needed. Each background job shows a
  macOS notification, with a sound and its reason, when it fails; the hourly
  refresh shows one only on its first failure after a run that worked, so a
  night with Docker stopped is one notification. The message reaches
  AppleScript as an argument, never as part of the script, and a notification
  that cannot be shown never changes how the job fails. It carries a reason,
  never a figure.

- <a id="a-certificate-is-warned-about-while-it-can-be-renewed"></a>**A certificate is warned about while it can still be renewed.** Each morning's backup
  checks the Mac's certificate, the cluster's and the CA, and notifies a month
  before one ends, every morning until it is renewed, naming the command. The
  CA is warned about earlier, 30 days before it has 397 days left, because
  from then on make-certificate.sh refuses to sign a certificate that would
  outlive it; a warning a month before the CA's own end would have come a year
  after renewals began to fail. Like make-certificate.sh, the check reads what
  OpenSSL prints rather than its exit status, and uses OpenSSL rather than the
  LibreSSL macOS puts first on launchd's path. A warning never fails the
  backup.
