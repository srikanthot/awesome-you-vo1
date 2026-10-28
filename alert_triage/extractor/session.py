"""Signed-in browser session for Alessa.

Alessa uses Microsoft sign-in with an authenticator code. For the POC the analyst signs in once
in the browser window this opens; the session is kept in a private browser profile folder and reused
by the extractor (its cookies are used for the data calls). When the session expires, run again and
sign in again.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

from playwright.sync_api import BrowserContext, Playwright

from ..config import ApiConfig

log = logging.getLogger("alessa")


def open_session(pw: Playwright, cfg: ApiConfig) -> BrowserContext:
    s = cfg.session
    Path(s.profile_dir).mkdir(parents=True, exist_ok=True)
    ctx = pw.chromium.launch_persistent_context(
        s.profile_dir, headless=s.headless, channel=s.browser_channel, accept_downloads=False,
    )
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(cfg.url(s.home_path))
    deadline = time.time() + s.sign_in_timeout_s
    asked = False
    while time.time() < deadline:
        if page.url.startswith(cfg.url(s.home_path)) and page.locator(s.ready_selector).first.is_visible():
            log.info("Alessa session ready")
            return ctx
        if not asked:
            print(">>> Sign in to Alessa in the browser window (authenticator code). Waiting...")
            asked = True
        page.wait_for_timeout(1000)
    ctx.close()
    raise TimeoutError(f"not signed in within {s.sign_in_timeout_s}s")
