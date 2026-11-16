#!/usr/bin/env python3
"""Generate docs/DATABASE_QUERIES.md.

Every SQL statement below is EXECUTED against a scratch copy of data/campaign.db while the document is built,
so the document only ever contains queries that actually run. INSERT / UPDATE / DELETE statements run inside
a transaction that is rolled back; the real database is never modified.

    python tools/build_query_docs.py
"""
import shutil, sqlite3, sys, tempfile, textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from campaign_engine import config

# --------------------------------------------------------------------------------------------------
# kind: "select" | "dml" (run together in one rolled-back transaction per entry) | "error" (must fail)
# --------------------------------------------------------------------------------------------------
S = []          # list of sections: (title, intro, [entries])


def section(title, intro=""):
    S.append((title, textwrap.dedent(intro).strip(), []))


def q(title, why, sql, kind="select", used_by=None):
    sql = [textwrap.dedent(x).strip() for x in sql] if isinstance(sql, list) else textwrap.dedent(sql).strip()
    S[-1][2].append(dict(title=title, why=why, sql=sql, kind=kind, used_by=used_by))


# ============================================================ 1. basic retrieval
section("3. Retrieving data (SELECT)", """
The front end only reads. These are the queries behind each page, written in plain SQL so they can be run in the
**SQL console** (`/database`) or any SQLite client. Joins go through the lookup tables because names are stored once (3NF).
""")
q("3.1  List the 20 most-engaging posts (with pagination)",
  "Reads the `v_post_flat` view (a ready-made join of `post`, `account`, `brand`, `platform`, `campaign`, `content_type`, `product_category`, `data_source`). `LIMIT/OFFSET` gives pagination: page *n* uses `OFFSET (n-1)*20`.",
  """
  SELECT post_id, brand, platform, content_type, campaign, likes, comments_count, shares, views,
         ROUND((likes + comments_count + COALESCE(shares,0)) * 100.0 / followers, 2) AS engagement_rate_pct
  FROM v_post_flat
  WHERE followers IS NOT NULL
  ORDER BY engagement_rate_pct DESC
  LIMIT 20 OFFSET 0;""", used_by="Posts page, Content page (top 10)")
q("3.2  Filter by platform, brand and campaign",
  "The three global filters (Platform / Brand / Campaign) become `WHERE` conditions.",
  """
  SELECT post_id, content_type, likes, comments_count
  FROM v_post_flat
  WHERE platform = 'Instagram' AND brand = 'Noor Lawn' AND campaign = '11.11 Sale'
  ORDER BY likes DESC;""", used_by="All filtered pages")
q("3.3  Search a post by id",
  "`LIKE` with `%` wildcards; the Posts page search box.",
  "SELECT post_id, brand, platform, content_type FROM v_post_flat WHERE post_id LIKE '%P004%' ORDER BY post_id;", used_by="Posts page")
q("3.4  The same result using the base tables (explicit joins)",
  "Shows how the normalised tables connect: `post → account → brand / platform`, and `post → campaign / content_type / product_category`.",
  """
  SELECT p.post_id, b.brand_name, pl.platform_name, c.campaign_name, ct.content_type_name, a.followers, p.likes
  FROM post p
  JOIN account a          ON a.account_id      = p.account_id
  JOIN brand b            ON b.brand_id        = a.brand_id
  JOIN platform pl        ON pl.platform_id    = a.platform_id
  JOIN campaign c         ON c.campaign_id     = p.campaign_id
  JOIN content_type ct    ON ct.content_type_id = p.content_type_id
  WHERE p.post_id = 'P0001';""")
q("3.5  One post with all of its comments",
  "Post detail page: a one-to-many join (`post` → `comment`).",
  """
  SELECT c.comment_id, c.comment_text, c.language_type, c.topic, c.sentiment
  FROM v_comment_flat c
  WHERE c.post_id = 'P0001'
  ORDER BY c.comment_id;""", used_by="Post detail page")

section("4. Question 1 – which content attracts attention?")
q("4.1  Engagement by content type",
  "Average engagement rate = interactions ÷ followers. (SQLite has no `MEDIAN`; the app computes medians in pandas, `AVG` is used here.) Posts younger than 3 days are excluded because their counts are still growing.",
  """
  SELECT content_type,
         COUNT(*)                                                                    AS posts,
         ROUND(AVG((likes + comments_count + COALESCE(shares,0)) * 100.0 / followers), 2) AS avg_engagement_pct,
         ROUND(AVG(likes))          AS avg_likes,
         ROUND(AVG(comments_count)) AS avg_comments,
         ROUND(AVG(shares))         AS avg_shares,
         ROUND(AVG(views))          AS avg_views
  FROM v_post_flat
  WHERE include_in_analysis = 1 AND days_since_post >= 3
  GROUP BY content_type
  ORDER BY avg_engagement_pct DESC;""", used_by="Content page")
q("4.2  Content type × platform matrix",
  "Pivot with conditional aggregation (`CASE` inside `AVG`).",
  """
  SELECT content_type,
         ROUND(AVG(CASE WHEN platform='Instagram' THEN (likes+comments_count+COALESCE(shares,0))*100.0/followers END),2) AS instagram,
         ROUND(AVG(CASE WHEN platform='TikTok'    THEN (likes+comments_count+COALESCE(shares,0))*100.0/followers END),2) AS tiktok,
         ROUND(AVG(CASE WHEN platform='Facebook'  THEN (likes+comments_count+COALESCE(shares,0))*100.0/followers END),2) AS facebook
  FROM v_post_flat
  WHERE include_in_analysis = 1 AND days_since_post >= 3
  GROUP BY content_type
  ORDER BY content_type;""", used_by="Content page heat-map")
q("4.3  Campaign and brand comparison",
  "Group by any dimension: swap `campaign` for `brand` or `platform`.",
  """
  SELECT campaign, COUNT(*) AS posts, ROUND(AVG(comments_count)) AS avg_comments, ROUND(AVG(likes)) AS avg_likes
  FROM v_post_flat
  WHERE include_in_analysis = 1
  GROUP BY campaign
  ORDER BY avg_comments DESC;""", used_by="Content page")
