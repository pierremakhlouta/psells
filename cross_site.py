"""Refusing writes that a browser sends on behalf of another site.

While uvicorn is running, any page open in the same browser can submit a form
to 127.0.0.1:8000, and the browser sends it as if the person had pressed the
button. Binding to localhost keeps the rest of the internet away from the port;
it does nothing about a browser on this machine being used as the messenger.
This is cross-site request forgery.

Every current browser labels a request with where it came from, and a page
cannot change the label: Sec-Fetch-Site says same-origin, same-site, cross-site
or none, and Origin names the site that sent it. A write labelled as coming from
anywhere but this site is refused before any route runs.

A request with neither header did not come from a browser acting for a page, so
it cannot be a forgery of this kind: the test client, curl, and the command
line's own users are all in that position. Such a request is let through.

This checks the labels rather than using a token in every form. A token would
need a secret kept somewhere and a hidden field in every form; it pairs
naturally with logins and sessions, and is the thing to revisit when
authentication is decided before deployment. Behind a proxy the scheme and host
seen here may be the proxy's, which is the other thing to revisit then.
"""

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}

# "none" is a navigation the person started themselves, such as a bookmark or a
# typed address. same-site is refused: another port on this machine is the same
# site, and a different local server is exactly who should not be writing here.
ALLOWED_FETCH_SITES = {"same-origin", "none"}


def refusal(method, headers, scheme, host):
    """Why this request should be refused, or None if it may go ahead.

    headers is anything with a case-insensitive get, as Starlette's are.
    """
    if method.upper() in SAFE_METHODS:
        return None

    fetch_site = headers.get("sec-fetch-site")

    if fetch_site is not None:
        if fetch_site in ALLOWED_FETCH_SITES:
            return None

        return f"Sec-Fetch-Site is {fetch_site}."

    origin = headers.get("origin")

    if origin is None:
        return None

    if origin == f"{scheme}://{host}":
        return None

    return f"Origin {origin} is not this site."
