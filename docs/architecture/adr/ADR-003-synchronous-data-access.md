# ADR-003: Synchronous Data Access in the Backend

- **Status:** Accepted
- **Issue:** [#11 – Backend skeleton](https://github.com/jankrus/doctorholiday/issues/11); applies to [#12](https://github.com/jankrus/doctorholiday/issues/12)–[#22](https://github.com/jankrus/doctorholiday/issues/22)
- **Builds on:** [ADR-001](ADR-001-tech-stack.md) (FastAPI, SQLAlchemy 2, PostgreSQL 16)

## 1. Context
FastAPI supports both synchronous (`def`) and asynchronous (`async def`) endpoints, and SQLAlchemy 2 offers a synchronous and an asyncio API. The choice determines how every repository function, transaction, session dependency and test from #12 onwards is written. Changing it later means rewriting the whole data access layer, so it is fixed before #12 starts.

## 2. Considered Options
*   **Option A: Synchronous** – SQLAlchemy `Engine`/`Session` with psycopg 3, endpoints that touch the database are `def`.
    *   *Pros:* Simple and well documented. FastAPI runs `def` endpoints in a thread pool (40 threads by default), so a slow query blocks one thread, not the server. Row locks (`SELECT … FOR UPDATE` for the admin bootstrap, BR-04) and transactions read like ordinary code. Tests need no async plugin.
    *   *Cons:* Concurrency is limited by the thread pool, which is far above the load of a single practice.
*   **Option B: Asynchronous** – SQLAlchemy asyncio extension with psycopg 3 async, endpoints are `async def`.
    *   *Pros:* Higher concurrency per process for I/O-bound workloads.
    *   *Cons:* One blocking call inside `async def` (e.g. Argon2id hashing, which is CPU-bound and must run in a thread anyway) stalls the whole event loop. Lazy loading raises errors and needs explicit eager loading. Tests need `pytest-asyncio`. More ways for a team to get it subtly wrong, with no benefit at our load.

## 3. Decision Outcome
We use **synchronous** data access: SQLAlchemy 2 `Engine`/`Session` with the psycopg 3 driver (`postgresql+psycopg://`).

- Endpoints that use the database or other blocking code (Argon2id, TOTP) are plain `def` functions.
- `async def` is used only for code that never blocks, e.g. pure ASGI middleware.
- The engine is created once per process in `create_app()` (`backend/src/doctorholiday/db.py`) and disposed on shutdown.

## 4. Consequences
*   **Security (Pros):** Fewer concurrency pitfalls in security-critical code paths (bootstrap, booking, session handling). Transactions and locks are explicit and easy to review.
*   **Operations (Cons):** Throughput per pod is bounded by the thread pool and the DB connection pool (SQLAlchemy default: 5 + 10 overflow). If that ever becomes a limit, scale horizontally (more replicas) before switching the model.