q("4.4  Rank formats inside each platform (window function)",
  "`RANK() OVER (PARTITION BY platform …)` gives the best format per platform without a self-join.",
  """
  SELECT platform, content_type, avg_er,
         RANK() OVER (PARTITION BY platform ORDER BY avg_er DESC) AS rank_in_platform
  FROM (SELECT platform, content_type,
               ROUND(AVG((likes+comments_count+COALESCE(shares,0))*100.0/followers),2) AS avg_er
        FROM v_post_flat WHERE include_in_analysis = 1 AND days_since_post >= 3
        GROUP BY platform, content_type)
  ORDER BY platform, rank_in_platform;""", used_by="Recommendations (best format per platform)")

section("5. Question 2 – what does the audience want?")
q("5.1  Topic distribution",
  "Counts and share of every topic (price, fabric, sizing, delivery, discount, availability, purchase intent…). The subquery in the denominator counts only analysed comments.",
  """
  SELECT t.topic_name AS topic, t.theme, COUNT(*) AS comments,
         ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM comment c2 JOIN post p2 USING(post_id)
                                   JOIN data_source d2 USING(source_id) WHERE d2.include_in_analysis = 1), 1) AS share_pct
  FROM comment c
  JOIN topic t USING(topic_id)
  JOIN post p USING(post_id)
  JOIN data_source d USING(source_id)
  WHERE d.include_in_analysis = 1
  GROUP BY t.topic_id
  ORDER BY comments DESC;""", used_by="Audience page, Dashboard")
q("5.2  Topics by platform",
  "Which platform asks about what.",
  """
  SELECT pl.platform_name AS platform, t.topic_name AS topic, COUNT(*) AS comments
  FROM comment c
  JOIN topic t   USING(topic_id)
  JOIN post p    USING(post_id)
  JOIN account a USING(account_id)
  JOIN platform pl USING(platform_id)
  JOIN data_source d ON d.source_id = p.source_id
  WHERE d.include_in_analysis = 1
  GROUP BY pl.platform_id, t.topic_id
  ORDER BY platform, comments DESC;""", used_by="Audience page (stacked chart)")
q("5.3  Sentiment inside each topic",
  "Share of negative comments per topic.",
  """
  SELECT t.topic_name AS topic,
         SUM(s.sentiment_label = 'Negative') AS negative,
         SUM(s.sentiment_label = 'Neutral')  AS neutral,
         SUM(s.sentiment_label = 'Positive') AS positive,
         ROUND(100.0 * SUM(s.sentiment_label = 'Negative') / COUNT(*), 1) AS negative_pct
  FROM comment c
  JOIN topic t USING(topic_id)
  JOIN sentiment s USING(sentiment_id)
  JOIN post p USING(post_id) JOIN data_source d USING(source_id)
  WHERE d.include_in_analysis = 1
  GROUP BY t.topic_id
  ORDER BY negative_pct DESC;""", used_by="Audience page")
q("5.4  Language mix and purchase intent",
  "Two lookups joined in one query.",
  """
  SELECT l.language_name AS language, i.intent_label AS intent, COUNT(*) AS comments
  FROM comment c
  JOIN language_type l   USING(language_id)
  JOIN purchase_intent i USING(intent_id)
  GROUP BY l.language_id, i.intent_id
  ORDER BY language, comments DESC;""", used_by="Audience page")
q("5.5  Search comments by keyword (English, Roman Urdu or Urdu)",
  "Substring search; the Comments page search box.",
  """
  SELECT comment_id, post_id, language_type, topic, sentiment, comment_text
  FROM v_comment_flat
  WHERE comment_text LIKE '%delivery%' OR comment_text LIKE '%ڈلیوری%'
  LIMIT 10;""", used_by="Comments page")
q("5.6  Ready-to-buy comments per brand",
  "Counts the leads a brand should answer first.",
  """
  SELECT b.brand_name, COUNT(*) AS ready_to_buy
  FROM comment c
  JOIN purchase_intent i USING(intent_id)
  JOIN post p USING(post_id) JOIN account a USING(account_id) JOIN brand b USING(brand_id)
  WHERE i.intent_label = 'Ready to buy'
  GROUP BY b.brand_id ORDER BY ready_to_buy DESC;""")
q("5.7  Cities mentioned in availability questions",
  "Uses `LIKE` per city and `UNION ALL`; the app does the same with a regular expression.",
  """
  SELECT 'Karachi' AS city, COUNT(*) AS mentions FROM comment WHERE comment_text LIKE '%karachi%'
  UNION ALL SELECT 'Lahore',    COUNT(*) FROM comment WHERE comment_text LIKE '%lahore%'
  UNION ALL SELECT 'Islamabad', COUNT(*) FROM comment WHERE comment_text LIKE '%islamabad%'
  ORDER BY mentions DESC;""", used_by="Audience page (cities)")

section("6. Question 3 – which marketing patterns are unusual?")
q("6.1  Flagged posts with the reason",
  "`post_anomaly` holds one row per flagged post (score, type and a plain-English reason written by the engine).",
  """
  SELECT a.post_id, v.brand, v.platform, v.content_type, a.anomaly_type, ROUND(a.anomaly_score, 3) AS score, a.reason
  FROM post_anomaly a
  JOIN v_post_flat v USING(post_id)
  ORDER BY a.anomaly_score DESC
  LIMIT 10;""", used_by="Anomalies page, Dashboard")
q("6.2  Count of flagged posts by type",
  "Drives the filter chips on the Anomalies page.",
  "SELECT anomaly_type, COUNT(*) AS posts, ROUND(AVG(anomaly_score), 3) AS avg_score FROM post_anomaly GROUP BY anomaly_type ORDER BY posts DESC;",
  used_by="Anomalies page")
