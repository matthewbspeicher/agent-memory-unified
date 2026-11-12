# Order terms module and Paper ledger ownership

**Status:** design agreed 2026-11-11, not started.
**Implementer:** Claude, coordinating with Codex. **Reviewer:** an independent read-only review per pull request.
**Vocabulary:** see `CONTEXT.md` for *Order terms*, *Paper ledger* and *Account generation*. Paths below are relative to `trading/`.

## Goal

Two behaviour-preserving refactors in the order execution and paper cluster:

1. **Order terms.** Move the order codec and structural validation out of `execution/service.py` into a module that storage, broker and execution can all import downward. This removes an import cycle that nine call sites currently dodge with lazy imports.
2. **Paper ledger.** Make `storage/paper.py` the only production module containing SQL against the nine ledger tables. Today 31 such statements live in nine other files, and the Account generation lookup is copied in 11 places.

Nothing a caller or an operator can observe changes. The single known exception is listed under "Known non-identical detail".

## Line numbers in this document

The call-site inventory was produced by a read-only sub-agent on 2026-11-11 against `main` at `6d08440`. I did not re-read every cited line. Treat line numbers as starting points and confirm each against the file.

## Decisions

| # | Decision |
|---|---|
| 1 | Claude implements, coordinating with Codex; each pull request gets an independent review before merge |
| 2 | The module is `broker/order_terms.py`, beside `broker/models.py` |
| 3 | It holds the codec and structural validation. The quote-freshness rule (`age < -5 or age > 30`) becomes one function beside `Quote`, not part of Order terms |
| 4 | Validation raises `InvalidOrderTerms`, defined in the new module. `ExecutionService` translates it to `ExecutionRejected` at its own interface |
| 5 | `PaperStore.transaction()` keeps yielding the handle. Only non-ledger stores may use it, to join the ledger's transaction. All SQL on ledger tables moves into named ledger operations |
| 6 | The ledger tables are: `paper_accounts`, `paper_positions`, `paper_orders`, `paper_order_terms`, `paper_fill_events`, `paper_risk_events`, `paper_risk_coverage`, `paper_dispatches`, `paper_match_ticks`. The work-queue tables (`paper_fill_jobs`, `paper_entry_exit_handoffs`, `paper_auto_ticks`) stay with the reconciler and the driver |
| 7 | No column type changes. REAL versus Decimal is a schema change and is out of scope |
| 8 | Strictly behaviour-preserving. The string-matched rest-or-reject decision and the raise-versus-reject contract stay exactly as they are |
| 9 | Public names: `encode_order`, `decode_order`, `validate_order_terms`. Every importer is updated. No aliases remain in `execution/service.py` |
| 10 | The first commit is a golden test pinning the stored payload string for each order type, written against the current code |
| 11 | `validate_order_terms` keeps normalising quantity and prices in place, and says so in its docstring |
| 12 | Tests may keep raw `paper_*` SQL only to fabricate legacy or corrupt ledger states. No test is rewritten unless the refactor breaks it |
| 13 | The last commit adds a test that fails if any production module other than `storage/paper.py` contains SQL naming a ledger table, modelled on the AST test in `tests/unit/test_execution_callers_integration.py` |
| 14 | `CONTEXT.md` gains *Order terms*, *Paper ledger*, *Account generation* (done). New code says "generation", not "epoch" |
| 15 | Extracting the shared transaction machinery is a follow-up, not part of this work |
| 16 | The operation set below is adopted |
| 17 | Order terms provides the one function that produces the stored payload string (sorted keys, `default=str`), used by the three SQL sites |
| 18 | Delete `api/container.py` and its `.coveragerc` entry. Leave `SimulatedBroker`; switch its reset to the ledger operation |
| 19 | Replace the raw `PAPER` account insert in `api/startup/brokers.py` with `ensure_account`. Do not fix the ignored initial balance here |
| 20 | Paper order managers expose a public read-only `store`. Remove reach-throughs via `_store` and the two `_get_db()` calls outside the store |
| 21 | Two pull requests, in the slice order below |
| 22 | Verification gate as below |

## Order terms module

**Moves from `execution/service.py`:** `_encode`, `_decode`, `ExecutionService._validate_order`.

**New in the module:** the payload-string function (decision 17) and `InvalidOrderTerms`.

**Importers to update** (lazy imports that exist only to dodge the cycle):
- `storage/paper.py:545`, `:595`, `:662`
- `broker/paper_dispatch.py:25`, `:75`, `:121`
- `broker/paper_matching.py:31`, `:88`, including the unbound call `ExecutionService._validate_order(None, account_id, order)` at `:34` and `:103`
- `execution/fill_reconciliation.py:21`
- every use inside `execution/service.py`

**Payload string.** These three sites must produce identical bytes, because `_match_dispatch` (`broker/paper_dispatch.py:208`) compares the stored string to a fresh one:
- `storage/paper.py:587` (`paper_order_terms.order_payload`)
- `broker/paper_dispatch.py:27`, `:104`, `:126` (`paper_dispatches.order_payload`)
- `execution/fill_reconciliation.py:288` (embedded in `paper_fill_jobs.payload`)

The Redis attempt and journal (`execution/service.py`) dump larger documents with `default=str` only. Leave their dump options alone; they are compared as raw strings read back from Redis, never re-encoded.

**Quote freshness.** One function beside `Quote` replaces the copies in `execution/service.py`, `broker/paper.py`, `broker/paper_matching.py` and `storage/paper.py`. Confirm each copy treats naive timestamps the same way before merging them; if they differ, keep the differences and report them, since unifying them would change behaviour.

