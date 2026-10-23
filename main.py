from datetime import datetime
from fastmcp import FastMCP
import os
import aiosqlite  # Changed: sqlite3 → aiosqlite
import tempfile
# Use temporary directory which should be writable
TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "decisiongate.db")

print(f"Database path: {DB_PATH}")

mcp = FastMCP("Decision-Gate")

_DEFAULT_PAGE = 50
_MAX_PAGE = 200

def init_db():  # Keep as sync for initialization
    try:
        # Use synchronous sqlite3 just for initialization
        import sqlite3
        with sqlite3.connect(DB_PATH) as c:
            c.execute("PRAGMA journal_mode=WAL")
            c.execute("""
                CREATE TABLE IF NOT EXISTS decisions (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id       TEXT NOT NULL,
                    community_id  TEXT,
                    session_id    TEXT,
                    query         TEXT NOT NULL,
                    verdict       TEXT NOT NULL CHECK (verdict IN ('approved', 'rejected', 'pending')),
                    note          TEXT,
                    supersedes_id INTEGER,
                    is_archived   INTEGER NOT NULL DEFAULT 0,
                    is_pinned     INTEGER NOT NULL DEFAULT 0,
                    pinned_at     TEXT,
                    archived_at   TEXT,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            columns = {row[1] for row in c.execute("PRAGMA table_info(decisions)")}
            if "supersedes_id" not in columns:
                c.execute("ALTER TABLE decisions ADD COLUMN supersedes_id INTEGER")
            c.execute("CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions (user_id, community_id, created_at DESC)")
            c.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS idx_decisions_supersedes
                ON decisions (supersedes_id)
                WHERE supersedes_id IS NOT NULL
                """
            )
            # Test write access
            c.execute("INSERT OR IGNORE INTO decisions(user_id, community_id, session_id, query, verdict, note) VALUES ('testuser', 'testcommunity', 'testsession', 'testquery', 'approved', 'testnote')")
            c.execute("DELETE FROM decisions WHERE query = 'testquery'")
            print("Database initialized successfully with write access")
    except Exception as e:
        print(f"Database initialization error: {e}")
        raise

# Initialize database synchronously at module load
init_db()

def _text(value: str | None) -> str:
    return (value or "").strip()


def _created_bound(value: str | None, *, end: bool) -> tuple[str | None, str | None]:
    """Normalize a date filter to YYYY-MM-DD HH:MM:SS. Returns (value, error)."""
    raw = _text(value).replace("T", " ").removesuffix("Z")
    if not raw:
        return None, None
    date_only = len(raw) == 10
    if date_only:
        pattern = "%Y-%m-%d"
    elif len(raw) == 16:
        raw += ":00"
        pattern = "%Y-%m-%d %H:%M:%S"
    else:
        pattern = "%Y-%m-%d %H:%M:%S"
    try:
        datetime.strptime(raw, pattern)
    except ValueError:
        return None, "dates must be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS"
    if date_only:
        raw = f"{raw} 23:59:59" if end else f"{raw} 00:00:00"
    return raw, None


