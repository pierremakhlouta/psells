# Decisions

PSells is an application for tracking a reselling business: the products held,
the sales made, items returned to suppliers, and payouts to a partner. This file
records the notable design choices and why; see the README for what the project
is and DATA_MODEL for how the data is structured. Kept short, the interesting
calls only, not every detail, and no specific business figures.

- **JSON, then SQLite.** Started with JSON storage because it maps directly onto
  Python's lists and dicts, preserves value types, and keeps the early model
  simple while the data structure is being worked out. The move to SQLite
  happened once querying and relationships became the point: items, sales,
  returns and payments needed reliable links, real queries, and a storage layer
  able to refuse bad data rather than one trusting the application to be careful
  every time.

- **Store facts, compute the rest.** Only raw facts are saved (an item exists, a
  sale happened, a payment was made). The stored data is the source of truth, and
  everything derived (available stock, revenue, profit, partner totals, the
  dashboard) is calculated from it, never stored. Storing derived values just
  lets them drift out of sync with the facts.

- **People use names, the program uses IDs.** Each item gets an internal ID it
  never has to show, so existing physical stock needs no relabeling. Sales and
  returns link to items by ID under the hood while the user works by name; if
  multiple items share a name, the app asks the user to choose the correct one.

- **History stays fixed.** Each sale records its own figures at the moment it
  happens, so later changes to an item never rewrite the numbers on past sales.
  For example, changing an item's price later does not change the price recorded
  on an earlier sale.

- **Real data stays out of the repo.** Actual inventory and financials are never
  committed, preventing accidental exposure of business data. Everything under
  the data folder is ignored with no exceptions, so no rule has to be trusted to
  tell real records from fake ones. Invented sample data lives in its own folder
  and is copied into place by anyone who wants to run the app.

- **Discontinued items are marked, not inferred.** Some stock is no longer sold
  at retail and has no retail price to work from. Rather than letting a zero
  price quietly stand for that, items carry an explicit flag, so the meaning
  lives in the data instead of in the owner's head. A discontinued item takes a
  fixed per-unit partner amount and the application refuses the other modes,
  because a percentage of a price the item no longer has is not a number worth
  computing.

- **Commercial terms live outside the repository.** The default partner
  percentage is a real business term, so it is read from a configuration file
  under the ignored data folder rather than written into the source. The code
  ships with a placeholder sample instead. This keeps the figure private in a
  public repository, and it means renegotiating the rate is a one-line edit in
  one file rather than a code change.

- **The spreadsheet was cleaned before it was imported.** The original workbook
  carried the partner's terms in three different places, including free text
  inside a condition column and inside notes. Rather than write parsing logic
  against inconsistent prose, the source was given explicit columns first, so the
  one-time import became a straight mapping with nothing inferred. The importer
  builds every record in memory, validates the whole result, and writes both
  files or neither, because a half-finished import gives no way to tell which
  half is real.

- **The application became importable.** The menu loop used to run at the top
  level of the file, so merely importing it started the interactive menu. That is
  why the one-time import script could not reuse a single helper and had to
  duplicate its validation instead. The loop now sits behind an entry-point
  guard, so the file can be read as a library or run as a program. The same
  startup path checks the configuration file once and exits with a sentence if it
  is missing or unusable, rather than raising a stack trace later, the first time
  a product happens to be displayed. Failing immediately with an explanation
  beats failing halfway through a task.

- **Calculations were separated from printing.** The dashboard used to read four
  files, work out nine figures, and print them, all in one function, so there was
  no way to check the arithmetic except by reading terminal output. The figures
  now come from a function that takes the four datasets and returns them as a
  set of named values; the dashboard only fetches and displays. This was done to
  make the totals testable, but the same separation is what a future web
  interface needs, since that interface must call the same logic rather than work
  the totals out a second time for itself. The change was confirmed to alter
  nothing by comparing the dashboard output against real data before and after.

- **Tests fake the commercial terms rather than reading them.** Because the
  default partner percentage lives in an ignored configuration file, a test that
  exercised the default mode for real would depend on a private figure and would
  fail anywhere that file does not exist, which includes every automated run on a
  build server. Tests replace the function that reads the configuration with one
  returning an invented number. That keeps the real term out of a public
  repository and keeps the tests independent of the machine running them.

- **Money is stored as whole cents.** Floating-point arithmetic cannot represent
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

