# Cache busting a static site

**Read when the project first ships a web page** (GitHub Pages or any static
host), and before touching the build step that stamps asset URLs. The template
carries no rendering or deploy code; this is the pattern to add with it.

Earned twice: edmonton-tax-viz (`scripts/build_site.py`, RUNBOOK §3c) and
physics_sim (`tools/build-site.js`, ARCHITECTURE §6).

## The failure

GitHub Pages serves every file with `cache-control: max-age=600`, and phones
(Safari especially) have been seen holding files longer than that. Once CSS,
JS or data live in separate files, each has its **own cache lifetime**, so
right after a deploy a browser can run fresh HTML against a stale
`styles.css` or a stale `catalog.js`. The change looks half-shipped: "I can
see it in a private window but not in normal Safari", "the new sim isn't there".

**A private window showing the change while the normal one doesn't is a cache
result.** Ask for that first, before debugging anything device-specific.
Triage, cheapest first:

1. Did the deploy run at all? (A path filter can skip data-only changes.)
2. `curl -s <site>/<file> | grep <new thing>` — is it served? That separates
   "not deployed" from "not seen" in one command.
3. Private window on the affected device.
4. Only then look for a real bug.

## The fix: stamp asset URLs at deploy time

A build step copies the source tree to an output dir (`_site/`) and rewrites
each asset URL in the HTML to `file.ext?v=<content hash>`. The deploy uploads
the output dir; the source stays unstamped for local work.

- **Content hash, not the commit sha.** A sha changes every deploy and throws
  away the cache for files that didn't change. A content hash (8–10 hex of
  sha256) changes only when the file does, and needs no git at build time.
- **ES modules: `?v=` on the entry `<script>` isn't enough.** It doesn't reach
  the files that entry imports, or dynamic `import()`s. Write an **import map**
  into each page, before the first module script, mapping every `./x.js` to
  `./x.js?v=<hash>`.
- **Data files are assets too.** A `fetch('./data/x.json')` of a refreshed
  dataset has the same problem: new code with old data, or the reverse. Stamp
  data URLs as well, or fetch them with `{cache: 'no-cache'}` (revalidates each
  load; costs one round trip per file).
- **Fail loudly when the HTML drifts.** The stamper should throw when it finds
  no stylesheet link or no module script, or when a URL points at a file that
  doesn't exist. Otherwise a renamed file ships silently unstamped.

## The limit

The HTML page itself can't be stamped, since its URL is what the user types.
A browser holding a stale page keeps the old asset URLs (and the old import
map) until `max-age` runs out or they hard-refresh. Pages doesn't let you set
headers, so after a deploy that matters, tell the owner to hard-refresh.

## Guard it

- **A unit test**: every `.js`/`.css` in the output is referenced with its
  current content hash (physics_sim:
  `test_build_site_every_module_is_in_the_import_map_with_its_content_hash`).
- **A browser check on the built output** that fails on any unversioned
  `.js`/`.css` request (physics_sim: `npm run verify:built`). A unit test
  checks the HTML. This checks what the browser actually fetched, which is
  what catches a missed dynamic import.
- Run the browser check in the deploy workflow, before the artifact is
  uploaded. Then a red run leaves the last good site live.
