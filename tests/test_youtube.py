import sqlite3
import pandas as pd
from campaign_engine import config, importer


def test_all_youtube_comments_stored_with_original_labels(built):
    src = pd.read_csv(config.YOUTUBE_CSV)
    conn = sqlite3.connect(built)
    n = conn.execute("SELECT COUNT(*) FROM comment WHERE external_id IS NOT NULL").fetchone()[0]
    assert n == len(src) == 2600
    got = dict(conn.execute("""SELECT s.sentiment_label, COUNT(*) FROM comment c JOIN sentiment s USING(sentiment_id)
                               WHERE c.external_id IS NOT NULL GROUP BY 1"""))
    assert got == src["sentiment"].value_counts().to_dict()
    assert conn.execute("SELECT COUNT(DISTINCT commenter_id) FROM comment WHERE external_id IS NOT NULL").fetchone()[0] == src["author"].nunique()
    assert abs(conn.execute("SELECT SUM(like_count) FROM comment WHERE external_id IS NOT NULL").fetchone()[0] - src["like_count"].sum()) == 0


def test_youtube_is_observed_and_excluded_from_analysis(built):
    conn = sqlite3.connect(built)
    assert conn.execute("SELECT provenance, include_in_analysis FROM data_source WHERE source_name LIKE 'YouTube%'").fetchone() == ("observed", 0)
    assert conn.execute("SELECT COUNT(*) FROM comment WHERE external_id IS NOT NULL AND segment_id IS NOT NULL").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM post_anomaly WHERE post_id LIKE 'YT-%'").fetchone()[0] == 0


def test_reimport_is_idempotent(built):
    from campaign_engine import database as db
    conn = db.connect(built)
    assert importer.import_youtube(config.YOUTUBE_CSV, conn=conn)["comments_added"] == 0
    assert conn.execute("SELECT COUNT(*) FROM comment WHERE external_id IS NOT NULL").fetchone()[0] == 2600
    conn.close()
