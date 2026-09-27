# Public-release scrub — 2026-09-27

Pre-publication scan of every tracked file for tokens/keys, absolute local paths,
email addresses, private IP ranges, and this machine's hostname, before the repo
is made public. No repository visibility, GitHub, or DNS setting was changed.

- Scanner: `probe/scrub.py` (pure, tested in `tests/test_scrub.py`).
- Driver: `scripts/scan_repo.py` — `git ls-files`, decompressing `.gz` in memory.
- Hostname scanned for: `MacBook-Air-Fadhlan.local`.
- Tracked files scanned: **964** (includes 878 gzipped raw bodies, decompressed).

## Repo size

- Total tracked size: **10,023,214 bytes (9.6 MB)**.
- 10 largest tracked files:

| bytes | file |
|---|---|
| 408841 | fixtures/graphql_introspection_2026-09-27.json |
| 376626 | fixtures/premise_2026-09-27_run2.jsonl.gz |
| 327846 | fixtures/premise_2026-09-27_run1.jsonl.gz |
| 50958 | fixtures/build_config_2026-09-27.rows.jsonl |
| 45305 | fixtures/ground_truth_2026-09-27.rows.jsonl |
| 28438 | fixtures/find_oldest_2026-09-27.rows.jsonl |
| 24976 | fixtures/discovery2_2026-09-27.rows.jsonl |
| 19818 | fixtures/raw/2026-09-27_run2/00042_publicnode.json.gz |
| 19818 | fixtures/raw/2026-09-27_run2/00013_publicnode.json.gz |
| 19818 | fixtures/raw/2026-09-27_run1/00042_publicnode.json.gz |

## Findings

### Fixture files: **0 hits**

No tokens, local paths, emails, private IPs, or the machine hostname were found in
ANY fixture — including all 878 decompressed gzipped raw response bodies and the
run JSONL. No fixture edit is needed and none was made (fixtures are dated
evidence). Nothing here requires a decision.

### Non-fixture files: 36 hits, ALL intentional — no real leak, nothing to fix

Every non-fixture hit is in the scanner itself or its test vectors. These are the
scanner's own pattern literals and deliberately-fake test data, not secrets. No
real credential, no real `/Users/…` path from this environment, no real email, no
real/private IP, and the machine hostname appears nowhere. Editing them would
break the scanner, so they are left as-is.

**`probe/scrub.py` (7 hits) — the scanner's pattern definitions and docstring:**

| line | category | match | why it is not a leak |
|---|---|---|---|
| 1 | token | `secret` | docstring: "…flagging likely secrets…" |
| 4 | token | `secret` | docstring: describes flagging the word "secret" |
| 22 | token | `secret` | the regex literal `(?i)secret` |
| 23 | token | `password` | the regex literal `(?i)password` |
| 26 | local_path | `/Users/` | the regex literal for detecting local paths |
| 27 | local_path | `/home/` | the regex literal |
| 28 | local_path | `/private/tmp` | the regex literal |

**`tests/test_scrub.py` (29 hits) — deliberately-fake test inputs:**

| line | category | match | why it is not a leak |
|---|---|---|---|
| 1 | token | `secret` | docstring |
| 11 | token | `ghp_ABCDEF1234567890`, `sk-abc123XYZ`, `gho_zzz999` | fake tokens asserted on |
| 16,19 | token | `api_key`, `secret`, `password` | test names / comment words |
| 17 | token | `Bearer abc.def`, `api_key`, `secret`, `password` | fake input string `hunter2` etc. |
| 23 | local_path | `/Users/`, `/home/`, `/private/tmp` | fake path input `/Users/fadhlan/x` (literal test string, not a real file) |
| 30,32 | email | `alice.b+tag@example.co.uk` | RFC 2606 example domain |
| 36,39–42 | private_ip | `10.0.0.5`, `192.168.1.1`, `172.16.9.9`, `127.0.0.1`, `169.254.1.1` | documentation/private ranges used to test the matcher; the public IP `93.184.216.34` in the same line is correctly NOT matched |
| 65 | token | `ghp_secrettoken0000` | fake token |

## Conclusion

**Clean for public release.** No real secrets, keys, local paths, emails, private
IPs, or the machine hostname are present in any tracked file. The only hits are
the scanner's own vocabulary and its test fixtures, which are expected and safe.
No fixture required a decision (0 fixture hits); no non-fixture file required a
fix (all 36 hits are intentional and not leaks).