q("6.3  Posts that beat their own brand's average (subquery)",
  "A hand-written \"outlier\" check, to compare with the machine-learning flags: posts whose engagement is more than 3× their brand + platform average.",
  """
  WITH er AS (
      SELECT post_id, brand, platform,
             (likes + comments_count + COALESCE(shares,0)) * 100.0 / followers AS er
      FROM v_post_flat WHERE include_in_analysis = 1 AND days_since_post >= 3),
  avg_er AS (SELECT brand, platform, AVG(er) AS mean_er FROM er GROUP BY brand, platform)
  SELECT er.post_id, er.brand, er.platform, ROUND(er.er, 2) AS er, ROUND(a.mean_er, 2) AS brand_platform_avg
  FROM er JOIN avg_er a USING (brand, platform)
  WHERE er.er > 3 * a.mean_er
  ORDER BY er.er DESC
  LIMIT 10;""")
q("6.4  Flagged posts that have no complaints (anti-join with NOT EXISTS)",
  "Finds viral / under-performing posts whose comments contain no delivery complaints.",
  """
  SELECT a.post_id, a.anomaly_type
  FROM post_anomaly a
  WHERE NOT EXISTS (SELECT 1 FROM comment c JOIN topic t USING(topic_id)
                    WHERE c.post_id = a.post_id AND t.topic_name = 'Delivery complaint')
  LIMIT 10;""")

section("7. Question 4 – audience segments (clusters)")
q("7.1  Segment sizes",
  "Each comment carries a nullable `segment_id`; comments from sources excluded from analysis (YouTube) have none.",
  """
  SELECT s.segment_id, s.segment_name, COUNT(*) AS comments,
         ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM comment WHERE segment_id IS NOT NULL), 1) AS share_pct
  FROM comment c
  JOIN segment s USING(segment_id)
  GROUP BY s.segment_id
  ORDER BY comments DESC;""", used_by="Segments page, Dashboard")
q("7.2  What each segment is made of",
  "Dominant topics inside each segment (window function picks the top topic per segment).",
  """
  SELECT segment_name, topic_name, n
  FROM (SELECT s.segment_name, t.topic_name, COUNT(*) AS n,
               ROW_NUMBER() OVER (PARTITION BY s.segment_id ORDER BY COUNT(*) DESC) AS rn
        FROM comment c JOIN segment s USING(segment_id) JOIN topic t USING(topic_id)
        GROUP BY s.segment_id, t.topic_id)
  WHERE rn = 1
  ORDER BY n DESC;""", used_by="Segments page (dominant need)")
q("7.3  Segment playbook",
  "The description and suggested action stored with each segment.",
  "SELECT segment_name, top_terms, suggested_action FROM segment ORDER BY segment_id LIMIT 5;", used_by="Segments page cards")
q("7.4  Sample comments of one segment",
  "Segments page examples and the \"browse this segment\" link.",
  """
  SELECT comment_text, language_type, sentiment
  FROM v_comment_flat
  WHERE segment = 'Price askers'
  LIMIT 5;""", used_by="Segments page, Comments page")
q("7.5  Which brand drives each segment",
  "Segment × brand cross-tab.",
  """
  SELECT s.segment_name, b.brand_name, COUNT(*) AS comments
  FROM comment c
  JOIN segment s USING(segment_id)
  JOIN post p USING(post_id) JOIN account a USING(account_id) JOIN brand b USING(brand_id)
  WHERE s.segment_name LIKE 'Delivery%'
  GROUP BY s.segment_id, b.brand_id
  ORDER BY s.segment_name, comments DESC;""")

section("8. Question 5 – recommendations")
q("8.1  Recommendations by priority",
  "Stored with their evidence, so the page and the CSV export are a plain `SELECT`.",
  """
  SELECT r.rec_id, r.priority, r.area, r.title, r.evidence, r.action, s.segment_name
  FROM recommendation r
  LEFT JOIN segment s USING(segment_id)
  ORDER BY CASE r.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, r.rec_id
  LIMIT 10;""", used_by="Recommendations page, Dashboard (High only)")
q("8.2  Count by area and priority",
  "",
  "SELECT area, priority, COUNT(*) AS recommendations FROM recommendation GROUP BY area, priority ORDER BY area, priority;")

section("9. Real data – YouTube comment sentiment",
        """
        The 2,600 comments from the YouTube Comment Sentiment Analyzer live in the same tables: the video is one
        `post` (`YT-UYaY2Kb_PKI`, platform *YouTube*), every comment is a `comment` row with `external_id` (YouTube comment id),
        `commenter_id`, `published_at`, `like_count`, `reply_count`, `sentiment_id`, `sentiment_score` and `sentiment_confidence`.
        The source row has `provenance = 'observed'` and `include_in_analysis = 0`.
        """)
q("9.1  Source and provenance",
  "Which data is real and which is simulated.",
  """
  SELECT ds.source_name, ds.provenance, ds.include_in_analysis, COUNT(DISTINCT p.post_id) AS posts, COUNT(c.comment_id) AS comments
  FROM data_source ds
  JOIN post p USING(source_id)
  LEFT JOIN comment c USING(post_id)
  GROUP BY ds.source_id;""", used_by="Method & data page, top-bar badges")
q("9.2  Sentiment distribution",
  "Should read 1,859 Negative / 366 Neutral / 375 Positive, identical to the analyzer's own `classified_comments.csv`.",
  """
  SELECT s.sentiment_label AS sentiment, COUNT(*) AS comments,
         ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percent,
         ROUND(AVG(c.sentiment_score), 3) AS avg_score, ROUND(AVG(c.sentiment_confidence), 3) AS avg_confidence
  FROM comment c JOIN sentiment s USING(sentiment_id)
  WHERE c.external_id IS NOT NULL
  GROUP BY s.sentiment_id
  ORDER BY comments DESC;""", used_by="YouTube page")
