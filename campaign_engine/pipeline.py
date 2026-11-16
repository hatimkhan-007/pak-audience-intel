"""Build / refresh the database: load data -> classify comments -> cluster -> anomalies -> recommendations."""
from __future__ import annotations
import time
from pathlib import Path
import joblib
import numpy as np
import pandas as pd

from . import config, database as db, nlp, analytics, generator


def _log(msg, verbose=True):
    if verbose:
        print(f"  • {msg}", flush=True)


# ---------------------------------------------------------------- lookups
def seed_lookups(conn):
    for lang in nlp.LANGUAGES: db.get_or_create(conn, "language_type", "language_id", "language_name", lang)
    for s in nlp.SENTIMENTS: db.get_or_create(conn, "sentiment", "sentiment_id", "sentiment_label", s)
    for i in nlp.INTENTS: db.get_or_create(conn, "purchase_intent", "intent_id", "intent_label", i)
    for t, theme in nlp.TOPICS: db.get_or_create(conn, "topic", "topic_id", "topic_name", t, theme=theme)
    conn.commit()


def _ids(conn, table, id_col, name_col):
    return {r[1]: r[0] for r in conn.execute(f"SELECT {id_col},{name_col} FROM {table}")}


# ---------------------------------------------------------------- posts
def insert_posts(conn, posts: pd.DataFrame, source_id: int) -> int:
    n = 0
    for col, table, idc, namec in [("brand", "brand", "brand_id", "brand_name"),
                                   ("platform", "platform", "platform_id", "platform_name"),
                                   ("campaign", "campaign", "campaign_id", "campaign_name"),
                                   ("content_type", "content_type", "content_type_id", "content_type_name"),
                                   ("product_category", "product_category", "category_id", "category_name")]:
        for v in posts[col].dropna().unique():
            db.get_or_create(conn, table, idc, namec, str(v))
    B = _ids(conn, "brand", "brand_id", "brand_name"); PL = _ids(conn, "platform", "platform_id", "platform_name")
    CA = _ids(conn, "campaign", "campaign_id", "campaign_name"); CT = _ids(conn, "content_type", "content_type_id", "content_type_name")
    PC = _ids(conn, "product_category", "category_id", "category_name")
    has_f = "followers" in posts.columns
    acc = {}
    for _, r in posts.drop_duplicates(["brand", "platform"]).iterrows():
        f = int(r["followers"]) if has_f and pd.notna(r["followers"]) else None
        row = conn.execute("SELECT account_id FROM account WHERE brand_id=? AND platform_id=?", (B[r["brand"]], PL[r["platform"]])).fetchone()
        if row:
            acc[(r["brand"], r["platform"])] = row[0]
        else:
            cur = conn.execute("INSERT INTO account(brand_id,platform_id,followers) VALUES (?,?,?)", (B[r["brand"]], PL[r["platform"]], f))
            acc[(r["brand"], r["platform"])] = cur.lastrowid
    def nz(v): return None if pd.isna(v) else int(v)
    rows = [(r.post_id, acc[(r.brand, r.platform)], CA[r.campaign], CT[r.content_type], PC[r.product_category], source_id,
             nz(r.likes), int(r.comments_count), nz(r.shares), nz(r.views), nz(r.days_since_post))
            for r in posts.itertuples()]
    conn.executemany("INSERT INTO post(post_id,account_id,campaign_id,content_type_id,category_id,source_id,likes,comments_count,shares,views,days_since_post) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


# ---------------------------------------------------------------- comments
_OPTIONAL = ("external_id", "commenter", "published_at", "like_count", "reply_count", "sentiment_score", "sentiment_confidence")


def _opt(r, col):
    v = getattr(r, col, None)
    return None if v is None or (isinstance(v, float) and np.isnan(v)) else v


def insert_comments(conn, comments: pd.DataFrame) -> pd.DataFrame:
    """Classify (unless labels supplied) and insert. Returns the analysed frame.

    Required columns: post_id, comment_text.
    Optional: language_type, topic, sentiment, purchase_intent (override the classifier) and
              external_id, commenter, published_at, like_count, reply_count,
              sentiment_score, sentiment_confidence (stored as given)."""
    L = _ids(conn, "language_type", "language_id", "language_name"); S = _ids(conn, "sentiment", "sentiment_id", "sentiment_label")
    I = _ids(conn, "purchase_intent", "intent_id", "intent_label"); T = _ids(conn, "topic", "topic_id", "topic_name")
    people = _ids(conn, "commenter", "commenter_id", "display_name")
    lookup = {"language_type": L, "topic": T, "sentiment": S, "purchase_intent": I}
    rows, out = [], []
    for r in comments.itertuples():
        a = nlp.analyze(r.comment_text)
        for col, ids in lookup.items():
            v = _opt(r, col)
            if v is not None and str(v) in ids:
                a[col] = str(v)
        score = _opt(r, "sentiment_score")
        score = float(score) if score is not None else a["sentiment_score"]
        who = _opt(r, "commenter")
        if who is not None and who not in people:
            people[who] = db.get_or_create(conn, "commenter", "commenter_id", "display_name", str(who))
        n = lambda v: None if v is None else int(v)
        conf = _opt(r, "sentiment_confidence")
        rows.append((r.post_id, _opt(r, "external_id"), people.get(who), r.comment_text, _opt(r, "published_at"),
                     n(_opt(r, "like_count")), n(_opt(r, "reply_count")),
                     L[a["language_type"]], T[a["topic"]], S[a["sentiment"]], score, None if conf is None else float(conf), I[a["purchase_intent"]]))
        out.append(a)
    conn.executemany("""INSERT INTO comment(post_id,external_id,commenter_id,comment_text,published_at,like_count,reply_count,
                        language_id,topic_id,sentiment_id,sentiment_score,sentiment_confidence,intent_id)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    conn.commit()
    return pd.DataFrame(out)


# ---------------------------------------------------------------- analysis
def _read(conn):
    """Only sources flagged include_in_analysis=1 take part in clustering / anomalies / recommendations."""
    posts = db._derive_posts(pd.read_sql_query("SELECT * FROM v_post_flat WHERE include_in_analysis = 1", conn))
    comments = pd.read_sql_query("SELECT * FROM v_comment_flat", conn)
    comments = comments.merge(posts[["post_id", "brand", "platform", "campaign", "content_type"]], on="post_id", how="inner")
    return posts, comments


def run_analysis(conn, seed=config.SEED, verbose=True, model_path=None):
    model_path = model_path or config.MODEL_PATH
    for t in ("recommendation", "post_anomaly", "segment_map_point"):
        conn.execute(f"DELETE FROM {t}")
    conn.execute("UPDATE comment SET segment_id=NULL"); conn.execute("DELETE FROM segment"); conn.commit()
    posts, comments = _read(conn)

    t0 = time.time(); _log("clustering comments into audience segments ...", verbose)
    labels, segs, scores, k, idx, emb, model = analytics.segment_comments(comments, seed=seed)
    seg_id = {}
    for s in segs:
        cur = conn.execute("INSERT INTO segment(segment_name,description,suggested_action,top_terms) VALUES (?,?,?,?)",
                           (s["segment_name"], s["description"], s["suggested_action"], s["top_terms"]))
        seg_id[s["cluster"]] = cur.lastrowid; s["segment_id"] = cur.lastrowid
    conn.executemany("UPDATE comment SET segment_id=? WHERE comment_id=?",
                     [(seg_id[int(c)], int(cid)) for c, cid in zip(labels, comments["comment_id"])])
    cids = comments["comment_id"].to_numpy()[idx]
    conn.executemany("INSERT INTO segment_map_point(comment_id,x,y) VALUES (?,?,?)",
                     [(int(c), float(x), float(y)) for c, (x, y) in zip(cids, emb)])
    model["segment_ids"] = [seg_id[c] for c in sorted(seg_id, key=lambda c: model["order"][c])]
    joblib.dump(model, model_path)
    conn.execute("INSERT OR REPLACE INTO run_metadata VALUES ('k', ?)", (str(k),))
    conn.execute("INSERT OR REPLACE INTO run_metadata VALUES ('silhouette_scores', ?)", (";".join(f"{a}:{b:.4f}" for a, b in scores.items()),))
    conn.commit()
    _log(f"{k} segments (silhouette {scores[k]:.3f}) in {time.time()-t0:.0f}s", verbose)

    posts, comments = _read(conn)
    _log("detecting anomalies ...", verbose)
    an = analytics.detect_anomalies(posts, comments, seed=seed)
    conn.executemany("INSERT INTO post_anomaly VALUES (?,?,?,?)", an.itertuples(index=False, name=None))
    conn.commit()
    _log(f"{len(an)} anomalous posts flagged", verbose)

    posts = posts.merge(an[["post_id", "anomaly_score", "anomaly_type", "reason"]], on="post_id", how="left")
    seg_df = pd.DataFrame([{k_: s[k_] for k_ in ("segment_id", "segment_name", "dominant_topic", "size")} for s in segs])
    recs = analytics.build_recommendations(posts, comments, seg_df)
    conn.executemany("INSERT INTO recommendation(area,priority,title,evidence,action,segment_id) VALUES (?,?,?,?,?,?)",
                     [(r["area"], r["priority"], r["title"], r["evidence"], r["action"], r["segment_id"]) for r in recs])
    conn.execute("INSERT OR REPLACE INTO run_metadata VALUES ('analysed_at', datetime('now'))")
    conn.commit()
    _log(f"{len(recs)} recommendations generated", verbose)
    return dict(k=k, silhouette=scores[k], anomalies=len(an), recommendations=len(recs))


# ---------------------------------------------------------------- full build
def build(n_posts=config.N_POSTS, seed=config.SEED, path=None, verbose=True):
    path = Path(path or config.DB_PATH); path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists(): path.unlink()
    conn = db.connect(path); db.init_schema(conn); seed_lookups(conn)
    _log(f"generating {n_posts} simulated posts + comments ...", verbose)
    posts, comments, truth, kinds = generator.generate(n_posts, seed)
    cur = conn.execute("INSERT INTO data_source(source_name,provenance,source_url,collected_on,reuse_permission) VALUES (?,?,?,?,?)",
                       ("Simulated lawn-suit campaign data (generator.py)", "simulated", None, config.COLLECTION_DATE,
                        "Synthetic - no third-party data; free to reuse for the class demonstration"))
    src = cur.lastrowid
    _log(f"inserted {insert_posts(conn, posts, src)} posts", verbose)
    an = insert_comments(conn, comments)
    _log(f"inserted and classified {len(an):,} comments", verbose)
    cid = np.arange(1, len(comments) + 1)
    tr = pd.DataFrame({"comment_id": cid, "true_topic": truth["true_topic"].values, "predicted_topic": an["topic"].values})
    tr.to_csv(config.TRUTH_PATH, index=False)
    acc = float((tr["true_topic"] == tr["predicted_topic"]).mean())
    conn.execute("INSERT OR REPLACE INTO run_metadata VALUES ('topic_accuracy_vs_simulated_labels', ?)", (f"{acc:.4f}",))
    conn.execute("INSERT OR REPLACE INTO run_metadata VALUES ('seed', ?)", (str(seed),)); conn.commit()
    _log(f"topic classifier agreement with generator labels: {acc:.1%}", verbose)
    from . import importer
    yt = Path(config.YOUTUBE_CSV)
    if yt.exists():
        res = importer.import_youtube(yt, conn=conn)
        _log(f"imported {res['comments_added']:,} real YouTube comments ({res['video_id']})", verbose)
    summary = run_analysis(conn, seed, verbose)
    conn.close()
    return summary
