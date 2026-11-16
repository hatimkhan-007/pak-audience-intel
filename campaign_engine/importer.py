"""Import real (observed) posts + comments from CSV and refresh the analysis.

posts.csv    : post_id, brand, platform, campaign, content_type, product_category, likes,
               comments_count, days_since_post  [+ shares, views, followers]
comments.csv : post_id, comment_text           [+ language_type, topic, sentiment, purchase_intent]
Existing post_ids are skipped so the command is safe to re-run.
"""
from __future__ import annotations
import pandas as pd
from . import config, database as db, pipeline

REQUIRED_POSTS = ["post_id", "brand", "platform", "campaign", "content_type", "product_category", "likes", "comments_count", "days_since_post"]


def import_csv(posts_csv, comments_csv, source_name, source_url=None, collected_on=config.COLLECTION_DATE, permission=None):
    posts = pd.read_csv(posts_csv, thousands=",")
    comments = pd.read_csv(comments_csv)
    missing = [c for c in REQUIRED_POSTS if c not in posts.columns]
    if missing: raise SystemExit(f"posts CSV is missing columns: {missing}")
    if not {"post_id", "comment_text"} <= set(comments.columns): raise SystemExit("comments CSV needs post_id and comment_text")
    for c in ("shares", "views", "followers"):
        if c not in posts.columns: posts[c] = None
    conn = db.connect(); db.init_schema(conn) if not config.DB_PATH.exists() else None
    pipeline.seed_lookups(conn)
    have = {r[0] for r in conn.execute("SELECT post_id FROM post")}
    posts = posts[~posts["post_id"].isin(have)].drop_duplicates("post_id")
    comments = comments[comments["post_id"].isin(posts["post_id"]) & comments["comment_text"].notna()]
    cur = conn.execute("INSERT INTO data_source(source_name,provenance,source_url,collected_on,reuse_permission) VALUES (?,?,?,?,?) ON CONFLICT(source_name) DO UPDATE SET source_url=excluded.source_url RETURNING source_id",
                       (source_name, "observed", source_url, collected_on, permission))
    sid = cur.fetchone()[0]
    n_posts = pipeline.insert_posts(conn, posts, sid)
    an = pipeline.insert_comments(conn, comments)
    summary = pipeline.run_analysis(conn)
    conn.close()
    return dict(posts_added=n_posts, comments_added=len(an), **summary)


YOUTUBE_SOURCE = "YouTube comment sentiment analyzer export (Project 2)"


def import_youtube(csv_path=config.YOUTUBE_CSV, conn=None, source_name=YOUTUBE_SOURCE, collected_on=config.COLLECTION_DATE):
    """Load the YouTube Comment Sentiment Analyzer output (classified_comments.csv) as REAL data.

    One YouTube video becomes one row in `post` (platform = YouTube); every comment becomes a row in `comment`
    with the analyzer's own sentiment label / score / confidence, like and reply counts and timestamp.
    The source is flagged include_in_analysis = 0 so a non-fashion video cannot distort the lawn-suit clusters.
    Re-running is safe: comments whose YouTube id already exists are skipped."""
    own = conn is None
    conn = conn or db.connect()
    if own and not config.DB_PATH.exists(): raise SystemExit("Run `python manage.py setup` first.")
    pipeline.seed_lookups(conn)
    df = pd.read_csv(csv_path)
    need = {"comment_id", "video_id", "comment", "author", "published_at", "like_count", "reply_count", "sentiment", "sentiment_score", "confidence"}
    if need - set(df.columns): raise SystemExit(f"CSV is missing columns: {sorted(need - set(df.columns))}")
    df = df.drop_duplicates("comment_id")
    have = {r[0] for r in conn.execute("SELECT external_id FROM comment WHERE external_id IS NOT NULL")}
    df = df[~df["comment_id"].isin(have)]
    if df.empty:
        return dict(comments_added=0, video_id=None)

    row = conn.execute("SELECT source_id FROM data_source WHERE source_name=?", (source_name,)).fetchone()
    if row: sid = row[0]
    else:
        sid = conn.execute("INSERT INTO data_source(source_name,provenance,source_url,collected_on,reuse_permission,include_in_analysis) VALUES (?,?,?,?,?,0)",
                           (source_name, "observed", "https://www.youtube.com/watch?v=" + str(df["video_id"].iloc[0]), collected_on,
                            "Public YouTube comments collected with the YouTube Data API; respect YouTube's terms before sharing")).lastrowid
    posts = []
    for vid, g in df.groupby("video_id"):
        posts.append(dict(post_id=f"YT-{vid}", brand="Gillette", platform="YouTube", campaign="Gillette ad (YouTube)", content_type="Video ad",
                          product_category="Advertisement (non-fashion)", likes=None, comments_count=len(g), shares=None, views=None, days_since_post=None, followers=None))
    existing = {r[0] for r in conn.execute("SELECT post_id FROM post")}
    new_posts = pd.DataFrame([p for p in posts if p["post_id"] not in existing])
    if len(new_posts): pipeline.insert_posts(conn, new_posts, sid)
    comments = pd.DataFrame(dict(post_id="YT-" + df["video_id"], comment_text=df["comment"].astype(str), external_id=df["comment_id"],
                                 commenter=df["author"], published_at=df["published_at"], like_count=df["like_count"], reply_count=df["reply_count"],
                                 sentiment=df["sentiment"], sentiment_score=df["sentiment_score"], sentiment_confidence=df["confidence"]))
    an = pipeline.insert_comments(conn, comments)
    # keep the platform-reported comment total consistent with what is stored
    conn.execute("UPDATE post SET comments_count = (SELECT COUNT(*) FROM comment c WHERE c.post_id = post.post_id) WHERE post_id LIKE 'YT-%'")
    conn.commit()
    if own: conn.close()
    return dict(comments_added=len(an), video_id=str(df["video_id"].iloc[0]), posts_added=len(new_posts))