q("9.3  Sentiment over time (by year)",
  "`substr(published_at, 1, 4)` takes the year from the ISO-8601 timestamp.",
  """
  SELECT substr(c.published_at, 1, 4) AS year,
         SUM(s.sentiment_label = 'Negative') AS negative,
         SUM(s.sentiment_label = 'Neutral')  AS neutral,
         SUM(s.sentiment_label = 'Positive') AS positive,
         COUNT(*) AS total
  FROM comment c JOIN sentiment s USING(sentiment_id)
  WHERE c.external_id IS NOT NULL
  GROUP BY year ORDER BY year;""", used_by="YouTube page")
q("9.4  Sentiment-score histogram",
  "Ten equal bins from −1 to +1 using integer arithmetic.",
  """
  SELECT MIN(9, CAST((sentiment_score + 1) * 5 AS INTEGER)) AS bin,
         ROUND(-1 + MIN(9, CAST((sentiment_score + 1) * 5 AS INTEGER)) * 0.2, 1) AS from_score,
         COUNT(*) AS comments
  FROM comment WHERE external_id IS NOT NULL
  GROUP BY bin ORDER BY bin;""", used_by="YouTube page")
q("9.5  Most-liked comments",
  "Joins `commenter` for the display name.",
  """
  SELECT c.like_count, c.reply_count, s.sentiment_label AS sentiment, cu.display_name AS commenter, substr(c.comment_text, 1, 90) AS comment
  FROM comment c
  JOIN sentiment s  USING(sentiment_id)
  JOIN commenter cu USING(commenter_id)
  WHERE c.external_id IS NOT NULL
  ORDER BY c.like_count DESC
  LIMIT 5;""", used_by="YouTube page")
q("9.6  Do negative comments get more likes?",
  "Average and total likes by sentiment.",
  """
  SELECT s.sentiment_label, COUNT(*) AS comments, ROUND(AVG(c.like_count), 1) AS avg_likes, SUM(c.like_count) AS total_likes, MAX(c.like_count) AS max_likes
  FROM comment c JOIN sentiment s USING(sentiment_id)
  WHERE c.external_id IS NOT NULL
  GROUP BY s.sentiment_id;""", used_by="YouTube page")
q("9.7  Commenters who wrote more than one comment",
  "`HAVING` filters groups; shows why `commenter` is its own table (one person, many comments).",
  """
  SELECT cu.display_name, COUNT(*) AS comments, ROUND(AVG(c.sentiment_score), 2) AS avg_score
  FROM comment c JOIN commenter cu USING(commenter_id)
  GROUP BY cu.commenter_id
  HAVING COUNT(*) > 1
  ORDER BY comments DESC
  LIMIT 5;""")
q("9.8  Comments about a word, by sentiment",
  "",
  """
  SELECT s.sentiment_label, COUNT(*) AS mentions
  FROM comment c JOIN sentiment s USING(sentiment_id)
  WHERE c.external_id IS NOT NULL AND lower(c.comment_text) LIKE '%woke%'
  GROUP BY s.sentiment_id;""")
q("9.9  Comments per month for one year",
  "",
  """
  SELECT substr(published_at, 1, 7) AS month, COUNT(*) AS comments
  FROM comment
  WHERE external_id IS NOT NULL AND published_at >= '2022-01-01' AND published_at < '2023-01-01'
  GROUP BY month ORDER BY month;""")

section("10. Adding data (INSERT)",
        """
        Foreign keys are looked up with **scalar sub-selects** so you never need to remember numeric ids.
        Each group below was executed inside one transaction and rolled back, so the sequence is verified but the
        database is unchanged. In your own code, finish with `COMMIT` (or `conn.commit()`).
        Remember `PRAGMA foreign_keys = ON;` on every connection (the app's `database.connect()` does it for you).
        """)
q("10.1  Add a new lookup value (idempotent)",
  "`INSERT OR IGNORE` skips the row if the `UNIQUE` name already exists.",
  ["INSERT OR IGNORE INTO brand (brand_name) VALUES ('Zari House');",
   "INSERT OR IGNORE INTO brand (brand_name) VALUES ('Nayab Threads');",
   "INSERT OR IGNORE INTO campaign (campaign_name) VALUES ('Black Friday');"], "dml")
q("10.2  Add a brand's page on a platform (account)",
  "The follower count belongs to the *brand + platform pair*, hence its own table.",
  ["INSERT OR IGNORE INTO brand (brand_name) VALUES ('Nayab Threads');",
   """INSERT INTO account (brand_id, platform_id, followers)
      VALUES ((SELECT brand_id FROM brand WHERE brand_name = 'Nayab Threads'),
              (SELECT platform_id FROM platform WHERE platform_name = 'Instagram'), 150000);"""], "dml")
q("10.3  Add a data source, a post (Table A) and its comments (Table B)",
  "A complete manual entry: source → post → commenters → comments. The classifier fields (language, topic, sentiment, intent) are lookups chosen by name.",
  ["""INSERT INTO data_source (source_name, provenance, source_url, collected_on, reuse_permission, include_in_analysis)
      VALUES ('Manual entry', 'observed', NULL, '2026-11-15', 'Own data', 1);""",
   """INSERT INTO post (post_id, account_id, campaign_id, content_type_id, category_id, source_id,
                      likes, comments_count, shares, views, days_since_post)
      VALUES ('P9001',
              (SELECT a.account_id FROM account a JOIN brand b USING(brand_id) JOIN platform pl USING(platform_id)
                WHERE b.brand_name = 'Noor Lawn' AND pl.platform_name = 'Instagram'),
              (SELECT campaign_id FROM campaign WHERE campaign_name = '12.12 Sale'),
              (SELECT content_type_id FROM content_type WHERE content_type_name = 'Reel'),
              (SELECT category_id FROM product_category WHERE category_name = 'Lawn suit'),
              (SELECT source_id FROM data_source WHERE source_name = 'Manual entry'),
              5400, 212, 130, 88000, 6);""",
   "INSERT OR IGNORE INTO commenter (display_name) VALUES ('@sana_k');",
   """INSERT INTO comment (post_id, commenter_id, comment_text, language_id, topic_id, sentiment_id, sentiment_score, intent_id)
      VALUES ('P9001',
              (SELECT commenter_id FROM commenter WHERE display_name = '@sana_k'),
              'Price bata dein please',
              (SELECT language_id FROM language_type WHERE language_name = 'Roman Urdu'),
              (SELECT topic_id FROM topic WHERE topic_name = 'Price inquiry'),
              (SELECT sentiment_id FROM sentiment WHERE sentiment_label = 'Neutral'), 0.0,
              (SELECT intent_id FROM purchase_intent WHERE intent_label = 'Possible inquiry'));"""], "dml", used_by="python manage.py import")
