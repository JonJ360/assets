"""Offline browser checks: synthetic fixture only; all network requests blocked."""
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def portal():
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        page.route("**/*", lambda route: route.abort())
        page.set_content((ROOT / "irp.html").read_text(encoding="utf-8"))
        page.add_style_tag(content="*, *::before, *::after { transition: none !important; animation: none !important; }")
        page.evaluate("""() => {
          hideLogin();
          window.calls = [];
          sb = async (path, options) => { calls.push({path, ...options}); return null; };
          ROWS = [{id:'offline-fixture', name:'Offline test vehicle', status:'Active',
            state:'ND', title_number:'00123-A', plate:'TEST', updated_at:'2026-01-01T00:00:00Z'}];
        }""")
        yield page
        browser.close()


def open_as(page, email):
    page.evaluate("email => { AUTH.s = email ? {email} : null; open('offline-fixture'); }", email)


def test_margi_can_edit_title_and_save_only_portal_fields(portal):
    open_as(portal, "margi@360-llc.com")
    assert portal.locator("#p_title_number").count() == 1, "IRP detail needs a title-number input"
    assert portal.locator("#p_title_number").input_value() == "00123-A"
    assert portal.locator("#p_state").input_value() == "ND"
    portal.locator("#p_title_number").fill("  000045-AB  ")
    portal.locator("#p_state").fill("  MN  ")
    portal.locator("#shSave").click()
    calls = portal.evaluate("calls")
    assert len(calls) == 1
    assert calls[0]["method"] == "PATCH"
    assert calls[0]["path"] == "assets?id=eq.offline-fixture"
    body = calls[0]["body"]
    assert body["title_number"] == "000045-AB"
    assert body["state"] == "MN"
    assert set(body) == {"title_number", "state", "plate", "reg_expires", "gvw", "unladen", "axles", "compliance_notes", "updated_at"}
    assert body["updated_at"]
    assert portal.evaluate("ROWS[0].title_number") == "000045-AB"
    assert not portal.locator("#sheet").evaluate("el => el.classList.contains('on')")


@pytest.mark.parametrize("email", ["viewer@example.invalid", None])
def test_viewer_and_signed_out_cannot_edit_or_invoke_save(portal, email):
    open_as(portal, email)
    assert portal.locator("#p_title_number").is_disabled()
    assert portal.locator("#p_state").is_disabled()
    assert not portal.locator("#shSave").is_visible()
    portal.evaluate("async () => { await document.querySelector('#shSave').onclick(); }")
    portal.locator('[data-t="on_irp"]').click()
    assert portal.evaluate("calls") == []
    assert portal.evaluate("ROWS[0].title_number") == "00123-A"


@pytest.mark.parametrize("email", ["jonj@360-llc.com", "shaynew@smionline.com", "MARGI@360-LLC.COM"])
def test_existing_editors_keep_title_access(portal, email):
    open_as(portal, email)
    assert portal.locator("#p_title_number").is_enabled()
    assert portal.locator("#p_state").is_enabled()
    assert portal.locator("#shSave").is_visible()


def test_failed_save_retains_form_and_original_record(portal):
    open_as(portal, "margi@360-llc.com")
    portal.evaluate("() => { sb = async () => { throw new Error('Offline test failure'); }; }")
    portal.locator("#p_title_number").fill("NEW-TITLE")
    portal.locator("#shSave").click()
    assert portal.locator("#sheet").evaluate("el => el.classList.contains('on')")
    assert portal.locator("#p_title_number").input_value() == "NEW-TITLE"
    assert portal.evaluate("ROWS[0].title_number") == "00123-A"
    assert portal.locator("#toast").inner_text() == "Offline test failure"


def test_title_fields_escape_stored_text_and_preserve_empty_values(portal):
    dangerous = '\"><img src=x onerror="window.injected=true">'
    portal.evaluate("value => { ROWS[0].title_number=value; ROWS[0].state=null; }", dangerous)
    open_as(portal, "margi@360-llc.com")
    assert portal.locator("#p_title_number").input_value() == dangerous
    assert portal.locator("#shBody img").count() == 0
    assert portal.locator("#p_state").input_value() == ""
    portal.locator("#p_title_number").fill("")
    portal.locator("#shSave").click()
    assert portal.evaluate("calls[0].body.title_number") == ""
    assert portal.evaluate("calls[0].body.state") == ""


def test_editor_access_is_rechecked_at_save_time(portal):
    open_as(portal, "margi@360-llc.com")
    portal.evaluate("AUTH.s = {email:'viewer@example.invalid'}")
    portal.locator("#shSave").click()
    assert portal.evaluate("calls") == []


def test_mobile_title_fields_stay_inside_existing_panel(portal):
    portal.set_viewport_size({"width": 390, "height": 844})
    open_as(portal, "margi@360-llc.com")
    for selector in ("#p_state", "#p_title_number"):
        box = portal.locator(selector).bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= 390
    assert portal.locator("#shSave").is_visible()
