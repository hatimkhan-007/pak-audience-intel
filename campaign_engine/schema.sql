-- ============================================================================
--  Pakistan Social Audience & Campaign Intelligence Engine  -  3NF schema
--  Every table: atomic columns (1NF), no partial dependencies (2NF),
--  no transitive dependencies (3NF).  Derived numbers (engagement rate,
--  totals, peer groups) are NOT stored; they are computed in views/queries.
-- ============================================================================
PRAGMA foreign_keys = ON;

-- ---------- lookup / dimension tables ---------------------------------------
CREATE TABLE brand            (brand_id        INTEGER PRIMARY KEY,
                               brand_name      TEXT NOT NULL UNIQUE);
CREATE TABLE platform         (platform_id     INTEGER PRIMARY KEY,
                               platform_name   TEXT NOT NULL UNIQUE);
CREATE TABLE campaign         (campaign_id     INTEGER PRIMARY KEY,
                               campaign_name   TEXT NOT NULL UNIQUE);
CREATE TABLE content_type     (content_type_id INTEGER PRIMARY KEY,
                               content_type_name TEXT NOT NULL UNIQUE);
CREATE TABLE product_category (category_id     INTEGER PRIMARY KEY,
                               category_name   TEXT NOT NULL UNIQUE);
CREATE TABLE language_type    (language_id     INTEGER PRIMARY KEY,
                               language_name   TEXT NOT NULL UNIQUE);
CREATE TABLE sentiment        (sentiment_id    INTEGER PRIMARY KEY,
                               sentiment_label TEXT NOT NULL UNIQUE);
CREATE TABLE purchase_intent  (intent_id       INTEGER PRIMARY KEY,
                               intent_label    TEXT NOT NULL UNIQUE);
CREATE TABLE topic            (topic_id        INTEGER PRIMARY KEY,
                               topic_name      TEXT NOT NULL UNIQUE,
                               theme           TEXT NOT NULL);

-- ---------- provenance: observed vs simulated -------------------------------
CREATE TABLE data_source (
    source_id        INTEGER PRIMARY KEY,
    source_name      TEXT NOT NULL UNIQUE,
    provenance       TEXT NOT NULL CHECK (provenance IN ('observed','simulated')),
    source_url       TEXT,
    collected_on     TEXT NOT NULL,
    reuse_permission TEXT,
    include_in_analysis INTEGER NOT NULL DEFAULT 1 CHECK (include_in_analysis IN (0,1))
);  -- 0 = stored and browsable, but kept out of the lawn-suit clustering / recommendations

-- ---------- a brand's page on one platform (followers depend on the pair) ----
CREATE TABLE account (
    account_id  INTEGER PRIMARY KEY,
    brand_id    INTEGER NOT NULL REFERENCES brand(brand_id),
    platform_id INTEGER NOT NULL REFERENCES platform(platform_id),
    followers   INTEGER CHECK (followers IS NULL OR followers >= 0),
    UNIQUE (brand_id, platform_id)
);

-- ---------- Table A : social media posts ------------------------------------
CREATE TABLE post (
    post_id         TEXT PRIMARY KEY,
    account_id      INTEGER NOT NULL REFERENCES account(account_id),
    campaign_id     INTEGER NOT NULL REFERENCES campaign(campaign_id),
    content_type_id INTEGER NOT NULL REFERENCES content_type(content_type_id),
    category_id     INTEGER NOT NULL REFERENCES product_category(category_id),
    source_id       INTEGER NOT NULL REFERENCES data_source(source_id),
    likes           INTEGER CHECK (likes IS NULL OR likes >= 0),       -- NULL when the source gives no post-level likes
    comments_count  INTEGER NOT NULL CHECK (comments_count >= 0),
    shares          INTEGER CHECK (shares IS NULL OR shares >= 0),   -- if available
    views           INTEGER CHECK (views  IS NULL OR views  >= 0),   -- if available
    days_since_post INTEGER CHECK (days_since_post IS NULL OR days_since_post >= 0)
);

-- ---------- analysis output: audience segments (clusters) -------------------
CREATE TABLE segment (
    segment_id       INTEGER PRIMARY KEY,
    segment_name     TEXT NOT NULL,
    description      TEXT NOT NULL,
    suggested_action TEXT NOT NULL,
    top_terms        TEXT NOT NULL
);

-- ---------- people who comment (a commenter writes many comments) -----------
CREATE TABLE commenter (
    commenter_id INTEGER PRIMARY KEY,
    display_name TEXT NOT NULL UNIQUE
);

