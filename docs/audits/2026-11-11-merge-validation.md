# Merge qualification follow-up

The two previously recorded baseline unit failures are fixed in test fixtures:

- Alpha Vantage sentiment composition now stubs the separate Fear & Greed fetch
  too, so a unit test does not depend on an unrelated external HTTP request.
  Assertions verify the blended score and both provider calls.
- The calibration-window test fixes its clock to the fixture's intended date and
  asserts exactly one recent trade rather than accepting any positive count.

No production behavior is changed by these follow-up fixes. Their 52 focused checks
pass. Broad sanitized unit qualification now passes 3,117 tests, with only the three
startup integration cases selected separately. The two native ML suites pass eight
and ten tests separately and 18 together with OMP_NUM_THREADS, OPENBLAS_NUM_THREADS
and MKL_NUM_THREADS set to one. This replaces the earlier local ML exclusion for
this qualification; it does not claim arbitrary native runtime configurations safe.

Together with the unchanged 232 real Redis/PostgreSQL/SQLite cases, three startup
cases and two arbitrage cases from the automatic-paper checkpoint, the disjoint
qualification is 3,372 passing tests with no remaining baseline failures. The GitHub
PR also runs its own frontend build and backend checks. Those remote results are
recorded on the pull request rather than inferred from these local receipts.

No live trading, deployment or user-database migration was performed. Unrelated
local lockfile changes, legacy API directory and scratch files remain excluded.

Local receipts: /Users/mspeicher/agent-memory-artifacts/merge-qualification-20261111/.
