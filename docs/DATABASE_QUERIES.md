# Database Query Guide

**Pakistan Social Audience & Campaign Intelligence Engine – Project 3**  
How to retrieve, add, change and delete data in the project's SQLite database (`data/campaign.db`).

> Every statement in this guide was executed against a copy of the real database when the guide was generated (`python tools/build_query_docs.py`). Results shown are real. `INSERT` / `UPDATE` / `DELETE` examples ran inside a transaction that was rolled back, so the guide never changes your data.

## 1. The database at a glance

* **3,001 posts** (Table A) and **31,795 comments** (Table B), of which **2,600 are real YouTube comments** imported from the YouTube Comment Sentiment Analyzer; the rest are simulated.
* 7 brands · 4 platforms · 6 campaigns · 7 content types · 19 brand-platform accounts · 2,486 commenters · 14 segments · 84 flagged posts · 19 recommendations.
* Normal form: **3NF**. Names live once in lookup tables; derived numbers (engagement rate, totals) are *never stored* – they are computed in queries.
* Two read-only views simplify most queries: **`v_post_flat`** (post + brand, platform, campaign, content type, followers, source) and **`v_comment_flat`** (comment + language, topic, sentiment, intent, segment, commenter).

### Tables

| Table | Purpose | Key columns |
|---|---|---|
| brand, platform, campaign, content_type, product_category | Lookup tables – each name stored once | `*_id` PK, `*_name` UNIQUE |
| language_type, sentiment, purchase_intent, topic | Lookup tables for comment labels (`topic.theme` groups topics) | `*_id` PK |
| data_source | Where data came from: `provenance` = simulated / observed; `include_in_analysis` 0/1 | `source_id` PK |
| account | A brand's page on a platform; holds `followers` | `brand_id` + `platform_id` UNIQUE |
| post  **(Table A)** | One social media post / video: likes, comments_count, shares, views, days_since_post | `post_id` PK; FKs to account, campaign, content_type, product_category, data_source |
| commenter | A person who comments (one person, many comments) | `commenter_id` PK, `display_name` UNIQUE |
| comment  **(Table B)** | One comment: text, language, topic, sentiment (+score, confidence), intent, segment, likes, replies, timestamp | `comment_id` PK; `post_id` FK (cascade); `external_id` UNIQUE |
| segment, segment_map_point | Clustering output: audience segments and 2-D map coordinates | `segment_id` PK |
| post_anomaly | Unusual posts with type and plain-English reason | `post_id` PK (cascade) |
| recommendation | Evidence-backed next steps | `rec_id` PK |
| run_metadata | k, silhouette scores, classifier accuracy, timestamps | `key` PK |

## 2. Connecting

```bash
sqlite3 data/campaign.db            # command-line shell (install SQLite, or use DB Browser for SQLite)
sqlite> PRAGMA foreign_keys = ON;   -- must be set on EVERY connection for FK / cascade rules to apply
sqlite> .headers on
sqlite> .mode column
```

Or open the web app and use **Database & SQL → SQL console** (read-only, single `SELECT`, 500 rows). Python examples are in section 15.

## 3. Retrieving data (SELECT)

The front end only reads. These are the queries behind each page, written in plain SQL so they can be run in the
**SQL console** (`/database`) or any SQLite client. Joins go through the lookup tables because names are stored once (3NF).

### 3.1  List the 20 most-engaging posts (with pagination)

Reads the `v_post_flat` view (a ready-made join of `post`, `account`, `brand`, `platform`, `campaign`, `content_type`, `product_category`, `data_source`). `LIMIT/OFFSET` gives pagination: page *n* uses `OFFSET (n-1)*20`.

```sql
SELECT post_id, brand, platform, content_type, campaign, likes, comments_count, shares, views,
       ROUND((likes + comments_count + COALESCE(shares,0)) * 100.0 / followers, 2) AS engagement_rate_pct
FROM v_post_flat
WHERE followers IS NOT NULL
ORDER BY engagement_rate_pct DESC
LIMIT 20 OFFSET 0;
```

**Returns 20 rows** (first 4 shown):

| post_id | brand | platform | content_type | campaign | likes | comments_count | shares | views | engagement_rate_pct |
|---|---|---|---|---|---|---|---|---|---|
| P0949 | Zari House | TikTok | Influencer Post | Spring Festive Edit | 191975 | 4115 | 8498 | 1267842 | 24.91 |
| P2322 | Rang Mahal | Facebook | Eid Campaign | Eid Collection | 174827 | 30053 | 15745 | NULL | 23.88 |
| P1303 | Mehr Couture | TikTok | Reel | Eid Collection | 78670 | 5551 | 16532 | 873931 | 21.17 |
| P0340 | Sitara Studio | Facebook | Eid Campaign | Summer Lawn Launch | 68406 | 9418 | 7074 | NULL | 16.61 |

*Used by:* Posts page, Content page (top 10)

### 3.2  Filter by platform, brand and campaign

The three global filters (Platform / Brand / Campaign) become `WHERE` conditions.

```sql
SELECT post_id, content_type, likes, comments_count
FROM v_post_flat
WHERE platform = 'Instagram' AND brand = 'Noor Lawn' AND campaign = '11.11 Sale'
ORDER BY likes DESC;
```

**Returns 53 rows** (first 4 shown):

| post_id | content_type | likes | comments_count |
|---|---|---|---|
| P0046 | Styling Video | 78529 | 9800 |
| P0681 | Reel | 62669 | 4140 |
| P1539 | Sale Announcement | 62484 | 23546 |
| P1945 | Reel | 61443 | 5905 |

*Used by:* All filtered pages

### 3.3  Search a post by id

`LIKE` with `%` wildcards; the Posts page search box.

```sql
SELECT post_id, brand, platform, content_type FROM v_post_flat WHERE post_id LIKE '%P004%' ORDER BY post_id;
```

**Returns 10 rows** (first 4 shown):

| post_id | brand | platform | content_type |
|---|---|---|---|
| P0040 | Gulabo Prints | Instagram | Eid Campaign |
| P0041 | Rang Mahal | Facebook | Product Photo |
| P0042 | Zari House | Facebook | Reel |
| P0043 | Rang Mahal | Instagram | Styling Video |

*Used by:* Posts page

### 3.4  The same result using the base tables (explicit joins)

Shows how the normalised tables connect: `post → account → brand / platform`, and `post → campaign / content_type / product_category`.

```sql
SELECT p.post_id, b.brand_name, pl.platform_name, c.campaign_name, ct.content_type_name, a.followers, p.likes
FROM post p
JOIN account a          ON a.account_id      = p.account_id
JOIN brand b            ON b.brand_id        = a.brand_id
JOIN platform pl        ON pl.platform_id    = a.platform_id
JOIN campaign c         ON c.campaign_id     = p.campaign_id
JOIN content_type ct    ON ct.content_type_id = p.content_type_id
WHERE p.post_id = 'P0001';
```