- **Money is compared with a tolerance only where it is still a fraction.** Test
  assertions against stored money are exact, because stored money is an integer
  number of cents. The tolerance remains only for a figure computed from a
  percentage before it has been rounded to a cent. Quantities, being whole
  numbers, are compared exactly and always were.

- **Tests and the dependency audit are separate automated workflows.** Run as a
  single unit, a failing test would end the run before the audit executed, so a
  broken test would also hide whether the dependencies were safe. Kept apart,
  each reports its own result. The audit additionally runs on a weekly schedule,
  because vulnerabilities get discovered in dependencies that have not changed,
  and a check that only runs when code is pushed would never find them.

- **The test runner is pinned, the security scanner is not.** Pinning the test
  runner means every run uses the version the tests were written against, so a
  failure is a real failure rather than a change in the tool. The scanner is the
  opposite case: an older version simply knows about fewer vulnerabilities, so it
  is deliberately left to update itself.

- **Nothing derived is stored, including how many units have sold.** The rule
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

- **The retail-discontinued flag says what it means.** The field was renamed to make
  clear that it describes the retail market and not this business. It records
  that a product is no longer sold at major retailers, so no retail price exists
  to take a percentage of. It does not mean the product was dropped here: this is
  a reselling business, and such a product is still held, still listed, still
  sold, and still counted in stock. The old name carried a strong conventional
  meaning that contradicted the actual one, which is a different problem from a
  field whose name is merely imprecise, and a column name is read by every future
  query rather than only by the person who wrote it.

- **The partner-share value became two columns.** One column held a percentage
  for one mode and a cash amount for another, with a second column deciding which
  it was. That cannot be range-checked, since a percentage stops at one hundred
  and an amount does not, and once money counts cents the column would hold two
  different units with nothing to tell them apart. Splitting it lets the database
  state the rule directly: each mode allows exactly one shape, and the mode is
  still stored rather than inferred from which column is filled, for the same
  reason the retail flag is explicit.

- **Deleting a product with history is refused.** Deleting a product used to
  leave its sales pointing at nothing. Cascading the delete was rejected because
  it would remove those sales along with the product, silently changing revenue,
  profit and the balance owed to a real person, with no error and no way back
  except a backup; that also contradicts the rule that history stays fixed, which
  is the reason each sale freezes its own figures. Marking products deleted
  rather than removing them was considered and deferred, because hiding a product
  from a list is a different question from what a delete should do to history,
  and it can be added later. Refusing is the option that loses nothing and can
  still be changed; the other two are harder to walk back.

- **The schema carries the rules it can carry, and says which it cannot.** A
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

- **Browsing matches widely, choosing a product does not.** Search covers a
  product's name and its category, because forgetting the exact name of one of
  several hundred items is normal while the category is usually easy to
  remember. Selecting a product to sell, edit or delete still matches on the
  name alone. The two look like the same operation and are not: one shows a
  list, the other leads straight into an action on whichever id is typed, and a
  category match there would offer an entire category at once. The asymmetry is
  deliberate and has a test holding it in place, so widening it later has to be
  a decision rather than a slip.

- **The sample data is a SQL seed file, not JSON.** The invented records used to
  be copied into place as files the application read directly. They are now
  statements applied to a database built from the real schema, so anyone trying
  the project exercises the same constraints the real data does, and a sample
  record that would break a rule cannot be shipped by accident.

- **The features were tested before any of them was taken apart.** Ten functions
  prompted and printed and none had an automated test, which is why building an
  HTTP layer started with writing those tests rather than with writing an
  endpoint. Input is faked and output captured, so a test drives a menu function
  the way a person does. Written first, they pin what the application already
  does and prove an extraction changed nothing. Written afterwards they would
  only describe code that had already moved, and the one thing worth knowing,
  whether it still behaves the same, would be unknowable.

- **The API is a second way in, not a second implementation.** Every figure the
  endpoints return comes from the functions the command line already uses:
  stock from the products view, the partner cut from the one function that
  computes it, the dashboard from the one function that totals it. Two copies of
  a business rule do not stay equal, and the failure is silent, because both
  answers look reasonable. Tests assert that the API's figures equal a direct
  call to those same functions, so the rule is checked on every run rather than
  remembered.

- **Recording a sale is one function, and asking the questions is not part of
  it.** The menu version is a conversation: search, choose, quantity, price,
  date, with context carried between the steps. HTTP has no conversation. A
  request arrives complete and the server remembers nothing, so an endpoint
  cannot drive a function built out of prompts. What both callers share is
  everything that happens once the answers exist, and that is now its own
  function: check the rules, compute the cut, insert one row. The prompts feed
  it and so does a request body.