@mcp.tool()
async def capture_decision(
    user_id: str,
    query: str,
    verdict: str,
    community_id: str | None = None,
    session_id: str | None = None,
    note: str | None = None,
    supersedes_id: int | None = None,
):
    """Record a user decision from Claude Desktop.

    verdict must be one of: approved, rejected, pending.
    community_id, session_id, note, and supersedes_id may be omitted.
    supersedes_id is an earlier decision by the same user that this one replaces.
    """
    user_id = _text(user_id)
    query = _text(query)
    verdict = _text(verdict).lower()
    if verdict not in ("approved", "rejected", "pending"):
        return {
            "status": "error",
            "message": "verdict must be approved, rejected, or pending",
        }
    if not user_id or not query:
        return {"status": "error", "message": "user_id and query are required"}
    if supersedes_id is not None and (
        isinstance(supersedes_id, bool) or not isinstance(supersedes_id, int) or supersedes_id < 1
    ):
        return {"status": "error", "message": "supersedes_id must be a positive integer"}
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            if supersedes_id is not None:
                prior = await c.execute(
                    "SELECT id FROM decisions WHERE id = ? AND user_id = ?",
                    (supersedes_id, user_id),
                )
                if await prior.fetchone() is None:
                    return {
                        "status": "error",
                        "message": "supersedes_id does not match a decision for this user",
                    }
                taken = await c.execute(
                    "SELECT id FROM decisions WHERE supersedes_id = ?",
                    (supersedes_id,),
                )
                if await taken.fetchone() is not None:
                    return {
                        "status": "error",
                        "message": "that decision has already been superseded",
                    }
            cur = await c.execute(
                """
                INSERT INTO decisions (
                    user_id, community_id, session_id, query, verdict, note, supersedes_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    _text(community_id) or None,
                    _text(session_id) or None,
                    query,
                    verdict,
                    _text(note) or None,
                    supersedes_id,
                ),
            )
            decision_id = cur.lastrowid
            await c.commit()
            return {
                "status": "success",
                "id": decision_id,
                "verdict": verdict,
                "supersedes_id": supersedes_id,
                "message": "Decision captured",
            }
    except Exception as e:
        message = str(e)
        if "readonly" in message.lower():
            return {"status": "error", "message": "Database is in read-only mode. Check file permissions."}
        if "UNIQUE constraint failed" in message and "supersedes_id" in message:
            return {"status": "error", "message": "that decision has already been superseded"}
        return {"status": "error", "message": f"Database error: {message}"}


@mcp.tool()
async def get_decisions(
    user_id: str,
    community_id: str | None = None,
    session_id: str | None = None,
    created_after: str | None = None,
    created_before: str | None = None,
    limit: int = _DEFAULT_PAGE,
    offset: int = 0,
):
    """Return stored decisions for a user, newest first.

    community_id and session_id narrow the result when provided.
    created_after and created_before are inclusive bounds (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
    A date with no time covers that whole day. limit defaults to 50 and cannot exceed 200.
    """
    user_id = _text(user_id)
    community_id = _text(community_id)
    session_id = _text(session_id)
    if not user_id:
        return {"status": "error", "message": "user_id is required"}
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= _MAX_PAGE:
        return {"status": "error", "message": f"limit must be an integer from 1 to {_MAX_PAGE}"}
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        return {"status": "error", "message": "offset must be an integer of 0 or greater"}
    created_after, date_error = _created_bound(created_after, end=False)
    if date_error:
        return {"status": "error", "message": date_error}
    created_before, date_error = _created_bound(created_before, end=True)
    if date_error:
        return {"status": "error", "message": date_error}
    if created_after and created_before and created_after > created_before:
        return {"status": "error", "message": "created_after must be on or before created_before"}
    filters = ["user_id = ?"]
    params: list[str | int] = [user_id]
    if community_id:
        filters.append("community_id = ?")
        params.append(community_id)
    if session_id:
        filters.append("session_id = ?")
        params.append(session_id)
    if created_after:
        filters.append("created_at >= ?")
        params.append(created_after)
    if created_before:
        filters.append("created_at <= ?")
        params.append(created_before)
    where = " AND ".join(filters)
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            count_cur = await c.execute(f"SELECT COUNT(*) FROM decisions WHERE {where}", params)
            total = (await count_cur.fetchone())[0]
            cur = await c.execute(
                f"""
                SELECT id, user_id, community_id, session_id, query, verdict, note, supersedes_id,
                       is_archived, is_pinned, pinned_at, archived_at, created_at, updated_at
                FROM decisions
                WHERE {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            )
            rows = await cur.fetchall()
            return {
                "status": "success",
                "decisions": [dict(row) for row in rows],
                "total": total,
                "limit": limit,
                "offset": offset,
            }
    except Exception as e:
        return {"status": "error", "message": f"Database error: {str(e)}"}


# Start the server
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
    # mcp.run()