-- ---------- Table B : comments ----------------------------------------------
CREATE TABLE comment (
    comment_id           INTEGER PRIMARY KEY,
    post_id              TEXT    NOT NULL REFERENCES post(post_id) ON DELETE CASCADE,
    external_id          TEXT    UNIQUE,                       -- id on the source platform (e.g. YouTube comment id)
    commenter_id         INTEGER REFERENCES commenter(commenter_id),
    comment_text         TEXT    NOT NULL,
    published_at         TEXT,                                 -- ISO-8601, when the platform provides it
    like_count           INTEGER CHECK (like_count  IS NULL OR like_count  >= 0),
    reply_count          INTEGER CHECK (reply_count IS NULL OR reply_count >= 0),
    language_id          INTEGER NOT NULL REFERENCES language_type(language_id),
    topic_id             INTEGER NOT NULL REFERENCES topic(topic_id),
    sentiment_id         INTEGER NOT NULL REFERENCES sentiment(sentiment_id),
    sentiment_score      REAL    CHECK (sentiment_score IS NULL OR sentiment_score BETWEEN -1 AND 1),
    sentiment_confidence REAL    CHECK (sentiment_confidence IS NULL OR sentiment_confidence BETWEEN 0 AND 1),
    intent_id            INTEGER NOT NULL REFERENCES purchase_intent(intent_id),
    segment_id           INTEGER REFERENCES segment(segment_id)
);

CREATE TABLE segment_map_point (            -- 2-D projection for the cluster map
    comment_id INTEGER PRIMARY KEY REFERENCES comment(comment_id) ON DELETE CASCADE,
    x REAL NOT NULL,
    y REAL NOT NULL
);

CREATE TABLE post_anomaly (
    post_id       TEXT PRIMARY KEY REFERENCES post(post_id) ON DELETE CASCADE,
    anomaly_score REAL NOT NULL,
    anomaly_type  TEXT NOT NULL,
    reason        TEXT NOT NULL
);

CREATE TABLE recommendation (
    rec_id     INTEGER PRIMARY KEY,
    area       TEXT NOT NULL CHECK (area IN ('Content','Promotions','Customer service','Campaign testing')),
    priority   TEXT NOT NULL CHECK (priority IN ('High','Medium','Low')),
    title      TEXT NOT NULL,
    evidence   TEXT NOT NULL,
    action     TEXT NOT NULL,
    segment_id INTEGER REFERENCES segment(segment_id)
);

CREATE TABLE run_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);

-- ---------- indexes on foreign keys -----------------------------------------
CREATE INDEX ix_post_account  ON post(account_id);
CREATE INDEX ix_post_campaign ON post(campaign_id);
CREATE INDEX ix_post_ctype    ON post(content_type_id);
CREATE INDEX ix_comment_post  ON comment(post_id);
CREATE INDEX ix_comment_topic ON comment(topic_id);
CREATE INDEX ix_comment_seg   ON comment(segment_id);
CREATE INDEX ix_comment_commenter ON comment(commenter_id);
CREATE INDEX ix_comment_published ON comment(published_at);

-- ---------- read models (joins only; nothing derived is persisted) ----------
CREATE VIEW v_post_flat AS
SELECT p.post_id, b.brand_name AS brand, pl.platform_name AS platform,
       c.campaign_name AS campaign, ct.content_type_name AS content_type,
       pc.category_name AS product_category, a.followers,
       p.likes, p.comments_count, p.shares, p.views, p.days_since_post,
       ds.source_name, ds.provenance, ds.include_in_analysis
FROM post p
JOIN account a          ON a.account_id = p.account_id
JOIN brand b            ON b.brand_id = a.brand_id
JOIN platform pl        ON pl.platform_id = a.platform_id
JOIN campaign c         ON c.campaign_id = p.campaign_id
JOIN content_type ct    ON ct.content_type_id = p.content_type_id
JOIN product_category pc ON pc.category_id = p.category_id
JOIN data_source ds     ON ds.source_id = p.source_id;

CREATE VIEW v_comment_flat AS
SELECT cm.comment_id, cm.post_id, cm.external_id, cm.comment_text, cu.display_name AS commenter,
       cm.published_at, cm.like_count, cm.reply_count, cm.sentiment_score, cm.sentiment_confidence,
       l.language_name AS language_type, t.topic_name AS topic, t.theme,
       s.sentiment_label AS sentiment, i.intent_label AS purchase_intent,
       cm.segment_id, sg.segment_name AS segment
FROM comment cm
JOIN language_type l   ON l.language_id = cm.language_id
JOIN topic t           ON t.topic_id = cm.topic_id
JOIN sentiment s       ON s.sentiment_id = cm.sentiment_id
JOIN purchase_intent i ON i.intent_id = cm.intent_id
LEFT JOIN segment sg   ON sg.segment_id = cm.segment_id
LEFT JOIN commenter cu ON cu.commenter_id = cm.commenter_id;