- **The shared function re-checks what the prompts already guarantee.** A
  prompt that refuses a quantity above the stock on hand makes the same check
  further down look redundant. It is not. The prompts are one caller, and the
  other is a request from outside that has guaranteed nothing at all. Several of
  the refusals now tested cannot be produced from the menu, which is exactly why
  they need to exist.

- **A malformed request and an impossible one get different answers.** The
  request model refuses a body that is wrong in itself, a missing field or a
  negative price or a date that is not a date, before the endpoint runs, and
  says which field. The shared function refuses a request that is well formed
  and that the stock disagrees with. A missing product answers 404, meaning
  correct the id; a stock conflict answers 409, meaning correct the sale. The
  two are carried by separate exception types rather than by matching on message
  text.

- **Money crosses the wire as whole cents.** The same reasoning that put
  integers in the database: exact, no rounding in transit, and no decision about
  presentation made in a layer that has no business making one. Field names say
  so, so a value cannot be mistaken for dollars. Formatting belongs to whatever
  is showing a figure to a person, which is the interface that comes next.

- **The API declares its own response shape.** Returning database rows directly
  would have been shorter and would have made the columns of a view into the
  published contract by accident, so renaming one would silently change what
  every caller receives. Declared shapes also document themselves, which is
  where the generated API documentation comes from, and they convert the 0 or 1
  SQLite stores for a flag into a real boolean.

- **The endpoints are synchronous on purpose.** The obvious style for this
  framework is asynchronous, and it would be wrong here. Asynchronous code helps
  only when a function waits on something that can yield while waiting, and the
  database driver in use cannot: it blocks. An asynchronous endpoint calling it
  would hold up every other request on the server. Plain functions are run on a
  thread pool instead, which suits blocking work. The consequence is that one
  request can touch two threads, and the driver refuses a connection used from a
  thread other than the one that opened it, so each request opens its own
  connection and closes it at the end.

- **The data location comes from the code, not from the shell.** The database
  and the configuration file used to be found by paths relative to whatever
  directory a process was started in. That produced three separate failures: a
  test suite that passed locally and failed in automation, a server that served
  nothing unless launched from one particular folder, and a sandbox copy that
  worked only as a side effect of changing directory. They now resolve beside
  the source file, with environment variables to override them, so pointing the
  application at a copy is a deliberate act and a deployment can point it at a
  mounted volume.

- **Runtime and development dependencies are separate files.** What the
  application needs in order to run is now listed apart from what is needed to
  work on it, so a deployment installs neither a test runner nor a spreadsheet
  library. The automated checks install both, and the vulnerability audit reads
  both files.

- **The web pages call the application's functions directly, not the API.** The
  pages and the API run in one process, and a page could have fetched its data
  from the API over the network instead. That would have doubled the work for
  every page, needed an HTTP client and a configured address, risked one request
  waiting on another inside the same small pool of threads, and made every page
  test depend on a running server. Calling the same functions the command line
  calls satisfies the rule that matters, one implementation of every business
  rule, and three narrower rules keep it honest: a page route does no arithmetic
  on money, stock or partner share; wherever a page shows a figure the API also
  serves, a test asserts the two agree; and templates format and never compute.

- **"Templates never compute" is enforced by reading them.** A test comparing
  page and API only catches a figure that disagrees, and a template recomputing
  profit correctly would pass it. So the tests parse every template the way the
  template engine does and fail on any arithmetic, and on any formatting filter
  other than the one that renders money. Adding a filter is therefore a decision,
  and the question to ask is whether it formats or computes.

- **Every write was separated from its prompts before a page used it.** Adding,
  editing, selling, returning, paying and deleting were each conversations the
  terminal holds with a person, which a web request cannot. Each was split into
  the prompting and a function that does the work and checks every rule again,
  because a caller that is not a prompt has guaranteed nothing. Each split was
  made against the existing tests of the terminal behaviour and changed none of
  them, and bugs found while moving code were fixed in commits of their own.

- **A save redirects; a refusal shows the form again.** Every form answers a
  successful save by sending the browser to another page to load, so refreshing
  cannot repeat it, which matters most for a sale: a repeated sale is a second
  sale with a second partner cut. A refusal writes nothing and shows the same
  form with a sentence beside each field that is wrong and everything already
  typed kept. Input that is wrong in itself and input the stock disagrees with
  are answered differently, the same distinction the API makes.

