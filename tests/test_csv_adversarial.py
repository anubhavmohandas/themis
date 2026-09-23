"""CSV / general ingest against hostile filenames, headers and values (Phase 9).

What must hold: nothing an upload contains is ever executed, interpreted as a
path, or promoted into evidence. The raw text is kept (STEP 23) - but every
CSV THEMIS hands back neutralises formula-leading cells, and no route answers
an ugly file with a traceback.
"""
import csv, io, json, os, pathlib, sys, unittest
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from fastapi.testclient import TestClient
from themis.api import app, _csv_safe_cell
from test_preflight import btc_address

client = TestClient(app, raise_server_exceptions=False)   # what a browser sees: a 500 is a failure here, not an exception
ADDRS = [btc_address(i) for i in range(12)]
FORMULAS = ["=cmd|' /C calc'!A0", "+1+1", "-2+3", "@SUM(1+1)", "\t=1+1", "\r=1+1", "=HYPERLINK(\"http://evil\",\"x\")"]


def csv_bytes(header, rows, bom=False, newline="\n") -> bytes:
    buf = io.StringIO(newline="")
    w = csv.writer(buf, lineterminator=newline)
    w.writerow(header)
    w.writerows(rows)
    return (b"\xef\xbb\xbf" if bom else b"") + buf.getvalue().encode("utf-8")


def post(path, data: bytes, filename="u.csv", **form):
    return client.post(path, files={"file": (filename, data, "text/csv")}, data=dict(use_reference="false", **form))


def clean(test: unittest.TestCase, r, allowed=(200, 400, 422)):
    test.assertIn(r.status_code, allowed, r.text[:300])
    test.assertNotIn("Traceback", r.text)
    return r


def export_rows(aid, name="normalized_claims.csv"):
    r = client.get(f"/api/analysis/{aid}/export/{name}")
    assert r.status_code == 200, r.text[:200]
    return list(csv.reader(io.StringIO(r.text)))


class TestFilenames(unittest.TestCase):
    NAMES = ["../../etc/passwd", "..\\..\\file", "normal.csv", "a.csv.csv", "数据.csv", "émoji😀.csv", "tab\there.csv",
             "new\nline.csv", "nul\x00.csv", "x" * 10_000 + ".csv", "/absolute/path.csv", "C:\\win\\path.csv",
             "<script>alert(1)</script>.csv", "=cmd().csv", ".csv", "", "file.csv.gz.csv", "CON", "..", "."]

    def test_no_filename_reaches_the_filesystem_or_breaks_a_route(self):
        outside = pathlib.Path("/tmp") / f"themis-traversal-{os.getpid()}"
        before = set(os.listdir("/tmp"))
        for name in self.NAMES:
            body = csv_bytes(["address", "label"], [[a, "exchange"] for a in ADDRS])
            for path in ("/api/preflight", "/api/analysis"):
                r = clean(self, post(path, body, filename=name))
                if path == "/api/analysis" and r.status_code == 200:
                    self.assertIsInstance(r.json()["meta"]["dataset_name"], str)   # only ever a label; never opened
        self.assertFalse(outside.exists())
        leaked = [n for n in set(os.listdir("/tmp")) - before if "passwd" in n or "file" == n or "path.csv" in n]
        self.assertEqual(leaked, [])

    def test_a_gz_name_on_plain_text_and_a_csv_name_on_gzip_are_both_handled(self):
        import gzip
        plain = csv_bytes(["address", "label"], [[a, "exchange"] for a in ADDRS])
        self.assertEqual(clean(self, post("/api/analysis", plain, filename="x.csv.gz")).status_code, 400)
        r = clean(self, post("/api/analysis", gzip.compress(plain), filename="x.csv"))    # binary read as text: nothing usable
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["preflight"]["stopped"])


