from fastmcp import FastMCP
import os
import aiosqlite  # Changed: sqlite3 → aiosqlite
import tempfile
# Use temporary directory which should be writable
TEMP_DIR = tempfile.gettempdir()
DB_PATH = os.path.join(TEMP_DIR, "decisiongate.db")

print(f"Database path: {DB_PATH}")

mcp = FastMCP("Decision-Gate")

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
                    is_archived   INTEGER NOT NULL DEFAULT 0,
                    is_pinned     INTEGER NOT NULL DEFAULT 0,
                    pinned_at     TEXT,
                    archived_at   TEXT,
                    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_decisions_user ON decisions (user_id, community_id, created_at DESC)")
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


@mcp.tool()
async def capture_decision(
    user_id: str,
    query: str,
    verdict: str,
    community_id: str | None = None,
    session_id: str | None = None,
    note: str | None = None,
):
    """Record a user decision from Claude Desktop.

    verdict must be one of: approved, rejected, pending.
    community_id, session_id, and note may be omitted.
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
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            cur = await c.execute(
                """
                INSERT INTO decisions (user_id, community_id, session_id, query, verdict, note)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    _text(community_id) or None,
                    _text(session_id) or None,
                    query,
                    verdict,
                    _text(note) or None,
                ),
            )
            decision_id = cur.lastrowid
            await c.commit()
            return {
                "status": "success",
                "id": decision_id,
                "verdict": verdict,
                "message": "Decision captured",
            }
    except Exception as e:
        if "readonly" in str(e).lower():
            return {"status": "error", "message": "Database is in read-only mode. Check file permissions."}
        return {"status": "error", "message": f"Database error: {str(e)}"}


@mcp.tool()
async def get_decisions(
    user_id: str,
    community_id: str | None = None,
    session_id: str | None = None,
):
    """Return stored decisions for a user.

    community_id and session_id narrow the result when provided.
    """
    user_id = _text(user_id)
    community_id = _text(community_id)
    session_id = _text(session_id)
    if not user_id:
        return {"status": "error", "message": "user_id is required"}
    filters = ["user_id = ?"]
    params: list[str] = [user_id]
    if community_id:
        filters.append("community_id = ?")
        params.append(community_id)
    if session_id:
        filters.append("session_id = ?")
        params.append(session_id)
    try:
        async with aiosqlite.connect(DB_PATH) as c:
            c.row_factory = aiosqlite.Row
            cur = await c.execute(
                f"""
                SELECT id, user_id, community_id, session_id, query, verdict, note,
                       is_archived, is_pinned, pinned_at, archived_at, created_at, updated_at
                FROM decisions
                WHERE {' AND '.join(filters)}
                ORDER BY created_at DESC, id DESC
                """,
                params,
            )
            rows = await cur.fetchall()
            return {"status": "success", "decisions": [dict(row) for row in rows]}
    except Exception as e:
        return {"status": "error", "message": f"Database error: {str(e)}"}


# Start the server
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
    # mcp.run()