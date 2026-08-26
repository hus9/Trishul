"""Kite Connect daily login. Access tokens expire every day (~6am IST reset), so this
needs one manual browser step per day -- same shape as the IBKR paper/live gate in the
main Nujumi project, just a different broker's session model.

Usage:
    .venv/bin/python kite_auth.py
    # prints a login URL -> open it, log in, get redirected to a URL containing
    # "request_token=..." -> paste just that token back when prompted
    # access_token is cached to .kite_session.json (gitignored) for the rest of the day
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()

SESSION_CACHE = Path(".kite_session.json")


def get_kite() -> KiteConnect:
    """Returns an authenticated KiteConnect client, reusing today's cached token
    if present, else running the interactive login flow."""
    api_key = os.environ["KITE_API_KEY"]
    kite = KiteConnect(api_key=api_key)

    if SESSION_CACHE.exists():
        cached = json.loads(SESSION_CACHE.read_text())
        kite.set_access_token(cached["access_token"])
        try:
            kite.profile()  # cheap call to check the token is still valid today
            return kite
        except Exception:
            pass  # expired -- fall through to re-login

    api_secret = os.environ["KITE_API_SECRET"]
    print(f"Login here, then paste the request_token from the redirect URL:\n{kite.login_url()}")
    request_token = input("request_token: ").strip()
    session = kite.generate_session(request_token, api_secret=api_secret)
    kite.set_access_token(session["access_token"])
    SESSION_CACHE.write_text(json.dumps({"access_token": session["access_token"]}))
    return kite


if __name__ == "__main__":
    kite = get_kite()
    print(f"logged in as {kite.profile()['user_name']}")
