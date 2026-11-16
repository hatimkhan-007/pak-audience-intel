# Pakistan Social Audience & Campaign Intelligence Engine

Project 3 – a small Python web application that groups similar audience behaviour, finds unusual
campaign patterns and turns the findings into marketing actions for a Lahore-based lawn-suit brand
running Instagram, TikTok and Facebook campaigns (11.11 / 12.12, Eid, …).

**Stack:** Python 3.10+ · Flask · SQLite (3NF) · pandas · scikit-learn · Chart.js (bundled, works offline)

## Run it

```bash
python -m venv venv
venv\Scripts\activate            # Windows   (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt
python manage.py run             # → http://127.0.0.1:5000   (database is already included)
```

Rebuild everything from scratch (about 25 s): `python manage.py setup`
Run the tests: `python -m pytest -q`

## The five marketing questions (one page each)

| # | Question | Page | How it is answered |
|---|----------|------|--------------------|
| 1 | Which content attracts attention? | `/content` | Likes / comments / shares / views / engagement rate by format, platform, campaign and brand; platform-adjusted index; content × platform heat-map |
| 2 | What does the audience want? | `/audience` | Every comment → language, topic (price, fabric, sizing, delivery, discount, availability, purchase intent…), sentiment, intent |
| 3 | Which patterns are unusual? | `/anomalies` | Robust z-scores vs comparable posts (same brand + platform + format) → Isolation Forest; each flag has a plain-English reason |
| 4 | Which audience needs should the brand address? | `/segments` | TF-IDF → SVD → **K-Means** on comments (k chosen by silhouette); named segments (discount hunters, delivery-concerned shoppers, availability seekers…) with actions |
| 5 | What should the team do next? | `/recommendations` | Evidence-based recommendations for content, promotions, customer service and campaign testing |

Extras: **real YouTube comment sentiment page** (`/youtube`), dashboard with filters (platform / brand / campaign), posts & comments explorers with search, sort,
pagination and CSV export, post detail pages, a live **comment classifier**, an **ER diagram + 3NF walkthrough +
read-only SQL console** (`/database`), light/dark mode, responsive layout, empty-state and error pages.

## Database (1NF → 2NF → 3NF)

19 tables + 2 read-only views (`schema.sql`): lookup tables (`brand, platform, campaign, content_type,
product_category, language_type, topic, sentiment, purchase_intent`), `data_source` (observed vs simulated),
`account` (followers depend on brand + platform), `commenter`, **Table A** `post`, **Table B** `comment`, and analysis outputs
(`segment, segment_map_point, post_anomaly, recommendation, run_metadata`).
Derived values (engagement rate, peer groups, totals) are never stored. The front end reads everything from the DB.

## Your YouTube comments are in the database

The 2,600 comments from the YouTube Comment Sentiment Analyzer (Project 2) are loaded as **real (`observed`) data**:
one `post` row for the video and 2,600 `comment` rows with the analyzer's sentiment label, score and confidence, like and
reply counts, timestamp and commenter (separate `commenter` table, 3NF). The data source is flagged
`include_in_analysis = 0`, so a razor ad cannot distort the lawn-suit segments, anomalies or recommendations; it has its own
page (`/youtube`) and appears in the explorers, SQL console and exports.
`python manage.py import-youtube --csv <file>` loads another export (re-runs are safe).

All SQL for retrieving, adding, changing and deleting data is documented and verified in
**`docs/DATABASE_QUERIES.md`** (also `.docx`).

## Data – please read

The lawn-suit data (3,000 posts, 29,195 comments, English / Roman Urdu / Urdu) is **simulated**; brand names are
fictional and none of the numbers are real measurements. It is flagged `provenance = simulated` everywhere in the
app. To use real, permitted data:

```bash
python manage.py import --posts my_posts.csv --comments my_comments.csv \
       --source "Public posts, Nov 2026" --url https://example.com --permission "Own data"
```
posts.csv: `post_id, brand, platform, campaign, content_type, product_category, likes, comments_count, days_since_post`
(+ optional `shares, views, followers`). comments.csv: `post_id, comment_text`. Real rows are stored as
`observed`, comments are classified automatically and the clustering / anomaly / recommendation steps re-run.
Follow each platform's terms; do not assume all comments or analytics are downloadable.

## Layout

```
manage.py                  setup / run / analyze / import
campaign_engine/
  schema.sql               3NF schema + views
  generator.py             simulated Table A + Table B
  nlp.py                   language, topic, sentiment, intent (EN / Roman Urdu / Urdu)
  analytics.py             clustering, anomaly detection, recommendations
  pipeline.py              build DB → classify → analyse → store
  importer.py              CSV import for real data + YouTube analyzer import
  webapp.py + templates/ + static/
data/campaign.db           ready-to-use database (+ model, ground-truth file for evaluation)
tools/build_query_docs.py  regenerates docs/DATABASE_QUERIES.md (executes every query)
docs/                      DATABASE_QUERIES.md / .docx, COMMITS.md
tests/                     56 tests (NLP, 3NF integrity, YouTube import, pipeline, every route, SQL-console safety)
```

## Known limitations
Rule-based NLP can miss sarcasm and new slang (≈93 % agreement with the simulator's hidden labels); only a sample
of comments per post is stored; anomalies are statistical flags to investigate, not verdicts; segment and
recommendation findings should be validated with A/B tests.