q("10.4  Bulk-copy rows from another table",
  "`INSERT … SELECT` – e.g. archive the High-priority recommendations into a scratch table.",
  ["CREATE TEMP TABLE high_recs AS SELECT * FROM recommendation WHERE 0;",
   "INSERT INTO high_recs SELECT * FROM recommendation WHERE priority = 'High';"], "dml")
q("10.5  Add a YouTube-style comment (upsert the commenter first)",
  "`ON CONFLICT … DO NOTHING` on the unique `external_id` makes re-imports safe.",
  ["INSERT OR IGNORE INTO commenter (display_name) VALUES ('@new_viewer');",
   """INSERT INTO comment (post_id, external_id, commenter_id, comment_text, published_at, like_count, reply_count,
                         language_id, topic_id, sentiment_id, sentiment_score, sentiment_confidence, intent_id)
      VALUES ('YT-UYaY2Kb_PKI', 'TEST_COMMENT_001',
              (SELECT commenter_id FROM commenter WHERE display_name = '@new_viewer'),
              'Great ad, well said.', '2026-11-15T10:00:00Z', 3, 0,
              (SELECT language_id FROM language_type WHERE language_name = 'English'),
              (SELECT topic_id FROM topic WHERE topic_name = 'Praise'),
              (SELECT sentiment_id FROM sentiment WHERE sentiment_label = 'Positive'), 0.8, 0.9,
              (SELECT intent_id FROM purchase_intent WHERE intent_label = 'No intent'))
      ON CONFLICT(external_id) DO NOTHING;"""], "dml", used_by="python manage.py import-youtube")

section("11. Changing data (UPDATE)")
q("11.1  Correct one comment's sentiment",
  "Change the foreign key, not the text of a label. Optionally store the corrected score too.",
  ["""UPDATE comment
      SET sentiment_id = (SELECT sentiment_id FROM sentiment WHERE sentiment_label = 'Positive'),
          sentiment_score = 0.6
      WHERE comment_id = 1;"""], "dml")
q("11.2  Re-label all comments of one topic",
  "Moves every “Price concern” comment of one brand to “Price inquiry”.",
  ["""UPDATE comment
      SET topic_id = (SELECT topic_id FROM topic WHERE topic_name = 'Price inquiry')
      WHERE topic_id = (SELECT topic_id FROM topic WHERE topic_name = 'Price concern')
        AND post_id IN (SELECT p.post_id FROM post p JOIN account a USING(account_id) JOIN brand b USING(brand_id)
                        WHERE b.brand_name = 'Noor Lawn');"""], "dml")
q("11.3  Update a follower count (one row, every post benefits)",
  "Because followers live in `account`, one `UPDATE` corrects thousands of posts' engagement rates – the payoff of 3NF.",
  ["""UPDATE account
      SET followers = followers + 50000
      WHERE brand_id    = (SELECT brand_id FROM brand WHERE brand_name = 'Noor Lawn')
        AND platform_id = (SELECT platform_id FROM platform WHERE platform_name = 'Instagram');"""], "dml")
q("11.4  Rename a brand (one row, every join follows)",
  "No other table repeats the name, so there is nothing else to update.",
  ["UPDATE brand SET brand_name = 'Noor Lawn Studio' WHERE brand_name = 'Noor Lawn';",
   "SELECT COUNT(*) FROM v_post_flat WHERE brand = 'Noor Lawn Studio';"], "dml")
q("11.5  Update post counters",
  "Fix a post's engagement numbers after a re-scrape; `CHECK` constraints reject negative values.",
  ["UPDATE post SET likes = 6100, comments_count = 240, shares = 150 WHERE post_id = 'P0001';"], "dml")
q("11.6  Keep `comments_count` consistent with stored comments (YouTube video)",
  "Correlated sub-query – used by the YouTube importer.",
  ["""UPDATE post
      SET comments_count = (SELECT COUNT(*) FROM comment c WHERE c.post_id = post.post_id)
      WHERE post_id LIKE 'YT-%';"""], "dml")
q("11.7  Include / exclude a data source from the analysis",
  "The single switch that keeps YouTube out of the lawn-suit clusters. After changing it, run `python manage.py analyze`.",
  ["UPDATE data_source SET include_in_analysis = 1 WHERE source_name LIKE 'YouTube%';"], "dml")
q("11.8  Change a recommendation's priority",
  "",
  ["UPDATE recommendation SET priority = 'Low' WHERE rec_id = 1;"], "dml")
q("11.9  Manually assign a comment to a segment",
  "",
  ["""UPDATE comment
      SET segment_id = (SELECT segment_id FROM segment WHERE segment_name = 'Price askers')
      WHERE comment_id = 2;"""], "dml")

section("12. Removing data (DELETE)",
        "`ON DELETE CASCADE` is declared from `comment`, `segment_map_point` and `post_anomaly` towards their parent, so deleting a post removes its comments, map points and anomaly row automatically.")
q("12.1  Delete one comment",
  "",
  ["DELETE FROM comment WHERE comment_id = 3;"], "dml")
