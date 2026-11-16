import sqlite3
from campaign_engine import database as db

def test_foreign_keys_hold(built):
    conn = sqlite3.connect(built)
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"

def test_lookup_values_unique_and_no_derived_columns(built):
    conn = sqlite3.connect(built)
    cols = {r[1] for t in ("post", "comment", "account") for r in conn.execute(f"PRAGMA table_info({t})")}
    assert not cols & {"engagement_rate", "brand_name", "platform_name", "topic_name", "sentiment_label"}   # 3NF: no derived / duplicated names
    for t, c in [("brand", "brand_name"), ("topic", "topic_name"), ("campaign", "campaign_name")]:
        n, d = conn.execute(f"SELECT COUNT({c}), COUNT(DISTINCT {c}) FROM {t}").fetchone()
        assert n == d

def test_every_comment_classified_and_segmented(built):
    conn = sqlite3.connect(built)
    # every comment from an analysed source gets a segment; the YouTube source is deliberately excluded
    assert conn.execute("""SELECT COUNT(*) FROM comment c JOIN post p USING(post_id) JOIN data_source d USING(source_id)
                           WHERE d.include_in_analysis = 1 AND c.segment_id IS NULL""").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM segment").fetchone()[0] >= 6
    assert conn.execute("SELECT COUNT(*) FROM recommendation").fetchone()[0] >= 8

def test_provenance_marked(built):
    conn = sqlite3.connect(built)
    assert {r[0] for r in conn.execute("SELECT DISTINCT provenance FROM data_source")} == {"simulated", "observed"}

def test_frames_derive_metrics(built):
    posts, comments = db.frames(built)
    fashion = posts[posts["include_in_analysis"] == 1]
    assert fashion["engagement_rate"].notna().all() and len(comments) > 1000
    assert posts.loc[posts["platform"] == "YouTube", "engagement_rate"].isna().all()   # no followers/likes -> no rate
    assert abs(fashion["er_index"].median() - 1) < 0.2
