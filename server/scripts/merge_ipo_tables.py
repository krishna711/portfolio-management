import argparse
import sqlite3
from pathlib import Path


TABLES_SIMPLE = {
    # table: conflict key columns
    "ipo": ["symbol"],
    "ipoquote": ["symbol"],
    "ipodailymetrics": ["symbol", "for_date"],
}


def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def get_table_sql(conn: sqlite3.Connection, name: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    if not row:
        return None
    return row[0]


def table_info(conn: sqlite3.Connection, name: str) -> list[tuple]:
    return conn.execute(f"PRAGMA table_info({name})").fetchall()


def table_columns(conn: sqlite3.Connection, name: str) -> dict[str, str]:
    # name -> declared type
    return {r[1]: (r[2] or "") for r in table_info(conn, name)}


def ensure_table(dst: sqlite3.Connection, src: sqlite3.Connection, name: str) -> None:
    if table_exists(dst, name):
        return
    sql = get_table_sql(src, name)
    if not sql:
        raise RuntimeError(f"Source DB missing table {name}")
    dst.execute(sql)


def ensure_columns(dst: sqlite3.Connection, src: sqlite3.Connection, name: str) -> None:
    src_cols = table_columns(src, name)
    dst_cols = table_columns(dst, name)
    for col, typ in src_cols.items():
        if col in dst_cols:
            continue
        decl = f"{col} {typ}".strip()
        dst.execute(f"ALTER TABLE {name} ADD COLUMN {decl}")


def upsert_table(dst: sqlite3.Connection, src: sqlite3.Connection, name: str, key_cols: list[str]) -> tuple[int, int]:
    src_cols = table_columns(src, name)
    dst_cols = table_columns(dst, name)

    cols = [c for c in src_cols.keys() if c in dst_cols]
    # never copy integer PK id if present
    cols = [c for c in cols if c != "id"]

    if any(k not in cols for k in key_cols):
        raise RuntimeError(f"Table {name} missing key columns in shared set: {key_cols}")

    select_cols = ",".join(cols)
    rows = src.execute(f"SELECT {select_cols} FROM {name}").fetchall()

    insert_cols = ",".join(cols)
    placeholders = ",".join(["?"] * len(cols))
    non_keys = [c for c in cols if c not in key_cols]
    if non_keys:
        set_sql = ",".join([f"{c}=excluded.{c}" for c in non_keys])
        conflict = ",".join(key_cols)
        sql = (
            f"INSERT INTO {name} ({insert_cols}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO UPDATE SET {set_sql}"
        )
    else:
        conflict = ",".join(key_cols)
        sql = (
            f"INSERT INTO {name} ({insert_cols}) VALUES ({placeholders}) "
            f"ON CONFLICT({conflict}) DO NOTHING"
        )

    before = dst.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
    dst.executemany(sql, rows)
    dst.commit()
    after = dst.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]

    inserted = max(0, after - before)
    updated = len(rows) - inserted
    return inserted, updated


def merge_userprefs(dst: sqlite3.Connection, src: sqlite3.Connection) -> dict:
    # Only copy IPO tracker columns preference by email mapping
    if not table_exists(src, "userpreference"):
        return {"copied": 0, "skipped": 0}

    q = (
        "SELECT u.email, p.key, p.value, p.created_at, p.updated_at "
        "FROM userpreference p JOIN user u ON u.id=p.user_id "
        "WHERE p.key='ipo_tracker_columns'"
    )
    rows = src.execute(q).fetchall()

    copied = 0
    skipped = 0
    for email, key, value, created_at, updated_at in rows:
        urow = dst.execute("SELECT id FROM user WHERE email=?", (email,)).fetchone()
        if not urow:
            skipped += 1
            continue
        user_id = int(urow[0])

        sql = (
            "INSERT INTO userpreference (user_id, key, value, created_at, updated_at) "
            "VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at"
        )
        dst.execute(sql, (user_id, key, value, created_at, updated_at))
        copied += 1

    dst.commit()
    return {"copied": copied, "skipped": skipped}


def merge_usertags(dst: sqlite3.Connection, src: sqlite3.Connection) -> dict:
    # Copy IPO row colors by mapping (user.email, ipo.symbol) to destination IDs
    if not table_exists(src, "ipousertag"):
        return {"copied": 0, "skipped": 0}

    q = (
        "SELECT u.email, i.symbol, t.color, t.updated_at "
        "FROM ipousertag t "
        "JOIN user u ON u.id=t.user_id "
        "JOIN ipo i ON i.id=t.ipo_id"
    )
    rows = src.execute(q).fetchall()

    copied = 0
    skipped = 0

    for email, symbol, color, updated_at in rows:
        urow = dst.execute("SELECT id FROM user WHERE email=?", (email,)).fetchone()
        if not urow:
            skipped += 1
            continue
        user_id = int(urow[0])

        irow = dst.execute("SELECT id FROM ipo WHERE symbol=?", (symbol,)).fetchone()
        if not irow:
            skipped += 1
            continue
        ipo_id = int(irow[0])

        sql = (
            "INSERT INTO ipousertag (user_id, ipo_id, color, updated_at) "
            "VALUES (?,?,?,?) "
            "ON CONFLICT(user_id, ipo_id) DO UPDATE SET color=excluded.color, updated_at=excluded.updated_at"
        )
        dst.execute(sql, (user_id, ipo_id, color, updated_at))
        copied += 1

    dst.commit()
    return {"copied": copied, "skipped": skipped}


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge IPO tracker tables from src DB into dst DB")
    ap.add_argument("--src", required=True, help="Source SQLite DB (local w/ IPO tracker data)")
    ap.add_argument("--dst", required=True, help="Destination SQLite DB (live)")
    ap.add_argument("--with-userdata", action="store_true", help="Also merge user tags (colors) and IPO column preferences")
    args = ap.parse_args()

    src_path = Path(args.src)
    dst_path = Path(args.dst)
    if not src_path.exists():
        raise SystemExit(f"Missing src: {src_path}")
    if not dst_path.exists():
        raise SystemExit(f"Missing dst: {dst_path}")

    src = sqlite3.connect(str(src_path))
    dst = sqlite3.connect(str(dst_path))

    try:
        # Ensure core tables exist and columns align
        for t in TABLES_SIMPLE.keys():
            ensure_table(dst, src, t)
            ensure_columns(dst, src, t)

        # Also ensure optional tables if requested
        if args.with_userdata:
            for t in ("userpreference", "ipousertag"):
                ensure_table(dst, src, t)
                ensure_columns(dst, src, t)

        dst.commit()

        summary = {}
        for t, keys in TABLES_SIMPLE.items():
            ins, upd = upsert_table(dst, src, t, keys)
            summary[t] = {"inserted_approx": ins, "updated_approx": upd}

        if args.with_userdata:
            summary["userpreference"] = merge_userprefs(dst, src)
            summary["ipousertag"] = merge_usertags(dst, src)

        print("Merge complete")
        for k, v in summary.items():
            print(k, v)
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
