"""Create the PSells account, or change its password.

Run inside the app container, where PSELLS_DATABASE_URL is already set:

    docker compose exec app python set_password.py

It asks for the username and then the password twice, without showing it.
Changing the password logs out every browser that was logged in. No web page
can do this: the password is set by whoever can reach this container, and
nobody else.

The work is done by auth.set_password. This file only asks the questions and
says what happened, so the rules have one home.
"""

import getpass
import sys

import auth
import psells


def run(connection, ask=input, ask_hidden=getpass.getpass):
    """Ask, set the password, and return the exit status.

    ask and ask_hidden are the two ways of asking, passed in so a test can
    answer them.
    """
    username = ask("Username: ").strip()

    problem = auth.username_problem(username)
    if problem:
        print(problem)
        return 1

    password = ask_hidden("New password: ")

    problem = auth.password_problem(password)
    if problem:
        print(problem)
        return 1

    if ask_hidden("The same password again: ") != password:
        print("The two passwords were different. Nothing was changed.")
        return 1

    try:
        auth.set_password(connection, username, password)
    except auth.AccountError as error:
        print(f"{error} Nothing was changed.")
        return 1

    print(f"The password for {username!r} is set. "
          "Every browser that was logged in has been logged out.")
    return 0


def main():
    try:
        connection = psells.connect()
    except psells.DatabaseUnavailable as error:
        print(f"Database error: {error}")
        return 1

    try:
        return run(connection)
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
