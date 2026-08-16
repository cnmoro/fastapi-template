# AGENTS.md

## Minimalism

The template ships the smallest thing that runs a real API: auth, RBAC, Mongo,
caching, a Dockerfile. Nothing speculative. If a feature is not used by an
endpoint that exists today, it does not belong here yet.

## Low complexity

Prefer a longer function over a deeper call chain. A reader should follow a
request from router to service to database without opening a fourth file.
Configuration is environment variables read once at module import, not a
settings framework.

## Abstractions

Keep them at the absolute minimum. Write plain functions that take arguments
and return values, C-like: no classes, no base classes, no dependency
injection containers, no repository or service-layer wrappers. Introduce an
abstraction only when it is critically necessary, meaning the code cannot work
without it, not when it would look tidier. Pydantic models are the one blessed
exception, because FastAPI needs them for validation and OpenAPI.

## Structure

Three folders, split by semantics rather than by layer ceremony.
`basemodels/` holds pydantic schemas grouped by scope (one file per domain,
e.g. `authentication.py`). `routers/` holds HTTP concerns only: paths,
status codes, dependencies, turning exceptions into responses. `services/`
holds everything else, one module per subject (`db`, `http`, `authentication`,
`rbac`, `util`, `example`). That is all. Do not add a folder without deleting
one.

## Async and sync

Route handlers and anything touching the network are `async def`, because the
work is I/O bound and the event loop should be free while it waits. Pure
computation stays a normal `def` and is called directly. The rule that matters:
never do blocking work inside `async def`. CPU-bound work goes through
`anyio.to_thread.run_sync`, as password hashing does in
`services/authentication.py`, otherwise one request stalls every other request
on that worker.

## Free-threaded Python

The Docker image runs `3.14t`, the free-threaded (no-GIL) build. It costs
roughly 14% throughput per request and buys real in-process thread
parallelism. You do not need it to scale plain I/O: each uvicorn worker is a
separate process with its own event loop. Reach for it when threads must share
memory and burn CPU at the same time, such as a large in-process model or a
parallel data transform. The tax: a dependency without a `cp314t` wheel cannot
be installed at all (this is why the template uses stdlib `json`, not orjson).
Not needed? Change `3.14t` to `3.14` in the Dockerfile.

## Async MongoDB

`services/db.py` keeps one lazily-created `AsyncMongoClient` per process. It is
created on first use rather than at import, because the client binds to the
running event loop, and one client means one connection pool shared by every
database, so `get_database("OTHER")` costs no extra connections. Every
operation is awaited: `await coll.find_one(...)`, `await coll.insert_one(...)`.
`find()` is the exception, returning a cursor that is not awaited but iterated
with `async for`, or drained with `await cursor.to_list(length=None)` when the
result set is known to be small. Never construct a client per request, and
close it on shutdown.

## Mindset

Be lazy, where lazy means efficient rather than careless: the best code is the
code never written. Before writing anything, stop at the first of these that
holds, in order: it does not need to exist at all (say so), this codebase
already has it, the stdlib does it, the platform does it (a database constraint
beats application code), an installed dependency does it, it fits on one line,
and only then the minimum code that works. That shortens the solution, never
the reading, so trace the real flow first and fix bugs at the root by checking
every caller rather than patching the one path that was reported. No interface
with a single implementation, no factory for one product, no config for a value
that never changes, no scaffolding for later; prefer deletion over addition and
boring over clever. Never trade away input validation, error handling that
prevents data loss, security, or anything explicitly asked for. Laziness stops
at tests, see below. Mark a deliberate corner-cut with
a comment naming its ceiling and upgrade path, as `services/util.py` and
`services/rbac.py` do. If an explanation runs longer than the code it defends,
delete the explanation.

## Tests

Everything produced ships with unit tests covering at least 90% of the new
code, measured rather than estimated, and at least one end-to-end test that
drives the feature through its real entry point: an HTTP request against a
running app, not a direct call to the function. When the instrumentation needed
to test something does not exist yet, building it is part of the task, whether
that is Playwright for a UI, a load harness for a throughput claim, or a
container for a datastore. A missing tool is a reason to add it, never a reason
to skip the test. Tests live in `tests/`, mirroring the module they cover; that
folder is the one exception to the three-folder rule above.

Mocked data proves nothing, so tests run against the real thing: a real MongoDB
in a container, real tokens, real hashing, with randomly generated values that
resemble production traffic instead of three hand-picked happy-path rows.
External dependencies are included rather than stubbed out. When one needs a
credential or is otherwise awkward to provision, an API key or a paid endpoint,
still wire it for real and add the harness and the instructions to run it,
arranged so the suite executes those tests when the credential is present and
skips them loudly when it is not.