- **Writes from another site are refused by checking where the browser says
  they came from.** Any page open in the same browser could otherwise submit a
  form to the running server, and binding it to this machine does not stop that.
  Every current browser labels each request with its origin in a way a page
  cannot change, and writes labelled as coming from anywhere else are refused
  before anything runs, including from another server on the same machine. The
  alternative, a secret token in every form, needs a secret stored somewhere and
  belongs with logins and sessions; it is the thing to add when authentication is
  decided.

- **On the web edit page, an emptied field means cleared.** The terminal treats
  a blank answer as "keep the current value". A web form opens already filled
  in, so a field that arrives empty was emptied on purpose, and treating it as
  "keep" would make it impossible to clear anything from a browser. The rule
  underneath is the same, notes may be empty; the two interfaces express it
  differently, and the terminal still cannot clear a note.

- **A page does not invent a default the business does not have.** A sale form
  starts at one unit and today's date, but with the price left blank, because
  the terminal has never assumed a price either. The listed price is shown
  beside the field instead.

- **Deleting is further away than every other action.** It is offered from a
  product's edit page rather than from each row, the page that offers it is the
  confirmation, and only its button deletes: a link alone never does, so no
  browser prefetch or link preview can. A product with sales or returns is told
  why it cannot be deleted instead of being offered a button that would then be
  refused.

- **Ids may be reused, until PostgreSQL.** Deleting the newest product frees its
  id for the next one. The original reasoning for allowing that, that products
  with history can never be deleted, still holds for the records. The web pages
  add one case it did not cover: a browser tab left open on a deleted product's
  form would post to the new product that inherited its id. Rebuilding the table
  to prevent reuse was judged not worth doing on live data at the end of a phase,
  because the planned move to PostgreSQL removes the case entirely. It did: ids
  now come from sequences, which never reuse a value.

- **The API grows no write endpoints until there is authentication.** The pages
  need the work separated from the prompts, and it has been. Putting HTTP
  endpoints on top of it now would add unauthenticated ways to change the
  records that nothing yet calls.

- **Pinned versions are checked weekly.** Pinning makes a build repeatable and
  then goes quiet forever. The vulnerability audit answers whether a pinned
  version is known to be unsafe; a weekly automated check answers whether it has
  aged, and opens a pull request that the same checks then test. Its pull
  requests appear on the repository under a bot's name, which was accepted
  knowingly before it was set up.

- **Money shown to people groups its thousands; money read back does not.** A
  figure is easier to read as 12,345.67 than as 12345.67, so everything displayed
  is grouped. The text an edit form holds for typing over is not, because it has
  to read back as exactly the amount that is stored.

- **PostgreSQL only, and the tests run on it.** The move off SQLite could have
  kept SQLite for the tests, in memory and with nothing to start, while
  production ran PostgreSQL. That would mean two schemas and two dialects, and
  every test passing against an engine that never runs the business. So SQLite
  was retired after the one-time move, and the suite runs against a real
  PostgreSQL: a throwaway one of its own, never the real one, each test inside a
  transaction that is rolled back. The price is that running the tests needs
  Docker.

- **The application's connection commits every write.** With PostgreSQL's
  driver a transaction opens at the first statement of any kind, and a write
  block inside an open transaction is only a savepoint: the write looks done and
  is lost when the connection closes. The application's connections run in
  autocommit, so each write block is a real transaction, and a test checks from
  a second connection that a write has landed, because nothing else in the suite
  can see the difference.

- **The types were chosen to change nothing.** Money stays whole cents in
  integer columns, not `numeric` and not `bigint`, because both would come back
  into Python as `Decimal`. The partner percentage is the same eight-byte float
  SQLite used; PostgreSQL's smaller one would lose digits. Dates became real
  dates, which the type itself checks. The retail flag stays 0 or 1. Categories
  sort by character code, as they did, rather than by the server's language,
  which can differ from one machine to the next.

- **The move from SQLite was one transaction, checked before it committed.**
  Every row was copied with its id, and nothing was kept until the result
  matched the source in every row and column, every product's stock and partner
  cut, and every dashboard figure, each worked out by the same functions on both
  sides. Money being whole cents made that an exact comparison rather than one
  within a tolerance. A verified copy of the SQLite database was archived first,
  and the first PostgreSQL backup was restored before it was trusted.

