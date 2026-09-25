"""Browser test of sign-in, workspace switching and conversation persistence.

Starts three things on free local ports, drives a real Chromium through the
frontend, then stops them:

    - the fixture documentation site (tests/suites/fixtures/site)
    - the API with the test fakes and a throwaway database (serve_backend.py)
    - the Vite dev server pointed at that API

    pip install playwright==1.56.0 && python -m playwright install chromium   # once
    python tests/e2e/run_e2e.py            # or: ./run-tests.sh e2e
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
FRONTEND = BACKEND.parent / "frontend"
SITE = BACKEND / "tests" / "suites" / "fixtures" / "site"
EMAIL, PASSWORD = "demo@e2e.test", "demo-password"

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    print("Playwright is not installed: pip install playwright==1.56.0 && python -m playwright install chromium")
    sys.exit(2)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_for(url: str, seconds: int = 90) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=2)
            return
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    raise SystemExit(f"{url} did not come up")


results: list[tuple[str, bool]] = []


def check(name: str, ok) -> None:
    results.append((name, bool(ok)))
    print(("  PASS  " if ok else "  FAIL  ") + name)


def run(app: str, api: str, site: str) -> None:
    def call(method, path, token, body=None):
        req = urllib.request.Request(
            api + path, method=method, data=json.dumps(body).encode() if body else None,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            text = r.read()
            return json.loads(text) if text else None

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page_errors: list[str] = []
        page.on("pageerror", lambda e: page_errors.append(str(e)))
        account = lambda: page.get_by_role("button", name=re.compile("Sinchana"))  # noqa: E731

        page.goto(app + "/ask")
        page.wait_for_url("**/login")
        check("signed out: /ask redirects to /login", page.url.endswith("/login"))

        page.fill("#login-email", EMAIL)
        page.fill("#login-password", "wrong")
        page.click("button[type=submit]")
        expect(page.get_by_role("alert")).to_contain_text("Email or password is incorrect")
        check("wrong password shows an error", True)

        page.fill("#login-password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/ask")
        check("sign-in returns to the page first asked for", page.url.endswith("/ask"))
        token = page.evaluate("JSON.parse(localStorage.getItem('kp.session')).token")

        sent: list[dict] = []
        page.on("request", lambda r: sent.append(r.headers) if r.url.startswith(api) else None)

        source = call("POST", "/api/sources", token, {"kind": "website", "location": f"{site}/docs/"})
        for _ in range(60):
            status = next(s for s in call("GET", "/api/sources", token) if s["id"] == source["id"])["status"]
            if status in ("ready", "failed"):
                break
            time.sleep(0.5)
        check("fixture site indexed", status == "ready")

        page.fill("#chat-input", "can i edit an invoice after sending it")
        page.keyboard.press("Enter")
        expect(page.get_by_text("Invoices › Editing an invoice after sending").first).to_be_visible(timeout=15000)
        page.fill("#chat-input", "how do i invite a team member")
        page.keyboard.press("Enter")
        expect(page.get_by_text("Team › Inviting a team member").first).to_be_visible(timeout=15000)
        check("question and follow-up answered with citations", True)
        check("the browser never sends X-Organization-Id", all("x-organization-id" not in h for h in sent))
        check("the browser sends its bearer token", any(h.get("authorization", "").startswith("Bearer ") for h in sent))

        page.get_by_role("link", name="Insights").click()
        page.get_by_role("link", name="Ask").click()
        expect(page.get_by_text("how do i invite a team member")).to_be_visible()
        check("conversation kept after visiting another page",
              page.get_by_text("can i edit an invoice after sending it").is_visible())

        page.fill("#chat-input", "how do i refund a payment")
        page.keyboard.press("Enter")
        page.get_by_role("link", name="Sources").click()
        page.wait_for_timeout(1500)
        page.get_by_role("link", name="Ask").click()
        expect(page.get_by_text("Payments › Refunds").first).to_be_visible(timeout=15000)
        check("an answer that arrived while on another page is shown", True)

        page.reload()
        expect(page.get_by_text("how do i refund a payment")).to_be_visible(timeout=10000)
        check("conversation kept after a full reload",
              page.get_by_text("can i edit an invoice after sending it").is_visible())

        for tab, path in [("This period", "/"), ("Insights", "/insights"), ("Report", "/report"),
                          ("Sources", "/sources"), ("Evaluation", "/evaluation"), ("Research", "/research")]:
            page.get_by_role("link", name=tab, exact=True).click()
            page.wait_for_url(f"**{path}")
            page.wait_for_load_state("networkidle")
        check("every section opens while signed in, without being sent to sign-in", "/login" not in page.url)
        page.get_by_role("link", name="Ask").click()

        account().click()
        check("account menu shows the user", page.get_by_text(EMAIL).is_visible())
        page.keyboard.press("Escape")

        call("POST", "/api/workspaces", token, {"name": "Second product"})
        page.reload()
        account().click()
        page.get_by_role("menuitemradio", name="Second product").click()
        expect(page.get_by_text("What do you need help with?")).to_be_visible(timeout=10000)
        check("switching workspace in the account menu shows that workspace's own conversation",
              not page.get_by_text("how do i refund a payment").is_visible())
        account().click()
        page.get_by_role("menuitemradio", name="Default workspace").click()
        expect(page.get_by_text("how do i refund a payment")).to_be_visible(timeout=10000)
        check("switching back restores the first conversation", True)

        account().click()
        page.get_by_role("menuitem", name="Sign out").click()
        page.wait_for_url("**/login")
        check("sign out lands on /login with a notice", page.get_by_text("You have signed out.").is_visible())
        check("session removed from the browser", page.evaluate("localStorage.getItem('kp.session')") is None)
        try:
            call("GET", "/api/sources", token)
            revoked = False
        except urllib.error.HTTPError as e:
            revoked = e.code == 401
        check("the old token is refused by the server", revoked)
        page.goto(app + "/report")
        page.wait_for_url("**/login")
        check("protected pages redirect after sign-out", True)

        page.fill("#login-email", EMAIL)
        page.fill("#login-password", PASSWORD)
        page.click("button[type=submit]")
        page.wait_for_url("**/report")
        page.get_by_role("link", name="Ask").click()
        expect(page.get_by_text("how do i refund a payment")).to_be_visible(timeout=10000)
        check("conversation kept across sign-out and sign-in", True)

        page.get_by_role("button", name="New conversation").click()
        expect(page.get_by_text("What do you need help with?")).to_be_visible()
        page.reload()
        expect(page.get_by_text("What do you need help with?")).to_be_visible(timeout=10000)
        check("New conversation starts empty and stays new after reload", True)

        page.evaluate("""() => { const s = JSON.parse(localStorage.getItem('kp.session'));
                                  s.token = 'forged'; localStorage.setItem('kp.session', JSON.stringify(s)); }""")
        page.reload()
        page.wait_for_url("**/login", timeout=10000)
        check("an ended session sends the user to /login with a reason",
              page.get_by_text("Your session has ended").is_visible())
        check("no uncaught errors in the page", not page_errors)
        browser.close()


def main() -> None:
    if not (FRONTEND / "node_modules").exists():
        raise SystemExit("Run `npm ci` in frontend/ first.")
    site_port, api_port, app_port = free_port(), free_port(), free_port()
    site, api, app = (f"http://127.0.0.1:{p}" for p in (site_port, api_port, app_port))
    npx = shutil.which("npx") or "npx"
    procs = [
        subprocess.Popen([sys.executable, "-m", "http.server", str(site_port), "--bind", "127.0.0.1"],
                         cwd=SITE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([sys.executable, str(Path(__file__).with_name("serve_backend.py")), str(api_port), app],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL),
        subprocess.Popen([npx, "vite", "--port", str(app_port), "--host", "127.0.0.1", "--strictPort"],
                         cwd=FRONTEND, env={**os.environ, "VITE_API_BASE_URL": api},
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=os.name == "nt"),
    ]
    try:
        wait_for(f"{api}/api/health")
        wait_for(app)
        wait_for(f"{site}/docs/")
        run(app, api, site)
    finally:
        for proc in procs:
            proc.terminate()
    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} browser checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