**Returns 1 row**:

| post_id | brand_name | platform_name | campaign_name | content_type_name | followers | likes |
|---|---|---|---|---|---|---|
| P0001 | Rang Mahal | Facebook | 12.12 Sale | Product Photo | 923971 | 2253 |

### 3.5  One post with all of its comments

Post detail page: a one-to-many join (`post` → `comment`).

```sql
SELECT c.comment_id, c.comment_text, c.language_type, c.topic, c.sentiment
FROM v_comment_flat c
WHERE c.post_id = 'P0001'
ORDER BY c.comment_id;
```

**Returns 16 rows** (first 4 shown):

| comment_id | comment_text | language_type | topic | sentiment |
|---|---|---|---|---|
| 1 | When is the sale? 🙄 | English | Discount request | Neutral |
| 2 | When is the sale? please | English | Discount request | Neutral |
| 3 | قیمت بتائیں | Urdu | Price inquiry | Neutral |
| 4 | بہت خوبصورت | Urdu | Praise | Positive |

*Used by:* Post detail page

## 4. Question 1 – which content attracts attention?

### 4.1  Engagement by content type

Average engagement rate = interactions ÷ followers. (SQLite has no `MEDIAN`; the app computes medians in pandas, `AVG` is used here.) Posts younger than 3 days are excluded because their counts are still growing.

```sql
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
ORDER BY avg_engagement_pct DESC;
```

**Returns 6 rows** (first 4 shown):

| content_type | posts | avg_engagement_pct | avg_likes | avg_comments | avg_shares | avg_views |
|---|---|---|---|---|---|---|
| Reel | 610 | 2.58 | 27267.0 | 2841.0 | 4108.0 | 567875.0 |
| Styling Video | 448 | 2.46 | 25848.0 | 2443.0 | 2762.0 | 440941.0 |
| Eid Campaign | 391 | 1.7 | 20679.0 | 4095.0 | 2010.0 | 540219.0 |
| Influencer Post | 635 | 1.45 | 14022.0 | 2468.0 | 1409.0 | 280882.0 |

*Used by:* Content page

### 4.2  Content type × platform matrix

Pivot with conditional aggregation (`CASE` inside `AVG`).

```sql
SELECT content_type,
       ROUND(AVG(CASE WHEN platform='Instagram' THEN (likes+comments_count+COALESCE(shares,0))*100.0/followers END),2) AS instagram,
       ROUND(AVG(CASE WHEN platform='TikTok'    THEN (likes+comments_count+COALESCE(shares,0))*100.0/followers END),2) AS tiktok,
       ROUND(AVG(CASE WHEN platform='Facebook'  THEN (likes+comments_count+COALESCE(shares,0))*100.0/followers END),2) AS facebook
FROM v_post_flat
WHERE include_in_analysis = 1 AND days_since_post >= 3
GROUP BY content_type
ORDER BY content_type;
```

**Returns 6 rows** (first 4 shown):

| content_type | instagram | tiktok | facebook |
|---|---|---|---|
| Eid Campaign | 1.81 | NULL | 1.53 |
| Influencer Post | 1.3 | 2.0 | 0.91 |
| Product Photo | 0.63 | NULL | 0.53 |
| Reel | 2.38 | 3.48 | 1.53 |

*Used by:* Content page heat-map

### 4.3  Campaign and brand comparison

Group by any dimension: swap `campaign` for `brand` or `platform`.

```sql
SELECT campaign, COUNT(*) AS posts, ROUND(AVG(comments_count)) AS avg_comments, ROUND(AVG(likes)) AS avg_likes
FROM v_post_flat
WHERE include_in_analysis = 1
GROUP BY campaign
ORDER BY avg_comments DESC;
```

**Returns 5 rows** (first 4 shown):

| campaign | posts | avg_comments | avg_likes |
|---|---|---|---|
| 11.11 Sale | 593 | 3462.0 | 16455.0 |
| 12.12 Sale | 458 | 3219.0 | 19041.0 |
| Summer Lawn Launch | 615 | 2753.0 | 16320.0 |
| Eid Collection | 895 | 2746.0 | 18655.0 |

*Used by:* Content page

### 4.4  Rank formats inside each platform (window function)

`RANK() OVER (PARTITION BY platform …)` gives the best format per platform without a self-join.

```sql
SELECT platform, content_type, avg_er,
       RANK() OVER (PARTITION BY platform ORDER BY avg_er DESC) AS rank_in_platform
FROM (SELECT platform, content_type,
             ROUND(AVG((likes+comments_count+COALESCE(shares,0))*100.0/followers),2) AS avg_er
      FROM v_post_flat WHERE include_in_analysis = 1 AND days_since_post >= 3
      GROUP BY platform, content_type)
ORDER BY platform, rank_in_platform;
```

**Returns 14 rows** (first 4 shown):

| platform | content_type | avg_er | rank_in_platform |
|---|---|---|---|
| Facebook | Eid Campaign | 1.53 | 1 |
| Facebook | Reel | 1.53 | 1 |
| Facebook | Influencer Post | 0.91 | 3 |
| Facebook | Sale Announcement | 0.82 | 4 |

*Used by:* Recommendations (best format per platform)

## 5. Question 2 – what does the audience want?

### 5.1  Topic distribution

Counts and share of every topic (price, fabric, sizing, delivery, discount, availability, purchase intent…). The subquery in the denominator counts only analysed comments.

```sql
SELECT t.topic_name AS topic, t.theme, COUNT(*) AS comments,
       ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM comment c2 JOIN post p2 USING(post_id)
                                 JOIN data_source d2 USING(source_id) WHERE d2.include_in_analysis = 1), 1) AS share_pct
FROM comment c
JOIN topic t USING(topic_id)
JOIN post p USING(post_id)
JOIN data_source d USING(source_id)
WHERE d.include_in_analysis = 1
GROUP BY t.topic_id
ORDER BY comments DESC;
```

**Returns 11 rows** (first 4 shown):

| topic | theme | comments | share_pct |
|---|---|---|---|
| Praise | General | 4464 | 15.3 |
| Price inquiry | Pricing | 4093 | 14.0 |
| Discount request | Pricing | 4035 | 13.8 |
| Availability | Product | 3856 | 13.2 |

*Used by:* Audience page, Dashboard

### 5.2  Topics by platform

Which platform asks about what.

```sql
SELECT pl.platform_name AS platform, t.topic_name AS topic, COUNT(*) AS comments
FROM comment c
JOIN topic t   USING(topic_id)
JOIN post p    USING(post_id)
JOIN account a USING(account_id)
JOIN platform pl USING(platform_id)
JOIN data_source d ON d.source_id = p.source_id
WHERE d.include_in_analysis = 1
GROUP BY pl.platform_id, t.topic_id
ORDER BY platform, comments DESC;
```