q("12.2  Delete a post and everything that depends on it (cascade)",
  "Run it and compare the counts: the comments of the post disappear with it.",
  ["SELECT COUNT(*) AS comments_before FROM comment WHERE post_id = 'P0001';",
   "DELETE FROM post WHERE post_id = 'P0001';",
   "SELECT COUNT(*) AS comments_after FROM comment WHERE post_id = 'P0001';"], "dml")
q("12.3  Remove commenters that no longer have comments (orphans)",
  "Clean-up after bulk deletes.",
  ["""DELETE FROM commenter
      WHERE commenter_id NOT IN (SELECT commenter_id FROM comment WHERE commenter_id IS NOT NULL);"""], "dml")
q("12.4  Remove an entire data source",
  "Delete children first (comments cascade from posts), then posts, then accounts that are no longer used, then the source.",
  ["DELETE FROM post WHERE source_id = (SELECT source_id FROM data_source WHERE source_name LIKE 'YouTube%');",
   "DELETE FROM data_source WHERE source_name LIKE 'YouTube%';",
   "SELECT COUNT(*) AS youtube_comments_left FROM comment WHERE external_id IS NOT NULL;"], "dml")
q("12.5  Clear derived results before re-running the analysis",
  "Exactly what `pipeline.run_analysis()` does; analysis tables can always be rebuilt.",
  ["DELETE FROM recommendation;", "DELETE FROM post_anomaly;", "DELETE FROM segment_map_point;",
   "UPDATE comment SET segment_id = NULL;", "DELETE FROM segment;"], "dml")
q("12.6  Delete old comments by date",
  "",
  ["DELETE FROM comment WHERE published_at IS NOT NULL AND published_at < '2020-01-01';"], "dml")

section("13. Safety nets: constraints and transactions",
        "These statements are **supposed to fail**; the error text below is the real message SQLite returned.")
q("13.1  CHECK constraint – negative likes",
  "", ["UPDATE post SET likes = -5 WHERE post_id = 'P0002';"], "error")
q("13.2  FOREIGN KEY – comment for a post that does not exist",
  "Requires `PRAGMA foreign_keys = ON`.",
  ["""INSERT INTO comment (post_id, comment_text, language_id, topic_id, sentiment_id, intent_id)
      VALUES ('NO-SUCH-POST', 'hello', 1, 1, 1, 1);"""], "error")
q("13.3  UNIQUE – duplicate lookup value",
  "", ["INSERT INTO brand (brand_name) VALUES ('Zari House');"], "error")
q("13.4  Restricting a delete – brand still in use",
  "A lookup row that is referenced cannot be deleted.", ["DELETE FROM brand WHERE brand_name = 'Zari House';"], "error")
q("13.5  Transaction pattern",
  "All-or-nothing: either every statement applies or none (`ROLLBACK`). Shown here with `SAVEPOINT`.",
  ["SAVEPOINT demo;", "UPDATE post SET likes = likes + 1 WHERE post_id = 'P0003';",
   "DELETE FROM comment WHERE post_id = 'P0003';", "ROLLBACK TO demo;", "RELEASE demo;"], "dml")

section("14. Integrity checks, performance and maintenance")
q("14.1  Foreign-key and integrity check", "Both should return nothing / `ok`.",
  "PRAGMA foreign_key_check;")
q("14.2  Comments whose post is missing (orphans)", "Should be 0.",
  "SELECT COUNT(*) AS orphan_comments FROM comment c LEFT JOIN post p USING(post_id) WHERE p.post_id IS NULL;")
q("14.3  Duplicate YouTube comment ids", "Should return no rows (`external_id` is UNIQUE).",
  "SELECT external_id, COUNT(*) FROM comment WHERE external_id IS NOT NULL GROUP BY external_id HAVING COUNT(*) > 1;")
q("14.4  Row counts of every table", "",
  """
  SELECT 'brand' AS tbl, COUNT(*) AS n FROM brand UNION ALL SELECT 'platform', COUNT(*) FROM platform
  UNION ALL SELECT 'campaign', COUNT(*) FROM campaign UNION ALL SELECT 'content_type', COUNT(*) FROM content_type
  UNION ALL SELECT 'account', COUNT(*) FROM account UNION ALL SELECT 'data_source', COUNT(*) FROM data_source
  UNION ALL SELECT 'post', COUNT(*) FROM post UNION ALL SELECT 'commenter', COUNT(*) FROM commenter
  UNION ALL SELECT 'comment', COUNT(*) FROM comment UNION ALL SELECT 'segment', COUNT(*) FROM segment
  UNION ALL SELECT 'post_anomaly', COUNT(*) FROM post_anomaly UNION ALL SELECT 'recommendation', COUNT(*) FROM recommendation;""")
q("14.5  Is an index used?", "`EXPLAIN QUERY PLAN` shows `SEARCH … USING INDEX ix_comment_post` rather than a full scan.",
  "EXPLAIN QUERY PLAN SELECT * FROM comment WHERE post_id = 'P0001';")
q("14.6  List the schema", "", "SELECT type, name FROM sqlite_master WHERE type IN ('table','view','index') AND name NOT LIKE 'sqlite_%' ORDER BY type, name LIMIT 12;")


# ==================================================================================================
def cut(v, n=60):
    s = "NULL" if v is None else str(v).replace("\n", " ").replace("|", "\\|")
    return s if len(s) <= n else s[: n - 1] + "…"