class TestColumnNames(unittest.TestCase):
    HEADERS = {
        "lowercase": ["address", "label"], "Capitalised": ["Address", "Label"], "UPPER": ["ADDRESS", "LABEL"],
        "sql": ["address; DROP TABLE x", "label"], "sql-quote": ['address"; DROP TABLE x; --', "label"],
        "script": ["<script>alert(1)</script>", "label"], "formula": ["=cmd()", "label"],
        "empty": ["", "label"], "duplicates": ["address", "address"], "dup-label": ["address", "label", "label"],
        "unicode": ["адрес", "метка"], "cjk": ["地址", "标签"], "bom-first": ["\ufeffaddress", "label"],
        "bom-second": ["address", "\ufefflabel"], "huge": ["a" * 10_000, "label"], "huge-address": ["address" * 1500, "label"],
        "whitespace": ["  address  ", " label "], "newline": ["ad\ndress", "label"], "null-ish": ["address\x00", "label"],
        "only-one": ["address"], "numeric": ["1", "2"], "single-space": [" ", "label"],
    }

    def test_every_header_is_answered_cleanly_by_preflight_and_analysis(self):
        for name, header in self.HEADERS.items():
            rows = [[ADDRS[i % 12], "exchange"][:len(header)] + [""] * max(0, len(header) - 2) for i in range(12)]
            body = csv_bytes(header, rows)
            for path in ("/api/preflight", "/api/analysis"):
                with self.subTest(header=name, route=path):
                    clean(self, post(path, body))

    def test_a_recognised_address_column_works_whatever_its_capitalisation_or_bom(self):
        for header in (["address", "label"], ["Address", "Label"], ["ADDRESS", "LABEL"]):
            r = post("/api/analysis", csv_bytes(header, [[a, "exchange"] for a in ADDRS], bom=True))
            self.assertEqual(r.status_code, 200)
            self.assertEqual(r.json()["meta"]["n_claims"], 12, header)

    def test_a_hostile_header_is_never_promoted_into_a_semantic_role(self):
        for header in (["address; DROP TABLE x", "label"], ["<script>", "label"], ["=cmd()", "label"]):
            pf = clean(self, post("/api/preflight", csv_bytes(header, [[a, "exchange"] for a in ADDRS]))).json()
            roles = {c["column"]: c["semantic_type"] for c in pf["preflight"]["columns"]}
            self.assertNotEqual(roles.get(header[0]), "attribution_source", header)   # not a source, not a claim role by accident of spelling
            self.assertEqual(set(roles), set(header))                                 # and reported back verbatim, as data

    def test_a_formula_header_is_neutralised_wherever_it_is_exported(self):
        body = csv_bytes(["address", "label", "=cmd()"], [[a, "exchange", "x"] for a in ADDRS])
        aid = post("/api/analysis", body).json()["analysis_id"]
        for name in ("normalized_claims.csv", "conflicts.csv"):
            for row in export_rows(aid, name):
                for cell in row:
                    self.assertFalse(cell.startswith(("=", "+", "-", "@", "\t", "\r")), (name, cell))