**Returns 33 rows** (first 4 shown):

| platform | topic | comments |
|---|---|---|
| Facebook | Discount request | 1240 |
| Facebook | Price inquiry | 1144 |
| Facebook | Praise | 1132 |
| Facebook | Availability | 1120 |

*Used by:* Audience page (stacked chart)

### 5.3  Sentiment inside each topic

Share of negative comments per topic.

```sql
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
ORDER BY negative_pct DESC;
```

**Returns 11 rows** (first 4 shown):

| topic | negative | neutral | positive | negative_pct |
|---|---|---|---|---|
| Price concern | 1686 | 0 | 0 | 100.0 |
| Delivery complaint | 1651 | 0 | 0 | 100.0 |
| Other | 4 | 1526 | 4 | 0.3 |
| Delivery inquiry | 6 | 2125 | 64 | 0.3 |

*Used by:* Audience page

### 5.4  Language mix and purchase intent

Two lookups joined in one query.

```sql
SELECT l.language_name AS language, i.intent_label AS intent, COUNT(*) AS comments
FROM comment c
JOIN language_type l   USING(language_id)
JOIN purchase_intent i USING(intent_id)
GROUP BY l.language_id, i.intent_id
ORDER BY language, comments DESC;
```

**Returns 12 rows** (first 4 shown):

| language | intent | comments |
|---|---|---|
| English | Possible inquiry | 8303 |
| English | No intent | 4959 |
| English | Ready to buy | 737 |
| English | Post-purchase issue | 630 |

*Used by:* Audience page

### 5.5  Search comments by keyword (English, Roman Urdu or Urdu)

Substring search; the Comments page search box.

```sql
SELECT comment_id, post_id, language_type, topic, sentiment, comment_text
FROM v_comment_flat
WHERE comment_text LIKE '%delivery%' OR comment_text LIKE '%ڈلیوری%'
LIMIT 10;
```

**Returns 10 rows** (first 4 shown):

| comment_id | post_id | language_type | topic | sentiment | comment_text |
|---|---|---|---|---|---|
| 29 | P0002 | English | Delivery inquiry | Neutral | What are the delivery charges? ?? |
| 38 | P0003 | Urdu | Discount request | Neutral | لاہور میں ڈلیوری کا کتنا وقت لگے گا؟ Kuch kam karen na |
| 41 | P0003 | Roman Urdu | Delivery inquiry | Neutral | Delivery kitne din mein hogi? |
| 42 | P0003 | English | Delivery inquiry | Neutral | Courier kitne din lega? What are the delivery charges? plea… |

*Used by:* Comments page

### 5.6  Ready-to-buy comments per brand

Counts the leads a brand should answer first.

```sql
SELECT b.brand_name, COUNT(*) AS ready_to_buy
FROM comment c
JOIN purchase_intent i USING(intent_id)
JOIN post p USING(post_id) JOIN account a USING(account_id) JOIN brand b USING(brand_id)
WHERE i.intent_label = 'Ready to buy'
GROUP BY b.brand_id ORDER BY ready_to_buy DESC;
```

**Returns 7 rows** (first 4 shown):

| brand_name | ready_to_buy |
|---|---|
| Gulabo Prints | 384 |
| Mehr Couture | 341 |
| Rang Mahal | 290 |
| Noor Lawn | 287 |

### 5.7  Cities mentioned in availability questions

Uses `LIKE` per city and `UNION ALL`; the app does the same with a regular expression.

```sql
SELECT 'Karachi' AS city, COUNT(*) AS mentions FROM comment WHERE comment_text LIKE '%karachi%'
UNION ALL SELECT 'Lahore',    COUNT(*) FROM comment WHERE comment_text LIKE '%lahore%'
UNION ALL SELECT 'Islamabad', COUNT(*) FROM comment WHERE comment_text LIKE '%islamabad%'
ORDER BY mentions DESC;
```

**Returns 3 rows**:

| city | mentions |
|---|---|
| Karachi | 502 |
| Lahore | 319 |
| Islamabad | 233 |

*Used by:* Audience page (cities)

## 6. Question 3 – which marketing patterns are unusual?

### 6.1  Flagged posts with the reason

`post_anomaly` holds one row per flagged post (score, type and a plain-English reason written by the engine).

```sql
SELECT a.post_id, v.brand, v.platform, v.content_type, a.anomaly_type, ROUND(a.anomaly_score, 3) AS score, a.reason
FROM post_anomaly a
JOIN v_post_flat v USING(post_id)
ORDER BY a.anomaly_score DESC
LIMIT 10;
```

**Returns 10 rows** (first 4 shown):

