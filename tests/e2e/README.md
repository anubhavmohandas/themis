# Browser workflows (optional, not run by pytest)

Real-browser checks of the flows a person uses: CSV upload -> pre-flight -> analysis -> overview -> claims ->
address -> provenance -> export; healthy / corrupt / recovered SQLite; the dependent-source demo; hostile
values rendered as text; and a foreign origin being refused. Needs `playwright-core` and a Chromium
(`CHROMIUM_PATH`), neither of which is a dependency of THEMIS.

```
E2E=/tmp/themis-e2e
python tests/e2e/make_fixtures.py $E2E
THEMIS_DB_DIR=$E2E/dbdir python -m themis.api &            # :5001
(cd frontend && npm run build && npx vite preview --port 4173 --host 127.0.0.1) &
mkdir -p $E2E/foreign && echo '<html></html>' > $E2E/foreign/index.html
python -m http.server 4999 --bind 127.0.0.1 --directory $E2E/foreign &   # any static page: the "foreign origin"
npm i --prefix $E2E playwright-core && cp tests/e2e/e2e.mjs $E2E/ && (cd $E2E && SP=$E2E node e2e.mjs)
```

Results go to `$E2E/e2e-results.json`. Last run: 16/16 (see THEMIS_RELEASE_READINESS_REPORT.md).