class TestValues(unittest.TestCase):
    HOSTILE = ["<script>alert(1)</script>", "<img src=x onerror=alert(1)>", "javascript:alert(1)",
               "'; DROP TABLE claims; --", '" OR ""="', "{{7*7}}", "${jndi:ldap://x}", "%s%s%s%n", "../../etc/passwd",
               "Ünï©ödé ✓ 日本語", "a\tb", "line1\r\nline2", "x" * 100_000, "   ", "", "NULL", "null", "None",
               "totally-unknown-category", "ransomware\x00", "\ud7ff"]

    def _upload(self, labels, **kw):
        rows = [[ADDRS[i % 12] if i < 12 else btc_address(500 + i), lab] for i, lab in enumerate(labels)]
        r = clean(self, post("/api/analysis", csv_bytes(["address", "label"], rows), **kw))
        return r

    def test_hostile_labels_never_crash_and_stay_unknown(self):
        r = self._upload(self.HOSTILE)
        self.assertEqual(r.status_code, 200)
        aid = r.json()["analysis_id"]
        claims = client.get(f"/api/analysis/{aid}/claims", params=dict(limit=500)).json()["claims"]
        self.assertTrue(claims)
        by_raw = {c["raw_label"]: c for c in claims}
        for lab in ("<script>alert(1)</script>", "'; DROP TABLE claims; --", "totally-unknown-category", "NULL", "{{7*7}}"):
            self.assertEqual(by_raw[lab]["canon"], "unknown", lab)                 # no forced taxonomy mapping
            self.assertEqual(by_raw[lab]["polarity"], "unknown", lab)
        self.assertEqual(by_raw["<script>alert(1)</script>"]["raw_label"], "<script>alert(1)</script>")   # raw kept verbatim

    def test_empty_and_blank_labels_are_rejected_not_defaulted(self):
        r = self._upload(["exchange", "", "   ", "exchange"] * 3)
        rejected = r.json()["preflight"]["validation"]["rejected_by_reason"]
        self.assertGreaterEqual(rejected.get("missing label", 0), 6)

    def test_an_extremely_long_label_is_kept_and_answered(self):
        r = self._upload(["x" * 500_000] + ["exchange"] * 11)
        self.assertEqual(r.status_code, 200)

    def test_formula_and_control_values_are_neutralised_in_every_csv_export(self):
        labels = FORMULAS + ["ok"] * 5
        aid = self._upload(labels, source_id="=cmd()").json()["analysis_id"]
        rows = export_rows(aid)
        header, body = rows[0], rows[1:]
        self.assertEqual(len(body), len(labels))
        for row in body:
            for cell in row:
                self.assertFalse(cell.startswith(("=", "+", "-", "@", "\t", "\r")), cell)
        raw_col = header.index("raw_label")
        exported = {r[raw_col] for r in body}
        for f in FORMULAS:
            self.assertIn("'" + f.strip(), exported)               # neutralised, but recognisably the same text (ingest trims)
        self.assertTrue({r[header.index("source")] for r in body} <= {"'=cmd()"})   # the source_id field too

    def test_the_csv_writer_neutralises_exactly_the_lead_characters_that_matter(self):
        for lead in ("=", "+", "-", "@", "\t", "\r"):
            self.assertEqual(_csv_safe_cell(lead + "1"), "'" + lead + "1")
        for safe in ("1", "a=b", " =1", "'=1", "", None):
            self.assertEqual(_csv_safe_cell(safe), "" if safe is None else safe)

    def test_null_bytes_and_crlf_inside_fields_do_not_break_parsing(self):
        rows = [[ADDRS[0], "exch\x00ange"], [ADDRS[1], "mixer\r\nmixer"], [ADDRS[2], "ransomware"]]
        r = clean(self, post("/api/analysis", csv_bytes(["address", "label"], rows)))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["meta"]["n_claims"], 3)

    def test_sql_looking_values_are_data(self):
        r = self._upload(["'; DROP TABLE x; --"] * 3 + ["exchange"] * 9)
        aid = r.json()["analysis_id"]
        self.assertEqual(client.get("/api/analysis").status_code, 200)              # nothing was dropped
        self.assertGreater(client.get(f"/api/analysis/{aid}/claims").json()["total"], 0)

    def test_a_search_query_full_of_metacharacters_is_a_plain_substring(self):
        aid = self._upload(["exchange"] * 12).json()["analysis_id"]
        for q in ("'; DROP TABLE x;--", "<script>", "%", "_", ".*", "\\", "a" * 5_000):
            r = client.get(f"/api/analysis/{aid}/claims", params=dict(q=q))
            self.assertIn(r.status_code, (200, 400, 414, 422), q[:20])
            self.assertNotIn("Traceback", r.text)


class TestNothingIsPromotedByCsvContent(unittest.TestCase):
    def test_a_file_calling_itself_verified_gains_no_evidence_tier_or_provenance(self):
        header = ["address", "label", "source", "confidence", "verified", "evidence", "heuristic", "root", "prov_verified"]
        rows = [[a, "exchange", "OFAC SDN", "1.0", "true", "court order", "manual_verified", "ofac_sdn", "true"] for a in ADDRS]
        aid = post("/api/analysis", csv_bytes(header, rows)).json()["analysis_id"]
        claims = client.get(f"/api/analysis/{aid}/claims", params=dict(limit=500)).json()["claims"]
        self.assertEqual({c["evidence_tier"] for c in claims} & {"verified", "derived"}, set())
        self.assertEqual({c["provenance"] for c in claims}, {"unresolved"})
        self.assertNotEqual({c["root"] for c in claims}, {"ofac_sdn"})

    def test_a_source_id_naming_a_bundled_source_is_refused_not_honoured(self):
        body = csv_bytes(["address", "label"], [[a, "exchange"] for a in ADDRS])
        r = client.post("/api/analysis", files={"file": ("u.csv", body, "text/csv")},
                        data=dict(use_reference="false", source_id="ransomwhere"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("bundled THEMIS reference source", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