| post_id | brand | platform | content_type | anomaly_type | score | reason |
|---|---|---|---|---|---|---|
| P2637 | Zari House | Instagram | Styling Video | Complaint spike | 0.696 | Negative-comment share 58% vs 30% typical; complaint share … |
| P1304 | Gulabo Prints | TikTok | Reel | Under-performer | 0.689 | Comment rate far below the norm for comparable posts (z=-5.… |
| P0197 | Zari House | TikTok | Influencer Post | Complaint spike | 0.687 | Negative-comment share 79% vs 27% typical; complaint share … |
| P1648 | Rang Mahal | Instagram | Reel | Under-performer | 0.648 | Views per follower far below the norm for comparable posts … |

*Used by:* Anomalies page, Dashboard

### 6.2  Count of flagged posts by type

Drives the filter chips on the Anomalies page.

```sql
SELECT anomaly_type, COUNT(*) AS posts, ROUND(AVG(anomaly_score), 3) AS avg_score FROM post_anomaly GROUP BY anomaly_type ORDER BY posts DESC;
```

**Returns 5 rows** (first 4 shown):

| anomaly_type | posts | avg_score |
|---|---|---|
| Under-performer | 26 | 0.576 |
| Viral over-performer | 20 | 0.583 |
| Comment / demand spike | 18 | 0.555 |
| Complaint spike | 11 | 0.607 |

*Used by:* Anomalies page

### 6.3  Posts that beat their own brand's average (subquery)

A hand-written "outlier" check, to compare with the machine-learning flags: posts whose engagement is more than 3× their brand + platform average.

```sql
WITH er AS (
    SELECT post_id, brand, platform,
           (likes + comments_count + COALESCE(shares,0)) * 100.0 / followers AS er
    FROM v_post_flat WHERE include_in_analysis = 1 AND days_since_post >= 3),
avg_er AS (SELECT brand, platform, AVG(er) AS mean_er FROM er GROUP BY brand, platform)
SELECT er.post_id, er.brand, er.platform, ROUND(er.er, 2) AS er, ROUND(a.mean_er, 2) AS brand_platform_avg
FROM er JOIN avg_er a USING (brand, platform)
WHERE er.er > 3 * a.mean_er
ORDER BY er.er DESC
LIMIT 10;
```

**Returns 10 rows** (first 4 shown):

| post_id | brand | platform | er | brand_platform_avg |
|---|---|---|---|---|
| P0949 | Zari House | TikTok | 24.91 | 2.72 |
| P2322 | Rang Mahal | Facebook | 23.88 | 1.22 |
| P1303 | Mehr Couture | TikTok | 21.17 | 3.05 |
| P0340 | Sitara Studio | Facebook | 16.61 | 1.15 |

### 6.4  Flagged posts that have no complaints (anti-join with NOT EXISTS)

Finds viral / under-performing posts whose comments contain no delivery complaints.

```sql
SELECT a.post_id, a.anomaly_type
FROM post_anomaly a
WHERE NOT EXISTS (SELECT 1 FROM comment c JOIN topic t USING(topic_id)
                  WHERE c.post_id = a.post_id AND t.topic_name = 'Delivery complaint')
LIMIT 10;
```

**Returns 10 rows** (first 4 shown):

| post_id | anomaly_type |
|---|---|
| P0115 | Unusual mix |
| P0415 | Viral over-performer |
| P0448 | Comment / demand spike |
| P0471 | Under-performer |

## 7. Question 4 – audience segments (clusters)

### 7.1  Segment sizes

Each comment carries a nullable `segment_id`; comments from sources excluded from analysis (YouTube) have none.

```sql
SELECT s.segment_id, s.segment_name, COUNT(*) AS comments,
       ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM comment WHERE segment_id IS NOT NULL), 1) AS share_pct
FROM comment c
JOIN segment s USING(segment_id)
GROUP BY s.segment_id
ORDER BY comments DESC;
```

**Returns 14 rows** (first 4 shown):

| segment_id | segment_name | comments | share_pct |
|---|---|---|---|
| 1 | Price askers | 3603 | 12.3 |
| 2 | Discount hunters | 3433 | 11.8 |
| 3 | Availability seekers | 2886 | 9.9 |
| 4 | Admirers (English) | 2733 | 9.4 |

*Used by:* Segments page, Dashboard

### 7.2  What each segment is made of

Dominant topics inside each segment (window function picks the top topic per segment).

```sql
SELECT segment_name, topic_name, n
FROM (SELECT s.segment_name, t.topic_name, COUNT(*) AS n,
             ROW_NUMBER() OVER (PARTITION BY s.segment_id ORDER BY COUNT(*) DESC) AS rn
      FROM comment c JOIN segment s USING(segment_id) JOIN topic t USING(topic_id)
      GROUP BY s.segment_id, t.topic_id)
WHERE rn = 1
ORDER BY n DESC;
```

**Returns 14 rows** (first 4 shown):

| segment_name | topic_name | n |
|---|---|---|
| Price askers | Price inquiry | 3327 |
| Discount hunters | Discount request | 3282 |
| Availability seekers | Availability | 2858 |
| Admirers (English) | Praise | 2598 |

*Used by:* Segments page (dominant need)

### 7.3  Segment playbook

The description and suggested action stored with each segment.

```sql
SELECT segment_name, top_terms, suggested_action FROM segment ORDER BY segment_id LIMIT 5;
```

**Returns 5 rows** (first 4 shown):

| segment_name | top_terms | suggested_action |
|---|---|---|
| Price askers | price, price suit, price praise, suit, praise, tell price | Put the price in the caption or the first frame; pin a pric… |
| Discount hunters | discount, code, discount code, discount not, not, discount … | Run time-boxed offers (11.11 / 12.12 style), put the promo … |
| Availability seekers | available, available xcity, available praise, ga, ga availa… | Show stock status and city/store availability in the post; … |
| Admirers (English) | praise, praise praise, بہت praise, بہت, colour praise, colo… | Engage with a reply and re-use their words as social proof;… |

*Used by:* Segments page cards

### 7.4  Sample comments of one segment

Segments page examples and the "browse this segment" link.

```sql
SELECT comment_text, language_type, sentiment
FROM v_comment_flat
WHERE segment = 'Price askers'
LIMIT 5;
```

**Returns 5 rows** (first 4 shown):

| comment_text | language_type | sentiment |
|---|---|---|
| قیمت بتائیں | Urdu | Neutral |
| قیمت بہت زیادہ ہے | Urdu | Negative |
| Price pls | English | Neutral |
| یہ کتنے کا ہے؟ | Urdu | Neutral |

*Used by:* Segments page, Comments page

### 7.5  Which brand drives each segment

Segment × brand cross-tab.

```sql
SELECT s.segment_name, b.brand_name, COUNT(*) AS comments
FROM comment c
JOIN segment s USING(segment_id)
JOIN post p USING(post_id) JOIN account a USING(account_id) JOIN brand b USING(brand_id)
WHERE s.segment_name LIKE 'Delivery%'
GROUP BY s.segment_id, b.brand_id
ORDER BY s.segment_name, comments DESC;
```

**Returns 12 rows** (first 4 shown):

| segment_name | brand_name | comments |
|---|---|---|
| Delivery-concerned shoppers | Zari House | 710 |
| Delivery-concerned shoppers | Noor Lawn | 315 |
| Delivery-concerned shoppers | Gulabo Prints | 304 |
| Delivery-concerned shoppers | Sitara Studio | 281 |

## 8. Question 5 – recommendations

### 8.1  Recommendations by priority

Stored with their evidence, so the page and the CSV export are a plain `SELECT`.

```sql
SELECT r.rec_id, r.priority, r.area, r.title, r.evidence, r.action, s.segment_name
FROM recommendation r
LEFT JOIN segment s USING(segment_id)
ORDER BY CASE r.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, r.rec_id
LIMIT 10;
```

**Returns 10 rows** (first 4 shown):

| rec_id | priority | area | title | evidence | action | segment_name |
|---|---|---|---|---|---|---|
| 1 | High | Content | Shift more budget and effort into Reels | After adjusting for platform norms, Reel posts have the hig… | Plan the next campaign calendar around Reel and re-purpose … | NULL |
| 2 | High | Customer service | Fix delivery complaints before they spread publicly | 5.7% of all comments are delivery complaints; Zari House is… | Assign a support owner for Zari House, answer complaints wi… | Delivery-concerned shoppers |
| 3 | High | Customer service | Capture ready-to-buy comments with a fast DM/WhatsApp flow | 1,865 comments (6.4%) explicitly ask to order or be contact… | Auto-reply with the order link/WhatsApp number and track re… | Ready-to-buy leads |
| 4 | High | Promotions | Give discount hunters a structured offer instead of ad-hoc … | 13.8% of comments ask for a discount; highest in '11.11 Sal… | Test a code-based or tiered offer (e.g. 2 suits = extra %),… | Mixed: discount hunters & price askers |

*Used by:* Recommendations page, Dashboard (High only)

### 8.2  Count by area and priority

```sql
SELECT area, priority, COUNT(*) AS recommendations FROM recommendation GROUP BY area, priority ORDER BY area, priority;
```

**Returns 9 rows** (first 4 shown):

| area | priority | recommendations |
|---|---|---|
| Campaign testing | Low | 2 |
| Campaign testing | Medium | 2 |
| Content | High | 2 |
| Content | Low | 1 |

## 9. Real data – YouTube comment sentiment

The 2,600 comments from the YouTube Comment Sentiment Analyzer live in the same tables: the video is one
`post` (`YT-UYaY2Kb_PKI`, platform *YouTube*), every comment is a `comment` row with `external_id` (YouTube comment id),
`commenter_id`, `published_at`, `like_count`, `reply_count`, `sentiment_id`, `sentiment_score` and `sentiment_confidence`.
The source row has `provenance = 'observed'` and `include_in_analysis = 0`.

### 9.1  Source and provenance

Which data is real and which is simulated.

```sql
SELECT ds.source_name, ds.provenance, ds.include_in_analysis, COUNT(DISTINCT p.post_id) AS posts, COUNT(c.comment_id) AS comments
FROM data_source ds
JOIN post p USING(source_id)
LEFT JOIN comment c USING(post_id)
GROUP BY ds.source_id;
```

**Returns 2 rows**:

| source_name | provenance | include_in_analysis | posts | comments |
|---|---|---|---|---|
| Simulated lawn-suit campaign data (generator.py) | simulated | 1 | 3000 | 29195 |
| YouTube comment sentiment analyzer export (Project 2) | observed | 0 | 1 | 2600 |

*Used by:* Method & data page, top-bar badges

### 9.2  Sentiment distribution

Should read 1,859 Negative / 366 Neutral / 375 Positive, identical to the analyzer's own `classified_comments.csv`.

```sql
SELECT s.sentiment_label AS sentiment, COUNT(*) AS comments,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS percent,
       ROUND(AVG(c.sentiment_score), 3) AS avg_score, ROUND(AVG(c.sentiment_confidence), 3) AS avg_confidence
FROM comment c JOIN sentiment s USING(sentiment_id)
WHERE c.external_id IS NOT NULL
GROUP BY s.sentiment_id
ORDER BY comments DESC;
```

**Returns 3 rows**:

| sentiment | comments | percent | avg_score | avg_confidence |
|---|---|---|---|---|
| Negative | 1859 | 71.5 | -0.718 | 0.759 |
| Positive | 375 | 14.42 | 0.591 | 0.663 |
| Neutral | 366 | 14.08 | -0.005 | 0.59 |

*Used by:* YouTube page

### 9.3  Sentiment over time (by year)

`substr(published_at, 1, 4)` takes the year from the ISO-8601 timestamp.

```sql
SELECT substr(c.published_at, 1, 4) AS year,
       SUM(s.sentiment_label = 'Negative') AS negative,
       SUM(s.sentiment_label = 'Neutral')  AS neutral,
       SUM(s.sentiment_label = 'Positive') AS positive,
       COUNT(*) AS total
FROM comment c JOIN sentiment s USING(sentiment_id)
WHERE c.external_id IS NOT NULL
GROUP BY year ORDER BY year;
```

**Returns 8 rows** (first 4 shown):

| year | negative | neutral | positive | total |
|---|---|---|---|---|
| 2019 | 78 | 16 | 31 | 125 |
| 2020 | 27 | 5 | 2 | 34 |
| 2021 | 86 | 20 | 17 | 123 |
| 2022 | 388 | 82 | 75 | 545 |

*Used by:* YouTube page

### 9.4  Sentiment-score histogram

Ten equal bins from −1 to +1 using integer arithmetic.

```sql
SELECT MIN(9, CAST((sentiment_score + 1) * 5 AS INTEGER)) AS bin,
       ROUND(-1 + MIN(9, CAST((sentiment_score + 1) * 5 AS INTEGER)) * 0.2, 1) AS from_score,
       COUNT(*) AS comments
FROM comment WHERE external_id IS NOT NULL
GROUP BY bin ORDER BY bin;
```

**Returns 10 rows** (first 4 shown):

| bin | from_score | comments |
|---|---|---|
| 0 | -1.0 | 851 |
| 1 | -0.8 | 325 |
| 2 | -0.6 | 422 |
| 3 | -0.4 | 216 |

*Used by:* YouTube page

### 9.5  Most-liked comments

Joins `commenter` for the display name.

```sql
SELECT c.like_count, c.reply_count, s.sentiment_label AS sentiment, cu.display_name AS commenter, substr(c.comment_text, 1, 90) AS comment
FROM comment c
JOIN sentiment s  USING(sentiment_id)
JOIN commenter cu USING(commenter_id)
WHERE c.external_id IS NOT NULL
ORDER BY c.like_count DESC
LIMIT 5;
```

**Returns 5 rows** (first 4 shown):

| like_count | reply_count | sentiment | commenter | comment |
|---|---|---|---|---|
| 10125 | 122 | Negative | @navylaks2 | This is the only channel that actually still shows this com… |
| 9221 | 78 | Negative | @gammaraider | Thanks Gillette, maybe now I can finally learn to live with… |
| 8136 | 86 | Negative | @Sekretariat. | A moment of silence for all the great deleted comments and … |
| 7364 | 60 | Negative | @ignaciolarat1391 | While Gilette charges double for pink razors...  Hypocrites |

*Used by:* YouTube page

### 9.6  Do negative comments get more likes?

Average and total likes by sentiment.

```sql
SELECT s.sentiment_label, COUNT(*) AS comments, ROUND(AVG(c.like_count), 1) AS avg_likes, SUM(c.like_count) AS total_likes, MAX(c.like_count) AS max_likes
FROM comment c JOIN sentiment s USING(sentiment_id)
WHERE c.external_id IS NOT NULL
GROUP BY s.sentiment_id;
```

**Returns 3 rows**:

| sentiment_label | comments | avg_likes | total_likes | max_likes |
|---|---|---|---|---|
| Positive | 375 | 72.7 | 27267 | 6655 |
| Neutral | 366 | 53.2 | 19488 | 5286 |
| Negative | 1859 | 62.6 | 116461 | 10125 |

*Used by:* YouTube page

### 9.7  Commenters who wrote more than one comment

`HAVING` filters groups; shows why `commenter` is its own table (one person, many comments).

```sql
SELECT cu.display_name, COUNT(*) AS comments, ROUND(AVG(c.sentiment_score), 2) AS avg_score
FROM comment c JOIN commenter cu USING(commenter_id)
GROUP BY cu.commenter_id
HAVING COUNT(*) > 1
ORDER BY comments DESC
LIMIT 5;
```

**Returns 5 rows** (first 4 shown):

| display_name | comments | avg_score |
|---|---|---|
| @dermotosullivan3065 | 19 | -0.64 |
| @SayWhen-st2zq | 9 | -0.22 |
| @ibrahimasscandy1849 | 9 | -0.39 |
| @Jon-q8e7g4 | 5 | -0.85 |

### 9.8  Comments about a word, by sentiment

```sql
SELECT s.sentiment_label, COUNT(*) AS mentions
FROM comment c JOIN sentiment s USING(sentiment_id)
WHERE c.external_id IS NOT NULL AND lower(c.comment_text) LIKE '%woke%'
GROUP BY s.sentiment_id;
```

**Returns 3 rows**:

| sentiment_label | mentions |
|---|---|
| Positive | 3 |
| Neutral | 1 |
| Negative | 8 |

### 9.9  Comments per month for one year

```sql
SELECT substr(published_at, 1, 7) AS month, COUNT(*) AS comments
FROM comment
WHERE external_id IS NOT NULL AND published_at >= '2022-01-01' AND published_at < '2023-01-01'
GROUP BY month ORDER BY month;
```

**Returns 12 rows** (first 4 shown):

| month | comments |
|---|---|
| 2022-01 | 13 |
| 2022-02 | 36 |
| 2022-03 | 48 |
| 2022-04 | 62 |

## 10. Adding data (INSERT)

Foreign keys are looked up with **scalar sub-selects** so you never need to remember numeric ids.
Each group below was executed inside one transaction and rolled back, so the sequence is verified but the
database is unchanged. In your own code, finish with `COMMIT` (or `conn.commit()`).
Remember `PRAGMA foreign_keys = ON;` on every connection (the app's `database.connect()` does it for you).

### 10.1  Add a new lookup value (idempotent)

`INSERT OR IGNORE` skips the row if the `UNIQUE` name already exists.

```sql
INSERT OR IGNORE INTO brand (brand_name) VALUES ('Zari House');
INSERT OR IGNORE INTO brand (brand_name) VALUES ('Nayab Threads');
INSERT OR IGNORE INTO campaign (campaign_name) VALUES ('Black Friday');
```

**Verified** (ran in a transaction, then rolled back): INSERT 0 rows; INSERT 1 row; INSERT 1 row

### 10.2  Add a brand's page on a platform (account)

The follower count belongs to the *brand + platform pair*, hence its own table.

```sql
INSERT OR IGNORE INTO brand (brand_name) VALUES ('Nayab Threads');
INSERT INTO account (brand_id, platform_id, followers)
      VALUES ((SELECT brand_id FROM brand WHERE brand_name = 'Nayab Threads'),
              (SELECT platform_id FROM platform WHERE platform_name = 'Instagram'), 150000);
```

**Verified** (ran in a transaction, then rolled back): INSERT 1 row; INSERT 1 row

### 10.3  Add a data source, a post (Table A) and its comments (Table B)

A complete manual entry: source → post → commenters → comments. The classifier fields (language, topic, sentiment, intent) are lookups chosen by name.

```sql
INSERT INTO data_source (source_name, provenance, source_url, collected_on, reuse_permission, include_in_analysis)
      VALUES ('Manual entry', 'observed', NULL, '2026-11-15', 'Own data', 1);
INSERT INTO post (post_id, account_id, campaign_id, content_type_id, category_id, source_id,
                      likes, comments_count, shares, views, days_since_post)
      VALUES ('P9001',
              (SELECT a.account_id FROM account a JOIN brand b USING(brand_id) JOIN platform pl USING(platform_id)
                WHERE b.brand_name = 'Noor Lawn' AND pl.platform_name = 'Instagram'),
              (SELECT campaign_id FROM campaign WHERE campaign_name = '12.12 Sale'),
              (SELECT content_type_id FROM content_type WHERE content_type_name = 'Reel'),
              (SELECT category_id FROM product_category WHERE category_name = 'Lawn suit'),
              (SELECT source_id FROM data_source WHERE source_name = 'Manual entry'),
              5400, 212, 130, 88000, 6);
INSERT OR IGNORE INTO commenter (display_name) VALUES ('@sana_k');
INSERT INTO comment (post_id, commenter_id, comment_text, language_id, topic_id, sentiment_id, sentiment_score, intent_id)
      VALUES ('P9001',
              (SELECT commenter_id FROM commenter WHERE display_name = '@sana_k'),
              'Price bata dein please',
              (SELECT language_id FROM language_type WHERE language_name = 'Roman Urdu'),
              (SELECT topic_id FROM topic WHERE topic_name = 'Price inquiry'),
              (SELECT sentiment_id FROM sentiment WHERE sentiment_label = 'Neutral'), 0.0,
              (SELECT intent_id FROM purchase_intent WHERE intent_label = 'Possible inquiry'));
```

**Verified** (ran in a transaction, then rolled back): INSERT 1 row; INSERT 1 row; INSERT 1 row; INSERT 1 row

*Used by:* python manage.py import

### 10.4  Bulk-copy rows from another table

`INSERT … SELECT` – e.g. archive the High-priority recommendations into a scratch table.

```sql
CREATE TEMP TABLE high_recs AS SELECT * FROM recommendation WHERE 0;
INSERT INTO high_recs SELECT * FROM recommendation WHERE priority = 'High';
```

**Verified** (ran in a transaction, then rolled back): INSERT 6 rows

### 10.5  Add a YouTube-style comment (upsert the commenter first)

`ON CONFLICT … DO NOTHING` on the unique `external_id` makes re-imports safe.

```sql
INSERT OR IGNORE INTO commenter (display_name) VALUES ('@new_viewer');
INSERT INTO comment (post_id, external_id, commenter_id, comment_text, published_at, like_count, reply_count,
                         language_id, topic_id, sentiment_id, sentiment_score, sentiment_confidence, intent_id)
      VALUES ('YT-UYaY2Kb_PKI', 'TEST_COMMENT_001',
              (SELECT commenter_id FROM commenter WHERE display_name = '@new_viewer'),
              'Great ad, well said.', '2026-11-15T10:00:00Z', 3, 0,
              (SELECT language_id FROM language_type WHERE language_name = 'English'),
              (SELECT topic_id FROM topic WHERE topic_name = 'Praise'),
              (SELECT sentiment_id FROM sentiment WHERE sentiment_label = 'Positive'), 0.8, 0.9,
              (SELECT intent_id FROM purchase_intent WHERE intent_label = 'No intent'))
      ON CONFLICT(external_id) DO NOTHING;
```

**Verified** (ran in a transaction, then rolled back): INSERT 1 row; INSERT 1 row

*Used by:* python manage.py import-youtube

## 11. Changing data (UPDATE)

### 11.1  Correct one comment's sentiment

Change the foreign key, not the text of a label. Optionally store the corrected score too.

```sql
UPDATE comment
      SET sentiment_id = (SELECT sentiment_id FROM sentiment WHERE sentiment_label = 'Positive'),
          sentiment_score = 0.6
      WHERE comment_id = 1;
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row

### 11.2  Re-label all comments of one topic

Moves every “Price concern” comment of one brand to “Price inquiry”.

```sql
UPDATE comment
      SET topic_id = (SELECT topic_id FROM topic WHERE topic_name = 'Price inquiry')
      WHERE topic_id = (SELECT topic_id FROM topic WHERE topic_name = 'Price concern')
        AND post_id IN (SELECT p.post_id FROM post p JOIN account a USING(account_id) JOIN brand b USING(brand_id)
                        WHERE b.brand_name = 'Noor Lawn');
```

**Verified** (ran in a transaction, then rolled back): UPDATE 793 rows

### 11.3  Update a follower count (one row, every post benefits)

Because followers live in `account`, one `UPDATE` corrects thousands of posts' engagement rates – the payoff of 3NF.

```sql
UPDATE account
      SET followers = followers + 50000
      WHERE brand_id    = (SELECT brand_id FROM brand WHERE brand_name = 'Noor Lawn')
        AND platform_id = (SELECT platform_id FROM platform WHERE platform_name = 'Instagram');
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row

### 11.4  Rename a brand (one row, every join follows)

No other table repeats the name, so there is nothing else to update.

```sql
UPDATE brand SET brand_name = 'Noor Lawn Studio' WHERE brand_name = 'Noor Lawn';
SELECT COUNT(*) FROM v_post_flat WHERE brand = 'Noor Lawn Studio';
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row; `COUNT(*)` → 520

### 11.5  Update post counters

Fix a post's engagement numbers after a re-scrape; `CHECK` constraints reject negative values.

```sql
UPDATE post SET likes = 6100, comments_count = 240, shares = 150 WHERE post_id = 'P0001';
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row

### 11.6  Keep `comments_count` consistent with stored comments (YouTube video)

Correlated sub-query – used by the YouTube importer.

```sql
UPDATE post
      SET comments_count = (SELECT COUNT(*) FROM comment c WHERE c.post_id = post.post_id)
      WHERE post_id LIKE 'YT-%';
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row

### 11.7  Include / exclude a data source from the analysis

The single switch that keeps YouTube out of the lawn-suit clusters. After changing it, run `python manage.py analyze`.

```sql
UPDATE data_source SET include_in_analysis = 1 WHERE source_name LIKE 'YouTube%';
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row

### 11.8  Change a recommendation's priority

```sql
UPDATE recommendation SET priority = 'Low' WHERE rec_id = 1;
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row

### 11.9  Manually assign a comment to a segment

```sql
UPDATE comment
      SET segment_id = (SELECT segment_id FROM segment WHERE segment_name = 'Price askers')
      WHERE comment_id = 2;
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row

## 12. Removing data (DELETE)

`ON DELETE CASCADE` is declared from `comment`, `segment_map_point` and `post_anomaly` towards their parent, so deleting a post removes its comments, map points and anomaly row automatically.

### 12.1  Delete one comment

```sql
DELETE FROM comment WHERE comment_id = 3;
```

**Verified** (ran in a transaction, then rolled back): DELETE 1 row

### 12.2  Delete a post and everything that depends on it (cascade)

Run it and compare the counts: the comments of the post disappear with it.

```sql
SELECT COUNT(*) AS comments_before FROM comment WHERE post_id = 'P0001';
DELETE FROM post WHERE post_id = 'P0001';
SELECT COUNT(*) AS comments_after FROM comment WHERE post_id = 'P0001';
```

**Verified** (ran in a transaction, then rolled back): `COUNT(*) AS comments_before` → 16; DELETE 1 row; `COUNT(*) AS comments_after` → 0

### 12.3  Remove commenters that no longer have comments (orphans)

Clean-up after bulk deletes.

```sql
DELETE FROM commenter
      WHERE commenter_id NOT IN (SELECT commenter_id FROM comment WHERE commenter_id IS NOT NULL);
```

**Verified** (ran in a transaction, then rolled back): DELETE 0 rows

### 12.4  Remove an entire data source

Delete children first (comments cascade from posts), then posts, then accounts that are no longer used, then the source.

```sql
DELETE FROM post WHERE source_id = (SELECT source_id FROM data_source WHERE source_name LIKE 'YouTube%');
DELETE FROM data_source WHERE source_name LIKE 'YouTube%';
SELECT COUNT(*) AS youtube_comments_left FROM comment WHERE external_id IS NOT NULL;
```

**Verified** (ran in a transaction, then rolled back): DELETE 1 row; DELETE 1 row; `COUNT(*) AS youtube_comments_left` → 0

### 12.5  Clear derived results before re-running the analysis

Exactly what `pipeline.run_analysis()` does; analysis tables can always be rebuilt.

```sql
DELETE FROM recommendation;
DELETE FROM post_anomaly;
DELETE FROM segment_map_point;
UPDATE comment SET segment_id = NULL;
DELETE FROM segment;
```

**Verified** (ran in a transaction, then rolled back): DELETE 19 rows; DELETE 84 rows; DELETE 2600 rows; UPDATE 31795 rows; DELETE 14 rows

### 12.6  Delete old comments by date

```sql
DELETE FROM comment WHERE published_at IS NOT NULL AND published_at < '2020-01-01';
```

**Verified** (ran in a transaction, then rolled back): DELETE 125 rows

## 13. Safety nets: constraints and transactions

These statements are **supposed to fail**; the error text below is the real message SQLite returned.

### 13.1  CHECK constraint – negative likes

```sql
UPDATE post SET likes = -5 WHERE post_id = 'P0002';
```

**Fails as intended:** `IntegrityError: CHECK constraint failed: likes IS NULL OR likes >= 0`

### 13.2  FOREIGN KEY – comment for a post that does not exist

Requires `PRAGMA foreign_keys = ON`.

```sql
INSERT INTO comment (post_id, comment_text, language_id, topic_id, sentiment_id, intent_id)
      VALUES ('NO-SUCH-POST', 'hello', 1, 1, 1, 1);
```

**Fails as intended:** `IntegrityError: FOREIGN KEY constraint failed`

### 13.3  UNIQUE – duplicate lookup value

```sql
INSERT INTO brand (brand_name) VALUES ('Zari House');
```

**Fails as intended:** `IntegrityError: UNIQUE constraint failed: brand.brand_name`

### 13.4  Restricting a delete – brand still in use

A lookup row that is referenced cannot be deleted.

```sql
DELETE FROM brand WHERE brand_name = 'Zari House';
```

**Fails as intended:** `IntegrityError: FOREIGN KEY constraint failed`

### 13.5  Transaction pattern

All-or-nothing: either every statement applies or none (`ROLLBACK`). Shown here with `SAVEPOINT`.

```sql
SAVEPOINT demo;
UPDATE post SET likes = likes + 1 WHERE post_id = 'P0003';
DELETE FROM comment WHERE post_id = 'P0003';
ROLLBACK TO demo;
RELEASE demo;
```

**Verified** (ran in a transaction, then rolled back): UPDATE 1 row; DELETE 16 rows

## 14. Integrity checks, performance and maintenance

### 14.1  Foreign-key and integrity check

Both should return nothing / `ok`.

```sql
PRAGMA foreign_key_check;
```

**Returns 0 rows**

### 14.2  Comments whose post is missing (orphans)

Should be 0.

```sql
SELECT COUNT(*) AS orphan_comments FROM comment c LEFT JOIN post p USING(post_id) WHERE p.post_id IS NULL;
```

**Returns 1 row**:

| orphan_comments |
|---|
| 0 |

### 14.3  Duplicate YouTube comment ids

Should return no rows (`external_id` is UNIQUE).

```sql
SELECT external_id, COUNT(*) FROM comment WHERE external_id IS NOT NULL GROUP BY external_id HAVING COUNT(*) > 1;
```

**Returns 0 rows**

### 14.4  Row counts of every table

```sql
SELECT 'brand' AS tbl, COUNT(*) AS n FROM brand UNION ALL SELECT 'platform', COUNT(*) FROM platform
UNION ALL SELECT 'campaign', COUNT(*) FROM campaign UNION ALL SELECT 'content_type', COUNT(*) FROM content_type
UNION ALL SELECT 'account', COUNT(*) FROM account UNION ALL SELECT 'data_source', COUNT(*) FROM data_source
UNION ALL SELECT 'post', COUNT(*) FROM post UNION ALL SELECT 'commenter', COUNT(*) FROM commenter
UNION ALL SELECT 'comment', COUNT(*) FROM comment UNION ALL SELECT 'segment', COUNT(*) FROM segment
UNION ALL SELECT 'post_anomaly', COUNT(*) FROM post_anomaly UNION ALL SELECT 'recommendation', COUNT(*) FROM recommendation;
```

**Returns 12 rows** (first 4 shown):

| tbl | n |
|---|---|
| brand | 7 |
| platform | 4 |
| campaign | 6 |
| content_type | 7 |

### 14.5  Is an index used?

`EXPLAIN QUERY PLAN` shows `SEARCH … USING INDEX ix_comment_post` rather than a full scan.

```sql
EXPLAIN QUERY PLAN SELECT * FROM comment WHERE post_id = 'P0001';
```

**Returns 1 row**:

| id | parent | notused | detail |
|---|---|---|---|
| 3 | 0 | 0 | SEARCH comment USING INDEX ix_comment_post (post_id=?) |

### 14.6  List the schema

```sql
SELECT type, name FROM sqlite_master WHERE type IN ('table','view','index') AND name NOT LIKE 'sqlite_%' ORDER BY type, name LIMIT 12;
```

**Returns 12 rows** (first 4 shown):

| type | name |
|---|---|
| index | ix_comment_commenter |
| index | ix_comment_post |
| index | ix_comment_published |
| index | ix_comment_seg |

## 15. Using the database from Python

### Plain `sqlite3` with parameters (never build SQL with string concatenation)

```python
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
```

Output:

```text
[{'post_id': 'P0412', 'likes': 362586}, {'post_id': 'P1524', 'likes': 258041}, {'post_id': 'P1453', 'likes': 203187}]
```

### Load query results straight into pandas

```python
import sqlite3, pandas as pd
conn = sqlite3.connect("data/campaign.db")
df = pd.read_sql_query("""
    SELECT topic, sentiment, COUNT(*) AS n
    FROM v_comment_flat
    WHERE segment_id IS NOT NULL
    GROUP BY topic, sentiment""", conn)
print(df.pivot(index="topic", columns="sentiment", values="n").head())
```

Output:

```text
sentiment           Negative  Neutral  Positive
topic                                          
Availability             6.0   3760.0      90.0
Delivery complaint    1651.0      NaN       NaN
Delivery inquiry         6.0   2125.0      64.0
Discount request         NaN   3978.0      57.0
Fabric quality           NaN   1668.0       NaN
```

### Use the project's own helpers (read-only connection, same code the web app uses)

```python
from campaign_engine import database as db
print(db.query("SELECT segment_name, COUNT(*) AS n FROM comment JOIN segment USING(segment_id) GROUP BY 1 ORDER BY n DESC LIMIT 3"))
posts, comments = db.frames()          # cached DataFrames with engagement_rate, er_index ... derived
print(posts[["post_id", "engagement_rate"]].head(3))
```

Output:

```text
[{'segment_name': 'Price askers', 'n': 3603}, {'segment_name': 'Discount hunters', 'n': 3433}, {'segment_name': 'Availability seekers', 'n': 2886}]
  post_id  engagement_rate
0   P0001         0.319707
1   P0002         0.425211
2   P0003         1.337801
```

### Add real data with the command line

```bash
# YouTube Comment Sentiment Analyzer output  ->  post + comment rows  (safe to re-run)
python manage.py import-youtube --csv data/youtube/youtube_classified_comments.csv

# real lawn-suit posts + comments from your own CSV files
python manage.py import --posts my_posts.csv --comments my_comments.csv --source "Public posts, Nov 2026"

# rebuild clustering, anomalies and recommendations after changing data
python manage.py analyze
```

## 16. Which page runs which query

| Page | URL | Main queries |
|---|---|---|
| Dashboard | `/` | 3.1, 4.1, 5.1, 6.1, 7.1, 8.1 |
| 1 · What attracts attention? | `/content` | 4.1 – 4.4 |
| 2 · What does the audience want? | `/audience` | 5.1 – 5.7 |
| 3 · What is unusual? | `/anomalies` | 6.1 – 6.4 |
| 4 · Audience segments | `/segments` | 7.1 – 7.5 |
| 5 · Recommendations | `/recommendations` | 8.1, 8.2 |
| YouTube sentiment (real data) | `/youtube` | 9.1 – 9.9 |
| Posts / Post detail | `/posts`, `/posts/<id>` | 3.1 – 3.5 |
| Comments | `/comments` | 5.5, 9.5 |
| Database & SQL console | `/database` | any `SELECT` from this guide |
| CSV exports | `/export/<posts|comments|anomalies|recommendations>.csv` | views `v_post_flat`, `v_comment_flat` |

## 17. Tips and cautions

* **Never concatenate user input into SQL** – use `?` placeholders (section 15).
* **Back up before bulk changes:** copy `data/campaign.db`, or `sqlite3 data/campaign.db ".backup backup.db"`.
* After changing posts, comments or `include_in_analysis`, run `python manage.py analyze` so segments, anomalies and recommendations match the data.
* `python manage.py setup` rebuilds the whole database (simulated data + YouTube import + analysis) from scratch.
* The 2,600 YouTube comments include commenters' public display names; do not publish the database without checking YouTube's terms and privacy expectations.
* Regenerate this guide after schema changes: `python tools/build_query_docs.py`.
