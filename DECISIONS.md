# Decisions

PSells is an application for tracking a reselling business: the products held,
the sales made, items returned to suppliers, and payouts to a partner. This file
records the notable design choices and why; see the README for what the project
is and DATA_MODEL for how the data is structured. Kept short, the interesting
calls only, not every detail, and no specific business figures.

## Index by area

The decisions that shape PSells, grouped by what they concern. The decisions
themselves follow in the order they were made, which is kept because the
reasoning often depends on what came before. One later replaced, in whole or
in part, says so in its last line and points to what replaced it. Smaller
decisions, about 100 more, were cut on 13 October 2026 to keep this file
readable; they are in its history in git, up to commit 7ecee20.

### Data and business rules

- [Store facts, compute the rest](#store-facts-compute-the-rest)
- [History stays fixed](#history-stays-fixed)
- [Money is stored as whole cents](#money-is-stored-as-whole-cents)
- [Money is compared with a tolerance only where it is still a fraction](#money-is-compared-with-a-tolerance-only-where-it)
- [Nothing derived is stored, including how many units have sold](#nothing-derived-is-stored-including-how-many-units-have)
- [The retail-discontinued flag says what it means](#the-retail-discontinued-flag-says-what-it-means)
- [The partner-share value became two columns](#the-partner-share-value-became-two-columns)
- [Deleting a product with history is refused](#deleting-a-product-with-history-is-refused)
- [The schema carries the rules it can carry, and says which it cannot](#the-schema-carries-the-rules-it-can-carry-and)
- [Why a product ran out is worked out, not recorded](#why-a-product-ran-out-is-worked-out-not)
- [A wrong record is corrected, and the correction is kept](#a-wrong-record-is-corrected-and-the-correction-is)
- [Categories and conditions are lists to choose from](#categories-and-conditions-are-lists-to-choose-from)
- [An item arrives before it is researched, and its stage is worked out](#an-item-arrives-before-it-is-researched-and-its-stage-is-worked-out)
- [Photos are files, kept without their metadata](#photos-are-files-kept-without-their-metadata)

### Storage and the database

- [JSON, then SQLite](#json-then-sqlite)
- [PostgreSQL only, and the tests run on it](#postgresql-only-and-the-tests-run-on-it)
- [The move from SQLite was one transaction, checked before it committed](#the-move-from-sqlite-was-one-transaction-checked-before)
- [Schema changes to an existing database are migration files, applied by hand](#schema-changes-to-an-existing-database-are-migration-files)

### Code structure and tests

- [Tests fake the commercial terms rather than reading them](#tests-fake-the-commercial-terms-rather-than-reading-them)
- [The features were tested before any of them was taken apart](#the-features-were-tested-before-any-of-them-was)
- [Warnings fail the tests](#warnings-fail-the-tests)
- [The sample data is generated, by the application's rules](#the-sample-data-is-generated-by-the-applications-rules)

### The API and the web pages

- [The API is a second way in, not a second implementation](#the-api-is-a-second-way-in-not-a)
- [Money crosses the wire as whole cents](#money-crosses-the-wire-as-whole-cents)
- [The endpoints are synchronous on purpose](#the-endpoints-are-synchronous-on-purpose)
- [The web pages call the application's functions directly, not the API](#the-web-pages-call-the-applications-functions-directly-not)
- ["Templates never compute" is enforced by reading them](#templates-never-compute-is-enforced-by-reading-them)
- [A save redirects; a refusal shows the form again](#a-save-redirects-a-refusal-shows-the-form-again)
- [Every list is one function, served three ways](#every-list-is-one-function-served-three-ways)
- [PSells is not an installable app](#psells-is-not-an-installable-app)
- [The home-screen icon is served; the app is not](#the-home-screen-icon-is-served-the-app-is-not)

### Security and the login

- [Real data stays out of the repo](#real-data-stays-out-of-the-repo)
- [Commercial terms live outside the repository](#commercial-terms-live-outside-the-repository)
- [The private CA can sign for one name and no address](#the-private-ca-can-sign-for-one-name-and)
- [nginx is the only way in, and the application believes nobody else](#nginx-is-the-only-way-in-and-the-application)
- [One name is answered, and every other refused](#one-name-is-answered-and-every-other-refused)
- [No scripts on any page](#no-scripts-on-any-page)
- [Passwords are hashed with Argon2id, and only length is required](#passwords-are-hashed-with-argon2id-and-only-length-is)
- [Sessions live in the database, and the database keeps only their hash](#sessions-live-in-the-database-and-the-database-keeps)
- [Every route needs a session, and one check says so](#every-route-needs-a-session-and-one-check-says)
- [A form token alongside the browser-label check, not instead of it](#a-form-token-alongside-the-browser-label-check-not)
- [The demo's login is public, and its records are put back every night](#the-demos-login-is-public-and-its-records-reset-nightly)
- [Other devices reach the Mac through Tailscale, not the Wi-Fi](#other-devices-reach-the-mac-through-tailscale-not-the-wi-fi)

### Containers and the Mac

- [Nothing is reachable beyond this machine](#nothing-is-reachable-beyond-this-machine)
- [A backup is a dump that has been restored](#a-backup-is-a-dump-that-has-been-restored)
- [Everything CI runs is pinned to its contents](#everything-ci-runs-is-pinned-to-its-contents)
- [An unfixable scan finding gets a dated exception, for the image it is in](#an-unfixable-scan-finding-gets-a-dated-exception-for)
- [PSells builds its own nginx image](#psells-builds-its-own-nginx-image)
- [Each backup leaves the Mac, encrypted, and is proved](#each-backup-leaves-the-mac-encrypted-and-proved)
- [The Mac says when a job fails](#the-mac-says-when-a-job-fails)
- [A certificate is warned about while it can still be renewed](#a-certificate-is-warned-about-while-it-can-be-renewed)
- [The app has a fixed address too](#the-app-has-a-fixed-address-too)

### AWS and Terraform

- [The cloud phases cost nothing, ever](#the-cloud-phases-cost-nothing-ever)
- [The cloud holds invented records only](#the-cloud-holds-invented-records-only)
- [No long-lived keys, and no SSH](#no-long-lived-keys-and-no-ssh)
- [Secrets live in Parameter Store and are written out at deploy](#secrets-live-in-parameter-store-and-are-written-out)
- [Terraform does not manage the access it runs with, or any secret](#terraform-does-not-manage-the-access-it-runs-with)
- [The managed database and the load balancer run on a switch](#the-managed-database-and-the-load-balancer-run-on)

### CI/CD

- [CI reaches AWS with OpenID Connect, not a stored key](#ci-reaches-aws-with-openid-connect-not-a-stored)
- [The pipeline can deploy and do nothing else on the server](#the-pipeline-can-deploy-and-do-nothing-else-on)
- [What runs is what was scanned](#what-runs-is-what-was-scanned)
- [A deploy waits for every check](#a-deploy-waits-for-every-check)
- [A deploy is checked from outside, and rolled back by hand](#a-deploy-is-checked-from-outside-and-rolled-back)

### Monitoring

- [Only the demo is watched](#only-the-demo-is-watched)
- [Two SLIs, one from each side](#two-slis-one-from-each-side)
- [One alert, on the symptom](#one-alert-on-the-symptom)
- [The failure was planned, real and written up as if it were not](#the-failure-was-planned-real-and-written-up-as)

### Kubernetes

- [Kubernetes runs on the Mac, with kind, and the sample records only](#kubernetes-runs-on-the-mac-with-kind-and-the)
- [nginx and the app share one pod](#nginx-and-the-app-share-one-pod)
- [A real cluster in CI, and Deploy waits for it](#a-real-cluster-in-ci-and-deploy-waits-for)

### Analytics

- [The ETL reads as a read-only role](#the-etl-reads-as-a-read-only-role)
- [The ETL asks psells for every figure](#the-etl-asks-psells-for-every-figure)
- [The analysis is shown on a page in PSells, not in Power BI](#the-analysis-is-shown-on-a-page-in-psells)
- [Each analytics figure is worked out once, in a warehouse view](#each-analytics-figure-is-worked-out-once-in-a)
- [Margin is summed profit over summed revenue; sell-through is units sold over units received](#margin-is-summed-profit-over-summed-revenue-sell-through)
- [The style block and its hash are checked where they meet](#the-style-block-and-its-hash-are-checked-where)

### Documents

- [A runbook procedure is tried before it is written down](#a-runbook-procedure-is-tried-before-it-is-written-down)
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

- <a id="commercial-terms-live-outside-the-repository"></a>**Commercial terms live outside the repository.** The default partner
  percentage is a real business term, so it is read from a configuration file
  under the ignored data folder rather than written into the source. The code
  ships with a placeholder sample instead. This keeps the figure private in a
  public repository, and it means renegotiating the rate is a one-line edit in
  one file rather than a code change.

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

- <a id="money-crosses-the-wire-as-whole-cents"></a>**Money crosses the wire as whole cents.** The same reasoning that put
  integers in the database: exact, no rounding in transit, and no decision about
  presentation made in a layer that has no business making one. Field names say
  so, so a value cannot be mistaken for dollars. Formatting belongs to whatever
  is showing a figure to a person, which is the interface that comes next.

- <a id="the-endpoints-are-synchronous-on-purpose"></a>**The endpoints are synchronous on purpose.** The obvious style for this
  framework is asynchronous, and it would be wrong here. Asynchronous code helps
  only when a function waits on something that can yield while waiting, and the
  database driver in use cannot: it blocks. An asynchronous endpoint calling it
  would hold up every other request on the server. Plain functions are run on a
  thread pool instead, which suits blocking work. The consequence is that one
  request can touch two threads, and the driver refuses a connection used from a
  thread other than the one that opened it, so each request opens its own
  connection and closes it at the end.

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

- <a id="a-save-redirects-a-refusal-shows-the-form-again"></a>**A save redirects; a refusal shows the form again.** Every form answers a
  successful save by sending the browser to another page to load, so refreshing
  cannot repeat it, which matters most for a sale: a repeated sale is a second
  sale with a second partner cut. A refusal writes nothing and shows the same
  form with a sentence beside each field that is wrong and everything already
  typed kept. Input that is wrong in itself and input the stock disagrees with
  are answered differently, the same distinction the API makes.

- <a id="postgresql-only-and-the-tests-run-on-it"></a>**PostgreSQL only, and the tests run on it.** The move off SQLite could have
  kept SQLite for the tests, in memory and with nothing to start, while
  production ran PostgreSQL. That would mean two schemas and two dialects, and
  every test passing against an engine that never runs the business. So SQLite
  was retired after the one-time move, and the suite runs against a real
  PostgreSQL: a throwaway one of its own, never the real one, each test inside a
  transaction that is rolled back. The price is that running the tests needs
  Docker.

- <a id="the-move-from-sqlite-was-one-transaction-checked-before"></a>**The move from SQLite was one transaction, checked before it committed.**
  Every row was copied with its id, and nothing was kept until the result
  matched the source in every row and column, every product's stock and partner
  cut, and every dashboard figure, each worked out by the same functions on both
  sides. Money being whole cents made that an exact comparison rather than one
  within a tolerance. A verified copy of the SQLite database was archived first,
  and the first PostgreSQL backup was restored before it was trusted.

- <a id="nothing-is-reachable-beyond-this-machine"></a>**Nothing is reachable beyond this machine.** Inside a container the server
  must listen on every interface, so the protection moved to how the port is
  published, which is to this machine only. The database publishes no port at
  all; only the application reaches it, and the terminal application runs inside
  the application's container rather than on the host. Its password lives in a
  file kept out of the repository and out of every image, and every setting is
  required, so a missing one stops the stack with a sentence instead of starting
  a database with no password.
  *Later replaced, in whole or in part: [Other devices reach the Mac through Tailscale, not the Wi-Fi](#other-devices-reach-the-mac-through-tailscale-not-the-wi-fi).*

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

- <a id="no-scripts-on-any-page"></a>**No scripts on any page.** The pages use none, so the
  Content-Security-Policy allows none, and allows the one style block by the
  hash of its exact text rather than allowing inline styles in general. Forms may post only to
  PSells, and no other site may frame it. A hash covers exact bytes, so a test
  renders a page, hashes its style block and fails, naming the new hash, if the
  template and the policy drift apart. Headers are added on error responses too,
  and all in one place, because the proxy silently drops a server's headers
  from any location that adds one of its own.

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

- <a id="a-form-token-alongside-the-browser-label-check-not"></a>**A form token alongside the browser-label check, not instead of it.** Each
  session has its own token, which every form carries in a hidden field and
  every write must send back; a program sends it in a header, and learns it
  from an endpoint whose answer another site cannot read. The label check stays
  in front: either stops a forged write alone, the token does not depend on the
  browser's labels, and the labels are what cover the login form, which has no
  session and so no token. The token is compared in constant time.

- <a id="schema-changes-to-an-existing-database-are-migration-files"></a>**Schema changes to an existing database are migration files, applied by
  hand.** The schema file builds tables only when a database is first created.
  A change is also written as a file that only adds, applied once after a
  backup, in a single transaction that stops at the first error. The same
  statements then live in two places, so a test builds a database both ways and
  compares every column, constraint, index and view. A migration tool that
  records which files have run was considered and waits for the managed
  database later on, when there will be more than one change to track.

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

- <a id="secrets-live-in-parameter-store-and-are-written-out"></a>**Secrets live in Parameter Store and are written out at deploy.** The
  database password is generated inside AWS as an encrypted parameter, free on
  the standard tier, and the deploy script writes it into a root-only settings
  file. Secrets Manager's rotation was more than a demonstration database
  needs.

- <a id="terraform-does-not-manage-the-access-it-runs-with"></a>**Terraform does not manage the access it runs with, or any secret.** The
  IAM user it runs as, its group and the root user are left out, so no plan
  can remove the way back in. The database password stays a parameter made by
  hand, because a managed value is copied into the state in plain text; only
  its path is written in the code. The address the budget's alerts go to is
  read from a file git ignores.

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

- <a id="why-a-product-ran-out-is-worked-out-not"></a>**Why a product ran out is worked out, not recorded.** "Sold out",
  "Returned", or a mix such as "2 sold, 1 returned of 3" follows from the
  quantities products_view already derives, so nothing new is stored and the
  reason cannot disagree with the stock. It is one psells function, which the
  page, the API and the terminal all call.

- <a id="every-list-is-one-function-served-three-ways"></a>**Every list is one function, served three ways.** Each list is a psells
  function. The page, the API route and the menu option each call it and only
  format the answer, and tests compare the page with the API and the terminal
  with the API, row by row. The API's existing routes are unchanged; the lists
  are new routes with response models of their own. The pages are at
  /out-of-stock, /sales-history, /returns-history and /payments-history,
  because /sales and /payments already belonged to the API and a form.

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

- <a id="one-alert-on-the-symptom"></a>**One alert, on the symptom.** It fires when the site is down for visitors,
  not on a cause such as memory, and by email, which needs nothing new. No data
  alerts too, because silence is not health. Burn-rate alerting on the error
  budget was turned down for now as harder to explain and to prove.

- <a id="the-failure-was-planned-real-and-written-up-as"></a>**The failure was planned, real and written up as if it were not.** The
  demo's database was stopped for fifteen minutes. A database stop was chosen
  over stopping the app, whose cause is obvious at once, and over exhausting
  memory, which could have taken the way into the server down with it. The
  postmortem is in `postmortems/`.

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

- <a id="a-real-cluster-in-ci-and-deploy-waits-for"></a>**A real cluster in CI, and Deploy waits for it.** Every push builds the
  cluster from nothing with `up.sh` and a throwaway CA and checks it as a
  browser would, so a manifest that only looks right fails before it ships.
  kind is the release binary checked against a hash written in the workflow,
  rather than a community action, so no third-party code runs. A pod is ready
  a moment before its Service routes to it, so CI first waits, up to twenty
  seconds, until anything answers, then asks each question once. curl's own
  `--retry` was used at first and dropped: it also retries a 503 or a 504,
  which are answers to report, not to wait out.

- <a id="the-etl-reads-as-a-read-only-role"></a>**The ETL reads as a read-only role.** `psells_etl` can SELECT the four
  business tables and the products view, which is what psells' own readers
  use, and nothing else: not the login's tables, not the corrections log, no
  write. Its transactions are read-only by default, and the grants stop a
  write even when that is switched off, so a bug or a compromised package in
  the analytics image cannot change a record. It cost one change to the real
  database, a role and its grants, made after a backup.

- <a id="the-etl-asks-psells-for-every-figure"></a>**The ETL asks psells for every figure.** It reads through psells' own
  readers, never its own SQL against the business tables, and works out no
  business figure, so the warehouse cannot hold a second version of a rule.
  It reads in one repeatable-read snapshot, so the rows and the totals come
  from the same moment, and it commits only if the warehouse adds up to all
  nine of the dashboard's figures. The sums it checks with are a comparison,
  never a figure the warehouse serves.

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

- <a id="the-style-block-and-its-hash-are-checked-where"></a>**The style block and its hash are checked where they meet.** The block is in
  the app's image and its hash in nginx's files, which ship separately: the
  demo's deploy brings both together, the Mac needs the app's rebuild followed
  by a reload of the proxy, and the cluster's pinned image fell behind the
  repository's nginx files without any status code changing. The Kubernetes
  workflow now hashes the served block and compares it with the policy.

- <a id="the-sample-data-is-generated-by-the-applications-rules"></a>**The sample data is generated, by the application's rules.** A business big
  enough for the charts, 80 products and a year of sales, is too much to
  write by hand correctly. `sample_data/generate_seed.py` writes it from a
  fixed random seed, so it is the same every time; it checks each product
  with psells' own rules and takes each sale's cut from psells' own function,
  so the invented records cannot break a rule the real ones must keep, and a
  test fails if the file is ever edited by hand. Its tests state what the
  seed must show as properties rather than naming its rows.

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

- <a id="the-app-has-a-fixed-address-too"></a>**The app has a fixed address too.** nginx looks up the app's address once, when it
  starts. The app's address was Docker's choice, so an app rebuilt on its
  own could come back on another, and every page was a 502 until nginx
  restarted. Compose restarts nginx after an "up" that names it, which the
  runbook's rebuild of the app alone does not, and it had worked only
  because Docker had handed back the same address. The app now has a fixed
  address beside nginx's, outside the range Docker hands out, and a test
  holds it there. Having nginx look the name up on every request was turned
  down: it changes how each request is proxied, and the cluster would need a
  different setting.

- <a id="the-demos-login-is-public-and-its-records-reset-nightly"></a>**The demo's login is public, and its records are put back every night.** A
  demonstration nobody can log in to shows a login page and nothing else. Its
  username and password are published, so anyone can use every page,
  including adding, editing and deleting the invented records, and each
  night a timer empties the records and the corrections log and loads the
  seed again, in one transaction that keeps the login. The corrections go
  with the records they describe, whose ids the seed hands out again. The
  password can be changed only on the server, never from the web, and the
  script refuses to run beside the real configuration. Turned down: a demo
  with no login, which would need a switch in the one check every route
  passes, a switch that set on the Mac would open the real business; and a
  read-only account, a new kind of account in every write route. The cost is
  that, until the night, what one visitor writes is seen by the next. Every
  page of the demo says so, from a setting only the server's
  compose.aws.yaml makes.

- <a id="psells-is-not-an-installable-app"></a>**PSells is not an installable app.** It was made one
  on 13 October 2026, in five commits: an icon from the logo, a web app
  manifest and iPhone tags served by nginx before the login, a service worker
  that showed an offline page and never a stored one, and Playwright tests
  on an emulated iPhone and Android phone in the Kubernetes check. Pierre
  then had it taken out, the same day, before the demo ever served it: a
  phone can reach only the demo, the Mac's Dock works from Safari without
  any of it, and push notifications would wait for private access to the
  Mac. Reverting it kept the security policy allowing no script at all. The
  work is in git, from dab119f to 594e0aa, should it be wanted again.
  *Later replaced, in whole or in part: [Other devices reach the Mac through Tailscale, not the Wi-Fi](#other-devices-reach-the-mac-through-tailscale-not-the-wi-fi).*

- <a id="other-devices-reach-the-mac-through-tailscale-not-the-wi-fi"></a>**Other devices reach the Mac through Tailscale, not the Wi-Fi.** Pierre's
  brother joined the business, working from his own MacBook and iPhone, and
  Pierre wanted to upload photos from his phone. Answering on the home Wi-Fi
  for those devices alone was the first plan, and could not work: behind
  Docker Desktop nginx sees every connection as coming from Docker's own
  address, so it cannot tell one device from another, and on any other
  network the laptop joined, a café's included, the login page would answer
  everyone there. Tailscale lets in only the tailnet's members, at home or
  away, with a Let's Encrypt certificate for the Mac's private ts.net name,
  so no new certificate authority is installed anywhere. `tailscale serve`
  ends HTTPS and passes each request to nginx on 127.0.0.1:8444, which
  answers only a ts.net name, by pattern so the private name stays out of the
  repository, and refuses any other with 421, keeping DNS rebinding closed.
  The same headers, login limit and login apply. Tailscale listens on 443 on
  every address, so PSells now also claims ::1:443 and ::1:80, which browsers
  try first for psells.localhost. Each person signs in with their own
  Tailscale account; PSells keeps one shared login. Everyone depends on the
  Mac being on.

- <a id="the-home-screen-icon-is-served-the-app-is-not"></a>**The home-screen icon is served; the app is not.** With the
  Mac's other devices reaching PSells through Tailscale, its address is
  saved to iPhones' home screens, and Safari asks for /apple-touch-icon.png
  at the site's root, without a session. nginx serves that one file, the
  logo's monogram from the reverted app work, under its two names, before
  the login, on every server that serves PSells. No manifest and no service
  worker: the security policy still allows no script at all.

- <a id="categories-and-conditions-are-lists-to-choose-from"></a>**Categories and conditions are lists to choose from.** With two
  people entering items, one category spelled two ways would split every
  count and chart in the analytics. Each list is a table of names, and a
  product keeps the name, with a foreign key on it: a name not on the list
  is refused by the database, whatever wrote it, and ON UPDATE CASCADE
  carries a rename to every product. A name keeps a product's rows readable
  without a join, as before. A value in use cannot be deleted; it is hidden
  instead, kept for its products and their history and not offered for a
  new item. A new name differing from one already there only in capitals is
  refused as the misspelling it most likely is. Conditions became Brand new, Open box, Like new, Used and
  Damaged, the free-typed ones mapped onto them by migration 0003, which
  also hid every category with nothing in stock, chosen by query so no real
  category is named in the repository. After that, hiding is by hand: a
  category never hides itself on running out. The two listing templates,
  Facebook and Instagram, are kept in the database too and are empty in the
  repository, so their pickup areas and hashtags stay out of it. A template
  using a placeholder PSells cannot fill is refused when saved, not found
  later in a listing.

- <a id="an-item-arrives-before-it-is-researched-and-its-stage-is-worked-out"></a>**An item arrives before it is researched, and its stage is worked out.**
  Pierre's brother takes items in and researches them; Pierre photographs
  and lists them. So an item's condition, retail price and listed price may
  be empty until someone fills them in. Its stage (Received, Researched,
  Photographed, Listed, then Sold or Returned) is worked out from what it
  has, the furthest reached winning, and never stored, for the same reason
  why a product ran out is not: a stored stage can disagree with the facts.
  Every existing product has a listed price, so each lands in Listed or Sold
  with nothing added. A sale freezes the partner's cut, and without a retail
  price a percentage cut is unknown, so a sale is refused until the retail
  price or a fixed payout is entered, rather than freezing a guess. The
  dates an item arrived and was first listed are stored, being facts nobody
  could work out later; products from before have no arrival date. Every
  save raises the product's version, so that a save made from a page opened
  before someone else's is refused: the edit page carries the version it
  was opened at, the terminal keeps the one it printed, and the UPDATE
  itself compares it, so nothing can slip in between a check and the
  write. Refused, the page shows the item as it now is, and the change is
  made again from that; nothing is merged, since two people's edits of one
  field cannot be merged by rule. A listed item's Edit page shows its listing text,
  filled in by psells from the platform's template: Facebook for every
  listed item, Instagram once "Also on Instagram" is ticked, which is how
  PSells records that it went there too. A line whose placeholder has
  nothing to say is left out rather than posted half empty: the retail
  price when it is unknown or the item is discontinued at retail, and the
  condition or the details when there are none. With more than one unit in
  stock, "Multiple quantities available" follows the price's line. The text
  sits in a read-only box, to be selected and copied, since no page runs a
  script that could copy it. How long an item has waited is worked out from its
  two stored dates: since it was listed, for a listed item, and since it
  arrived otherwise, counted by the database's date, the one the dates are
  stamped with, so two clocks are never mixed. Items from before the
  workflow have neither date; they wait "Unknown" and come first, being the
  oldest. A listed item waiting at least stale_listing_days, a figure in
  the ignored configuration file like the profit minimum, is flagged "Not
  selling" in the pipeline and the inventory; with none set nothing is. Each
  item's Edit page links to a search for its name on the Canadian Amazon,
  Best Buy and Walmart sites and on Facebook Marketplace, where the retail
  and Marketplace prices are looked up; the name is quoted into each
  address, so nothing in it can change the search. What is not known yet reads "Not
  yet" on the pages and in the terminal, and null in the API, never 0. The
  terminal application prints the Marketplace price, the listing details
  and whether the item is also on Instagram, and the API serves all three,
  but the terminal's edit does not ask for them, so an edit made there keeps
  them as stored rather than emptying research done on the pages. Asking
  would add three questions to every edit in a tool the pages have
  replaced for this work. Whether an item is worth listing is
  worked out too: the profit is the Marketplace price less the partner
  payout, and under the minimum set in the configuration file the item is
  flagged "Not worth listing", never hidden or refused, since it may be
  listed anyway. The minimum is a business figure, so it sits in the
  ignored configuration file beside the partner rate; with none set nothing
  is flagged, and an item whose profit is not known yet is never flagged. The
  pipeline page counts products, not units, at each stage, and lists only
  the four stages still being worked on; sold and returned items are
  counted there and listed on the out-of-stock page, which already shows
  them.

- <a id="photos-are-files-kept-without-their-metadata"></a>**Photos are files, kept without their metadata.**
  Each item's photos are files in their own Docker volume beside the
  database's, with a row each in `photos`, rather than in the database,
  which would make every backup and restore carry them. An upload is never
  kept as sent: Pillow turns it the right way up, shrinks it to 1600 pixels
  on its long side and writes it again as a JPEG with no EXIF, XMP or
  comments, so the location a phone records never reaches the disk. JPEG
  and PNG only: an iPhone converts its HEIC photos when Safari uploads them,
  and reading HEIC directly would take a second image library to keep
  patched. Up to ten photos of 25 MB each per upload, chosen by Pierre; one
  bad photo keeps none of them. nginx allows that larger body on the upload
  address alone, every other request staying at 64k, and the page security
  policy now allows images from PSells itself and nowhere else. Photos are
  served behind the login like every page. A product with photos is
  deleted only once its photos are, one by one, so deleting a product never
  quietly deletes files. Pillow is pinned at 12.3.0 rather than 13.0.0,
  which was two days old. The daily backup archives the photos after the database:
  every photo the database records must be in the archive, and a new
  archive is kept, and encrypted into iCloud, only when the photos changed,
  since a stored photo never changes; otherwise thirty identical copies of
  every photo would pile up in both places. The newest archive is kept
  however old. An archive whose iCloud copy fails is not kept, so the next
  morning makes and sends it again. Each photo downloads on its own, and all of an
  item's as one zip, for whoever posts the listing from another computer.
  A download is named by the item's id and the photo's place
  (psells-12-3.jpg), never by the uploader's file name or the item's name,
  so nothing typed reaches a header or someone's disk; the zip stores the
  JPEGs as they are rather than compressing them again. On the demo, whose
  login is public and whose server has 1 GiB, an upload carries at most
  three photos of 8 MB each; nginx's limit sits in each site's folder
  (photo-limit.conf), since it takes no variable, and a test holds each to
  what the app accepts. The nightly reset deletes the photos visitors
  uploaded, so a stranger's photo never outlives the night.
