from __future__ import annotations
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
from . import config

SCHEMA = Path(__file__).with_name("schema.sql")


def connect(path=None, readonly=False) -> sqlite3.Connection:
    path = Path(path or config.DB_PATH)
    if readonly:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))


def get_or_create(conn, table, id_col, name_col, name, **extra) -> int:
    row = conn.execute(f"SELECT {id_col} FROM {table} WHERE {name_col}=?", (name,)).fetchone()
    if row:
        return row[0]
    cols = [name_col] + list(extra)
    cur = conn.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                       [name] + list(extra.values()))
    return cur.lastrowid


# ----------------------------------------------------------------- DataFrames
_cache: dict = {}


def _derive_posts(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["shares_f"] = df["shares"].fillna(0)
    df["interactions"] = df["likes"] + df["comments_count"] + df["shares_f"]      # NaN when likes unknown
    base = df["followers"].where(df["followers"].notna() & (df["followers"] > 0), df["views"])
    df["engagement_rate"] = np.where(base > 0, df["interactions"] / base * 100, np.nan)
    df["comment_rate"] = np.where(base > 0, df["comments_count"] / base * 100, np.nan)
    df["share_rate"] = np.where(base > 0, df["shares_f"] / base * 100, np.nan)
    df["like_rate"] = np.where(base > 0, df["likes"] / base * 100, np.nan)
    df["er_index"] = df["engagement_rate"] / df.groupby("platform")["engagement_rate"].transform("median")
    df["interactions_per_view"] = np.where(df["views"] > 0, df["interactions"] / df["views"] * 100, np.nan)
    return df


def frames(path=None):
    """(posts, comments) DataFrames, cached until the database file changes."""
    path = Path(path or config.DB_PATH)
    key = (str(path), path.stat().st_mtime_ns)
    if _cache.get("key") != key:
        conn = connect(path, readonly=True)
        posts = pd.read_sql_query("SELECT * FROM v_post_flat", conn)
        comments = pd.read_sql_query("SELECT * FROM v_comment_flat", conn)
        anomalies = pd.read_sql_query("SELECT * FROM post_anomaly", conn)
        conn.close()
        posts = _derive_posts(posts)
        posts = posts.merge(anomalies, on="post_id", how="left")
        comments = comments.merge(posts[["post_id", "brand", "platform", "campaign", "content_type"]],
                                  on="post_id", how="left")
        _cache.clear()
        _cache.update(key=key, posts=posts, comments=comments)
    return _cache["posts"], _cache["comments"]


def query(sql, params=(), path=None) -> list[dict]:
    conn = connect(path, readonly=True)
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    finally:
        conn.close()