- **The image holds code and nothing else.** The records live in the database
  container and the configuration file is mounted read-only when the
  application starts, so an image can be shared without carrying a record. The
  Dockerfile names every file it copies rather than copying the folder, which
  holds the real data, and the build context leaves that data out as well.
  Every file is made readable before the server's own unprivileged user takes
  over, so the image does not depend on how the files happened to be saved on
  the machine that built it.

- **Nothing is reachable beyond this machine.** Inside a container the server
  must listen on every interface, so the protection moved to how the port is
  published, which is to this machine only. The database publishes no port at
  all; only the application reaches it, and the terminal application runs inside
  the application's container rather than on the host. Its password lives in a
  file kept out of the repository and out of every image, and every setting is
  required, so a missing one stops the stack with a sentence instead of starting
  a database with no password.

- **A backup is a dump that has been restored.** Each daily dump is restored
  into a throwaway database and its products counted against the live database
  before any older copy is deleted. The schedule moved from cron to macOS's own
  scheduler, which runs a missed job when the machine wakes; cron skipped every
  morning the laptop slept through. Every copy is still on the same disk as the
  database, which is the largest risk left, and waits for the cloud phases.

- **Warnings fail the tests.** A deprecation printed in a summary is read once
  and then ignored until the thing it warns about is removed. As an error it
  fails the day it appears. One known warning is allowed, matched on its exact
  text. On its first run the setting found a real leak: test connections that
  were never closed.

- **Everything CI runs is pinned to its contents.** A tag names a version and
  can be moved to different code after it is published, which is how a widely
  used scanning action was turned against its users in March 2026. Every action
  is pinned to a commit and every image to a digest, every workflow can only
  read the repository, and the built image is scanned for known
  vulnerabilities, failing on a serious one that has a fix and listing the rest.
  Pins age, so Dependabot proposes each update and the same checks judge it.

- **HTTPS on this machine before there is a server.** A certificate every
  browser trusts has to name a public address its issuer can check, and there
  is no server or domain yet. Holding HTTPS back until there is one would have
  put two new layers, a server and TLS, into one step, so that a failure had
  two possible causes. PSells is served over HTTPS on this machine now, with a
  certificate from a certificate authority of its own that this machine
  trusts, and a publicly trusted certificate arrives with the server. Everything
  else about serving it, the proxy, the redirect, the headers and which names
  are answered, carries over unchanged.

- **The private CA can sign for one name and no address.** Trusting a CA of
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

- **nginx is the only way in, and the application believes nobody else.** The
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

- **One name is answered, and every other refused.** A request for any other
  name is refused in the handshake, answered 421 if it names another host only
  inside the request, or redirected to the one name if it arrives over plain
  HTTP. The cross-site check only ever guarded writes; answering any name left
  pages readable by a hostile site that points its own name at this machine,
  which is called DNS rebinding. The redirect names its target in full rather
  than echoing the host it was sent, so it can only ever lead to PSells.

- **TLS 1.3 only, and HTTPS remembered for a year.** Every client is a current
  browser or command-line tool on this machine, so older protocol versions
  would only add handshakes nothing uses. Browsers are told to use nothing but
  HTTPS for this name for a year after one visit, for this name alone and on no
  preload list, which is undone by sending a zero lifetime over HTTPS.

- **No scripts on any page.** The pages use none, so the
  Content-Security-Policy allows none, and allows the one style block by the
  hash of its exact text rather than allowing inline styles in general. Forms may post only to
  PSells, and no other site may frame it. A hash covers exact bytes, so a test
  renders a page, hashes its style block and fails, naming the new hash, if the
  template and the policy drift apart. Headers are added on error responses too,
  and all in one place, because the proxy silently drops a server's headers
  from any location that adds one of its own.

- **The interactive API pages are turned off.** FastAPI builds them from
  JavaScript fetched from a CDN and pinned only to a major version, the same
  kind of floating reference that had been hijacked in the scanning action,
  and they would run it on the same origin as the forms, which the cross-site
  check trusts. The strict policy would refuse that code anyway. The same
  description of the API is still served as plain JSON.

- **The proxy runs as its own user, from the slim image.** Nothing in the
  stack runs as root, so the proxy listens above port 1024 inside its container
  and keeps its working files where its own user can write. The first scan of
  the full image failed on a library that only its optional add-on modules
  need, and PSells loads none of them; the slim variant is the same server
  without them. A test fails if the configuration ever asks for a module.

- **Authentication comes before anything is public.** Logins, sessions and a
  token in every form were left for this phase and are their own phase
  instead, built on this machine before a server puts PSells on a public
  address. Sessions need the HTTPS now in place.
