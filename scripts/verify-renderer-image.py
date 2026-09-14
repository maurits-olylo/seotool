"""Exercise the actual non-root renderer image with local content only."""

import os
from pathlib import Path

from cryptography.fernet import Fernet
from playwright.sync_api import sync_playwright


def main() -> None:
    assert os.getuid() != 0, "Renderer must not run as root"
    cipher = Fernet(Fernet.generate_key())
    assert cipher.decrypt(cipher.encrypt(b"image-check")) == b"image-check"
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content('<html lang="en"><title>Check</title><h1>Before</h1></html>')
        page.evaluate("document.querySelector('h1').textContent = 'Rendered'")
        assert page.locator("h1").inner_text() == "Rendered"
        assert page.screenshot().startswith(b"\x89PNG")
        page.add_script_tag(content=Path("/opt/axe/axe.min.js").read_text())
        assert isinstance(page.evaluate("async () => (await axe.run()).violations"), list)
        browser.close()
    print("Non-root Chromium, JavaScript, screenshots, axe and Fernet verified offline.")


if __name__ == "__main__":
    main()