## Paper ledger operations

| Operation | Replaces | Already on `PaperStore`? |
|---|---|---|
| Account generation for an account, returning the value or none | `paper_matching.py:228`; `paper_dispatch.py:192`; `paper_driver.py:99`, `:151`; `fill_reconciliation.py:95`, `:106`, `:141`, `:220`, `:330`, `:470`; `storage/pnl.py:319` | No. The same select is inlined at `storage/paper.py:550` |
| Open order ids for an account | `paper_matching.py:153`, `:169`; `paper_driver.py:108` | No |
| Open orders in arrival order, with trigger flag | `paper_matching.py:254` | No |
| Set stop triggered on or off | `paper_matching.py:74`, `:124`, `:287` | No |
| Fill evidence for an order (quantity, price, commission) | `paper_matching.py:305` | No. `get_order_result` reads only commission and time |
| Tick record: get, save | `paper_matching.py:239`, `:338` | Yes: `get_match_tick`, `save_match_tick`, currently test-only |
| Dispatch record: get | `paper_dispatch.py:184` | No |
| Dispatch record: insert | `paper_dispatch.py:63`, `:107`, `:139` | No |
| Dispatch receipts for an account, optionally by generation | `fill_reconciliation.py:354`, `:388` | No |
| Order terms for an account | `fill_reconciliation.py:340` | No |
| Debit cash | `broker/paper.py:175` | No |
| Reset account | `broker/paper.py:446`, `:451`; `adapters/paper/broker.py:336`, `:341` | No |
| Seed account | `api/startup/brokers.py:47` | Yes: `ensure_account` |

**Rules for these operations**
- **Callers keep their own error handling.** The generation lookup returns a value or none. Each of the 11 callers currently raises a different message or returns early; keep that at the call site.
- **Dispatch insert takes all seven columns explicitly.** The submit path today omits `operation` and `original_order_id` and relies on column defaults (`'submit'`, null). Pass those same values.
- **Reset keeps its current extent.** It clears six tables and re-seeds the account and coverage. It does not clear `paper_dispatches` or `paper_match_ticks`, deliberately.
- **Dialect knowledge stays inside the store.** `INSERT OR REPLACE` in the two `reset()` methods moves with them.

**Reaching the store (decision 20).** Remove:
- `broker/paper_matching.py:72` (`self._store._get_db()`)
- `api/startup/brokers.py:33`, `:55`
- `execution/paper_driver.py:62` (`manager._store is paper_store`)
- `execution/fill_reconciliation.py:57` (`broker.orders._store`)

`execution/paper_driver.py:118` calls `manager._snapshot(...)`, a private on the matching mixin. Give it a public name in the same change.

Leave the inherited privates used inside `TrackedPositionStore` (`storage/pnl.py`) and `storage/exit_rules.py:55`. They belong to the follow-up.

### Known non-identical detail

`save_match_tick` dumps with sorted keys; the inline code at `paper_matching.py:338` does not. After the change, newly stored tick rows differ in key order from old ones. Every reader parses the JSON and compares fields, so nothing observes this. If the reviewer finds any reader comparing raw tick payload strings, stop and keep the unsorted form.

## Slices

**Pull request 1: Order terms**
1. Golden test pinning the payload string for market, limit, stop, stop-limit and trailing-stop orders, against current code.
2. `broker/order_terms.py` with codec, validation, payload string and `InvalidOrderTerms`; `ExecutionService` translates the error.
3. Importers updated; lazy imports removed; no aliases left.
4. Quote-freshness function beside `Quote`; copies replaced.

**Pull request 2: Paper ledger**
1. Generation, reset, seed and debit operations; callers switched.
2. Matching operations: open orders, trigger flag, fill evidence, tick record.
3. Dispatch record operations and the reconciler's reads.
4. Public `store` on paper order managers; reach-throughs removed.
5. Delete `api/container.py` and its `.coveragerc` entry.
6. Enforcement test.

Each commit leaves the suite green.

## Verification gate

- **Every commit:** the unit suite, `cd trading && python -m pytest tests/unit/ -v --tb=short --timeout=30`.
- **Pull request 1:** also the SQLite paper integration tests.
- **Pull request 2:** also the PostgreSQL and real-Redis integration suites, in disposable containers as on 2026-11-11, before merge.
- No production database, live broker or deployment is involved.

## Out of scope, recorded as follow-ups

- **Transaction machinery extraction (done as a third pull request).** `TrackedPositionStore` subclassed `PaperStore`, and `storage/exit_rules.py` constructed one, only to borrow its transaction. The machinery now lives in `storage/unit_of_work.py`; each store holds a `UnitOfWork`, and the tracked-position store reads the ledger through a `PaperStore` bound to its own unit of work.
- **Ignored paper initial balance.** `init_tables` seeds `PAPER` at 100,000 before startup tries to insert the configured `paper_trading_initial_balance`, so the configured value is ignored on a fresh database. Needs a decision, since fixing it changes what a new paper account starts with.
- **Rest-or-reject by message text.** `broker/paper_matching.py` decides an order should rest by matching the text of a rejection message. Becomes a small change once Order terms exists.
- **Typed order outcome.** Definite rejection versus unknown outcome is a convention re-derived in several callers.
- **Approved Opportunities never execute.** `OpportunityStatus.APPROVED` is written by the approval routes and WhatsApp and read by nothing that executes.
- **`SpreadTracker` has no notifier.** It is constructed with `notifier=None` and a comment promising later wiring that does not exist.
- **REAL versus Decimal columns** in the ledger tables.

The wider review these came from is not in the repository; ask for it if needed.
