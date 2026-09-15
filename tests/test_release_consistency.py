import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(name):
    return (ROOT / name).read_text(encoding="utf-8")


class ReleaseConsistencyTests(unittest.TestCase):
    def test_visible_release_is_v141_on_all_pages(self):
        self.assertIn('id="verTag">v1.41', text("index.html"))
        self.assertIn('IRP · IFTA · 2290 &nbsp; v1.41', text("irp.html"))
        self.assertIn('<span class="ver">v1.41</span>', text("docs.html"))

    def test_live_pages_refresh_every_five_minutes_without_stomping_edits(self):
        register = text("index.html")
        portal = text("irp.html")
        self.assertRegex(register, r"setInterval\([^;]*syncNow\(true\)[^;]*300000\)")
        self.assertRegex(portal, r"setInterval\([^;]*load\(true\)[^;]*300000\)")
        self.assertIn('!$("#sheet").classList.contains("on")', register)
        self.assertIn('!$("#sheet").classList.contains("on")', portal)

    def test_shayne_is_an_editor_on_both_apps_and_in_recovery_sql(self):
        editor = "shaynew@smionline.com"
        self.assertIn(editor, text("index.html"))
        self.assertIn(editor, text("irp.html"))
        self.assertIn(editor, text("supabase/live_schema_snapshot.sql"))

    def test_docs_do_not_publish_anonymous_write_policy(self):
        docs = text("docs.html")
        self.assertNotIn('create policy "anon all assets"', docs)
        self.assertNotIn("fine for an unlisted pages url", docs.lower())

    def test_docs_describe_auth_session_storage_accurately(self):
        docs = text("docs.html")
        self.assertNotIn("No <code>localStorage</code>", docs)
        self.assertIn("authentication session", docs)

    def test_portal_updates_modified_timestamp(self):
        portal = text("irp.html")
        self.assertRegex(portal, r"updated_at\s*:\s*new Date\(\)\.toISOString\(\)")

    def test_asset_table_spans_all_eleven_columns(self):
        app = text("index.html")
        self.assertIn('colspan="11" class="empty"', app)
        self.assertRegex(app, r'<tfoot><tr><td colspan="9">')


if __name__ == "__main__":
    unittest.main()