def md_table(cols, rows):
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(cut(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def run_entry(conn, e):
    stmts = e["sql"] if isinstance(e["sql"], list) else [e["sql"]]
    if e["kind"] == "select":
        cur = conn.execute(stmts[0].rstrip(";"))
        rows = cur.fetchall()
        cols = [d[0] for d in cur.description] if cur.description else []
        res = f"**Returns {len(rows)} row{'s' if len(rows) != 1 else ''}**"
        if rows and cols:
            res += (" (first 4 shown):\n\n" if len(rows) > 4 else ":\n\n") + md_table(cols, rows[:4])
        return res
    if e["kind"] == "error":
        try:
            conn.execute("SAVEPOINT t")
            for s in stmts: conn.execute(s)
            raise SystemExit(f"EXPECTED FAILURE DID NOT FAIL: {e['title']}")
        except sqlite3.Error as ex:
            conn.execute("ROLLBACK TO t"); conn.execute("RELEASE t")
            return f"**Fails as intended:** `{type(ex).__name__}: {ex}`"
    # dml group
    conn.execute("SAVEPOINT g")
    notes = []
    for s in stmts:
        cur = conn.execute(s)
        if s.lstrip().upper().startswith("SELECT"):
            r = cur.fetchall(); notes.append(f"`{cut(s.split('FROM')[0].replace('SELECT','').strip(), 40)}` → {r[0][0] if r and len(r[0]) == 1 else r}")
        elif s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            notes.append(f"{s.lstrip().split()[0].upper()} {cur.rowcount} row{'s' if cur.rowcount != 1 else ''}")
    conn.execute("ROLLBACK TO g"); conn.execute("RELEASE g")
    return "**Verified** (ran in a transaction, then rolled back): " + "; ".join(notes)


PY_SNIPPETS = [
 ("Plain `sqlite3` with parameters (never build SQL with string concatenation)", '''
import sqlite3
conn = sqlite3.connect("data/campaign.db")
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA foreign_keys = ON")

# read, with ? placeholders
rows = conn.execute("""SELECT post_id, likes FROM v_post_flat
                       WHERE platform = ? AND content_type = ? ORDER BY likes DESC LIMIT ?""",
                    ("Instagram", "Reel", 3)).fetchall()
print([dict(r) for r in rows])

# write inside a transaction (the `with` block commits, or rolls back on error)
with conn:
    conn.execute("INSERT OR IGNORE INTO commenter (display_name) VALUES (?)", ("@demo_user",))
    conn.execute("UPDATE post SET likes = likes + ? WHERE post_id = ?", (10, "P0001"))
    conn.rollback()                     # demo only: undo so the database stays unchanged
'''),
 ("Load query results straight into pandas", '''
import sqlite3, pandas as pd
conn = sqlite3.connect("data/campaign.db")
df = pd.read_sql_query("""
    SELECT topic, sentiment, COUNT(*) AS n
    FROM v_comment_flat
    WHERE segment_id IS NOT NULL
    GROUP BY topic, sentiment""", conn)
print(df.pivot(index="topic", columns="sentiment", values="n").head())
'''),
 ("Use the project's own helpers (read-only connection, same code the web app uses)", '''
from campaign_engine import database as db
print(db.query("SELECT segment_name, COUNT(*) AS n FROM comment JOIN segment USING(segment_id) GROUP BY 1 ORDER BY n DESC LIMIT 3"))
posts, comments = db.frames()          # cached DataFrames with engagement_rate, er_index ... derived
print(posts[["post_id", "engagement_rate"]].head(3))
'''),
 ("Add real data with the command line (bash)", '''
# YouTube Comment Sentiment Analyzer output  ->  post + comment rows  (safe to re-run)
python manage.py import-youtube --csv data/youtube/youtube_classified_comments.csv

# real lawn-suit posts + comments from your own CSV files
python manage.py import --posts my_posts.csv --comments my_comments.csv --source "Public posts, Nov 2026"

# rebuild clustering, anomalies and recommendations after changing data
python manage.py analyze
'''),
]


def main():
    tmp = Path(tempfile.mkdtemp()) / "scratch.db"
    shutil.copy(config.DB_PATH, tmp)
    conn = sqlite3.connect(tmp, isolation_level=None)       # autocommit; we manage SAVEPOINTs ourselves
    conn.execute("PRAGMA foreign_keys = ON")
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in
              ("brand", "platform", "campaign", "content_type", "account", "post", "commenter", "comment", "segment", "post_anomaly", "recommendation")}
    yt = conn.execute("SELECT COUNT(*) FROM comment WHERE external_id IS NOT NULL").fetchone()[0]

    out = []
    w = out.append
    w("# Database Query Guide")
    w("")
    w("**Pakistan Social Audience & Campaign Intelligence Engine – Project 3**  ")
    w("How to retrieve, add, change and delete data in the project's SQLite database (`data/campaign.db`).")
    w("")
    w("> Every statement in this guide was executed against a copy of the real database when the guide was generated "
      "(`python tools/build_query_docs.py`). Results shown are real. `INSERT` / `UPDATE` / `DELETE` examples ran inside a "
      "transaction that was rolled back, so the guide never changes your data.")
    w("")
    w("## 1. The database at a glance")
    w("")
    w(f"* **{counts['post']:,} posts** (Table A) and **{counts['comment']:,} comments** (Table B), "
      f"of which **{yt:,} are real YouTube comments** imported from the YouTube Comment Sentiment Analyzer; the rest are simulated.")
    w(f"* {counts['brand']} brands · {counts['platform']} platforms · {counts['campaign']} campaigns · {counts['content_type']} content types · "
      f"{counts['account']} brand-platform accounts · {counts['commenter']:,} commenters · {counts['segment']} segments · "
      f"{counts['post_anomaly']} flagged posts · {counts['recommendation']} recommendations.")
    w("* Normal form: **3NF**. Names live once in lookup tables; derived numbers (engagement rate, totals) are *never stored* – they are computed in queries.")
    w("* Two read-only views simplify most queries: **`v_post_flat`** (post + brand, platform, campaign, content type, followers, source) and "
      "**`v_comment_flat`** (comment + language, topic, sentiment, intent, segment, commenter).")
    w("")
    w("### Tables")
    w("")
    w("| Table | Purpose | Key columns |")
    w("|---|---|---|")
    for t, p, k in [
        ("brand, platform, campaign, content_type, product_category", "Lookup tables – each name stored once", "`*_id` PK, `*_name` UNIQUE"),
        ("language_type, sentiment, purchase_intent, topic", "Lookup tables for comment labels (`topic.theme` groups topics)", "`*_id` PK"),
        ("data_source", "Where data came from: `provenance` = simulated / observed; `include_in_analysis` 0/1", "`source_id` PK"),
        ("account", "A brand's page on a platform; holds `followers`", "`brand_id` + `platform_id` UNIQUE"),
        ("post  **(Table A)**", "One social media post / video: likes, comments_count, shares, views, days_since_post", "`post_id` PK; FKs to account, campaign, content_type, product_category, data_source"),
        ("commenter", "A person who comments (one person, many comments)", "`commenter_id` PK, `display_name` UNIQUE"),
        ("comment  **(Table B)**", "One comment: text, language, topic, sentiment (+score, confidence), intent, segment, likes, replies, timestamp", "`comment_id` PK; `post_id` FK (cascade); `external_id` UNIQUE"),
        ("segment, segment_map_point", "Clustering output: audience segments and 2-D map coordinates", "`segment_id` PK"),
        ("post_anomaly", "Unusual posts with type and plain-English reason", "`post_id` PK (cascade)"),
        ("recommendation", "Evidence-backed next steps", "`rec_id` PK"),
        ("run_metadata", "k, silhouette scores, classifier accuracy, timestamps", "`key` PK")]:
        w(f"| {t} | {p} | {k} |")
    w("")
    w("## 2. Connecting")
    w("")
    w("```bash")
    w("sqlite3 data/campaign.db            # command-line shell (install SQLite, or use DB Browser for SQLite)")
    w("sqlite> PRAGMA foreign_keys = ON;   -- must be set on EVERY connection for FK / cascade rules to apply")
    w("sqlite> .headers on")
    w("sqlite> .mode column")
    w("```")
    w("")
    w("Or open the web app and use **Database & SQL → SQL console** (read-only, single `SELECT`, 500 rows). "
      "Python examples are in section 15.")
    w("")

    for title, intro, entries in S:
        w(f"## {title}")
        w("")
        if intro:
            w(intro); w("")
        for e in entries:
            w(f"### {e['title']}")
            w("")
            if e["why"]:
                w(e["why"]); w("")
            stmts = e["sql"] if isinstance(e["sql"], list) else [e["sql"]]
            w("```sql"); w("\n".join(textwrap.dedent(s).strip() for s in stmts)); w("```"); w("")
            w(run_entry(conn, e)); w("")
            if e["used_by"]:
                w(f"*Used by:* {e['used_by']}"); w("")

    w("## 15. Using the database from Python")
    w("")
    ns_db = str(config.DB_PATH)
    for title, code in PY_SNIPPETS:
        lang = "bash" if "(bash)" in title else "python"
        title = title.replace(" (bash)", "")
        w(f"### {title}"); w("")
        w(f"```{lang}"); w(code.strip()); w("```"); w("")
        if lang == "python":                       # prove the snippet runs (against the scratch copy)
            import contextlib, io, os
            src = code.replace("data/campaign.db", str(tmp))
            buf = io.StringIO()
            old = os.getcwd(); os.chdir(ROOT)
            try:
                with contextlib.redirect_stdout(buf):
                    if "campaign_engine" in src:
                        config.DB_PATH = tmp
                    exec(compile(src, "snippet", "exec"), {})
            finally:
                os.chdir(old); config.DB_PATH = Path(ns_db)
            printed = buf.getvalue().strip()
            if printed:
                w("Output:"); w(""); w("```text"); w(printed[:700]); w("```"); w("")

    w("## 16. Which page runs which query")
    w("")
    w("| Page | URL | Main queries |")
    w("|---|---|---|")
    for pg, url, qs in [
        ("Dashboard", "`/`", "3.1, 4.1, 5.1, 6.1, 7.1, 8.1"),
        ("1 · What attracts attention?", "`/content`", "4.1 – 4.4"),
        ("2 · What does the audience want?", "`/audience`", "5.1 – 5.7"),
        ("3 · What is unusual?", "`/anomalies`", "6.1 – 6.4"),
        ("4 · Audience segments", "`/segments`", "7.1 – 7.5"),
        ("5 · Recommendations", "`/recommendations`", "8.1, 8.2"),
        ("YouTube sentiment (real data)", "`/youtube`", "9.1 – 9.9"),
        ("Posts / Post detail", "`/posts`, `/posts/<id>`", "3.1 – 3.5"),
        ("Comments", "`/comments`", "5.5, 9.5"),
        ("Database & SQL console", "`/database`", "any `SELECT` from this guide"),
        ("CSV exports", "`/export/<posts|comments|anomalies|recommendations>.csv`", "views `v_post_flat`, `v_comment_flat`")]:
        w(f"| {pg} | {url} | {qs} |")
    w("")
    w("## 17. Tips and cautions")
    w("")
    w("* **Never concatenate user input into SQL** – use `?` placeholders (section 15).")
    w("* **Back up before bulk changes:** copy `data/campaign.db`, or `sqlite3 data/campaign.db \".backup backup.db\"`.")
    w("* After changing posts, comments or `include_in_analysis`, run `python manage.py analyze` so segments, anomalies and recommendations match the data.")
    w("* `python manage.py setup` rebuilds the whole database (simulated data + YouTube import + analysis) from scratch.")
    w("* The 2,600 YouTube comments include commenters' public display names; do not publish the database without checking YouTube's terms and privacy expectations.")
    w("* Regenerate this guide after schema changes: `python tools/build_query_docs.py`.")
    w("")
    conn.close()
    dest = ROOT / "docs" / "DATABASE_QUERIES.md"
    dest.write_text("\n".join(out), encoding="utf-8")
    n_q = sum(len(e) for _, _, e in S)
    print(f"wrote {dest}  ({n_q} verified statements/groups, {len(out)} lines)")


if __name__ == "__main__":
    main()
