"""Flask front-end: reads everything from the SQLite database."""
from __future__ import annotations
import io
import math
import re
import sqlite3
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from flask import Flask, Response, abort, jsonify, render_template, request, url_for

from . import config, database as db, nlp, analytics

FILTER_KEYS = ("platform", "brand", "campaign")
PER_PAGE = 25


def r(x, n=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return None
    return round(float(x), n)


def create_app():
    app = Flask(__name__)
    app.json.sort_keys = False

    # ------------------------------------------------------------ helpers
    def data(scope="analysis"):
        """scope='analysis' -> only sources used for the lawn-suit engine; 'all' -> everything incl. YouTube."""
        if not config.DB_PATH.exists():
            from . import pipeline
            pipeline.build(verbose=False)
        posts, comments = db.frames()
        if scope == "analysis":
            posts = posts[posts["include_in_analysis"] == 1]
            comments = comments[comments["post_id"].isin(posts["post_id"])]
        return posts, comments

    ALL_SCOPE = {"posts_list", "post_detail", "comments_list", "export", "youtube"}

    def filters():
        return {k: request.args.get(k, "") for k in FILTER_KEYS if request.args.get(k)}

    def apply(posts, comments, f):
        for k, v in f.items():
            posts = posts[posts[k] == v]
            comments = comments[comments[k] == v]
        return posts, comments

    def meta():
        return {x["key"]: x["value"] for x in db.query("SELECT key,value FROM run_metadata")}

    @app.context_processor
    def inject():
        posts, _ = data("all" if request.endpoint in ALL_SCOPE else "analysis")
        f = filters()
        opts = {k: sorted(posts[k].dropna().unique().tolist()) for k in FILTER_KEYS}
        return dict(filters=f, filter_opts=opts, fq=lambda ep, **kw: url_for(ep, **{**f, **kw}),
                    sources=db.query("SELECT provenance, COUNT(*) n FROM data_source ds JOIN post p USING(source_id) GROUP BY provenance"))

    @app.template_filter("num")
    def num(x):
        try:
            return f"{int(round(float(x))):,}"
        except (TypeError, ValueError):
            return "—"

    @app.template_filter("compact")
    def compact(x):
        try:
            x = float(x)
        except (TypeError, ValueError):
            return "—"
        for lim, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
            if abs(x) >= lim:
                return f"{x/lim:.1f}{suf}"
        return f"{x:.0f}"

    @app.template_filter("pct")
    def pct(x, d=1):
        return "—" if x is None or pd.isna(x) else f"{x*100:.{d}f}%"

    @app.template_filter("mark")
    def mark(text, q):
        from markupsafe import Markup, escape
        t = str(escape(text))
        if q:
            t = re.sub(f"({re.escape(str(escape(q)))})", r"<mark>\1</mark>", t, flags=re.I)
        return Markup(t)

    def paginate(df, page):
        pages = max(1, math.ceil(len(df) / PER_PAGE))
        page = min(max(page, 1), pages)
        return df.iloc[(page - 1) * PER_PAGE: page * PER_PAGE], page, pages

    def args_page():
        try:
            return int(request.args.get("page", 1))
        except ValueError:
            return 1

    def qs_without(*drop, **extra):
        d = {k: v for k, v in request.args.items() if k not in drop and v}
        d.update(extra)
        return d

    app.jinja_env.globals["qs_without"] = qs_without

    def topic_share(comments):
        vc = comments["topic"].value_counts()
        return vc, vc / max(len(comments), 1)

    # ------------------------------------------------------------ dashboard
    @app.route("/")
    def dashboard():
        posts, comments = apply(*data(), filters())
        ready = posts[posts["days_since_post"] >= 3]
        vc, share = topic_share(comments)
        by_ct = ready.groupby("content_type")["er_index"].median().sort_values(ascending=False)
        seg = comments.groupby("segment").size().sort_values(ascending=False)
        sent = comments["sentiment"].value_counts()
        kpis = dict(posts=len(posts), comments=len(comments),
                    interactions=int(posts["interactions"].sum()), er=r(ready["engagement_rate"].median()),
                    anomalies=int(posts["anomaly_type"].notna().sum()),
                    segments=int(seg.size), top_topic=vc.index[0] if len(vc) else "—",
                    neg=r((comments["sentiment"] == "Negative").mean() * 100, 1) if len(comments) else None)
        recs = db.query("SELECT * FROM recommendation WHERE priority='High' ORDER BY rec_id LIMIT 4")
        top_an = posts[posts["anomaly_type"].notna()].sort_values("anomaly_score", ascending=False).head(5)
        charts = dict(
            content=dict(type="bar", data=dict(labels=by_ct.index.tolist(), datasets=[dict(label="Engagement index (1.0 = platform norm)", data=[r(v) for v in by_ct.values])]),
                         options=dict(indexAxis="y", plugins=dict(legend=dict(display=False)), colorByPoint=True)),
            topics=dict(type="bar", data=dict(labels=vc.index.tolist(), datasets=[dict(label="Comments", data=vc.values.tolist())]),
                        options=dict(indexAxis="y", plugins=dict(legend=dict(display=False)), colorByPoint=True)),
            segments=dict(type="bar", data=dict(labels=seg.index.tolist(), datasets=[dict(label="Comments", data=seg.values.tolist())]),
                          options=dict(indexAxis="y", plugins=dict(legend=dict(display=False)), colorByPoint=True)),
            sentiment=dict(type="doughnut", data=dict(labels=sent.index.tolist(), datasets=[dict(data=sent.values.tolist(),
                           backgroundColor=[{"Positive": "#2f9e6e", "Neutral": "#9aa5b1", "Negative": "#d6455d"}[s] for s in sent.index])]),
                           options=dict(plugins=dict(legend=dict(position="bottom")))),
        )
        return render_template("dashboard.html", page="dashboard", kpis=kpis, charts=charts, recs=recs,
                               top_an=top_an.to_dict("records"), meta=meta())

    # ------------------------------------------------------------ Q1 content
    @app.route("/content")
    def content():
        posts, _ = apply(*data(), filters())
        P = posts[posts["days_since_post"] >= 3]
        metrics = {"Engagement rate (% of followers)": ("engagement_rate", "median"),
                   "Platform-adjusted index": ("er_index", "median"),
                   "Likes": ("likes", "mean"), "Comments": ("comments_count", "mean"),
                   "Shares": ("shares", "mean"), "Views": ("views", "mean")}

        def series(group):
            out = {}
            for label, (col, fn) in metrics.items():
                s = P.groupby(group)[col].agg(fn).sort_values(ascending=False)
                out[label] = s
            return out

        def bar_payload(group):
            s = series(group)
            order = s["Platform-adjusted index"].index.tolist()
            return dict(labels=order, metrics={k: [r(v.get(o)) for o in order] for k, v in s.items()},
                        n=[int((P[group] == o).sum()) for o in order])

        ct_platform = P.pivot_table(index="content_type", columns="platform", values="engagement_rate", aggfunc="median")
        ct_platform = ct_platform.loc[P.groupby("content_type")["er_index"].median().sort_values(ascending=False).index]
        grouped = dict(type="bar", data=dict(labels=ct_platform.index.tolist(),
                       datasets=[dict(label=c, data=[r(v) for v in ct_platform[c].values]) for c in ct_platform.columns]),
                       options=dict(scales=dict(y=dict(title=dict(display=True, text="Median engagement rate %")))))
        vmax = np.nanmax(ct_platform.values) if ct_platform.size else 1
        heat = [dict(label=i, cells=[dict(v=r(ct_platform.loc[i, c]), a=(0 if pd.isna(ct_platform.loc[i, c]) else 0.12 + 0.75 * ct_platform.loc[i, c] / vmax),
                                          n=int(((P.content_type == i) & (P.platform == c)).sum())) for c in ct_platform.columns]) for i in ct_platform.index]
        top_posts = P.sort_values("engagement_rate", ascending=False).head(10)
        stats = P.groupby("content_type").agg(posts=("post_id", "size"), er=("engagement_rate", "median"), idx=("er_index", "median"),
                                              likes=("likes", "mean"), comments=("comments_count", "mean"),
                                              shares=("shares", "mean"), views=("views", "mean")).sort_values("idx", ascending=False)
        return render_template("content.html", page="content", ct=bar_payload("content_type"), camp=bar_payload("campaign"),
                               brand=bar_payload("brand"), plat=bar_payload("platform"), grouped=grouped,
                               heat=heat, heat_cols=ct_platform.columns.tolist(), top_posts=top_posts.to_dict("records"),
                               stats=stats.reset_index().to_dict("records"), n=len(P))

    # ------------------------------------------------------------ Q2 audience
    @app.route("/audience")
    def audience():
        posts, comments = apply(*data(), filters())
        vc, share = topic_share(comments)
        order = vc.index.tolist()
        bp = pd.crosstab(comments["platform"], comments["topic"], normalize="index")[order] * 100 if len(comments) else pd.DataFrame()
        bs = pd.crosstab(comments["topic"], comments["sentiment"]).reindex(order).fillna(0) if len(comments) else pd.DataFrame()
        lang = comments["language_type"].value_counts()
        intent = comments["purchase_intent"].value_counts()
        cities = pd.Series(re.findall("|".join(nlp.CITIES), " ".join(comments["comment_text"].str.lower()))).value_counts().head(10)
        themes = comments["theme"].value_counts()
        col = {"Positive": "#2f9e6e", "Neutral": "#9aa5b1", "Negative": "#d6455d"}
        charts = dict(
            topics=dict(type="bar", data=dict(labels=order, datasets=[dict(label="Comments", data=vc.values.tolist())]),
                        options=dict(indexAxis="y", plugins=dict(legend=dict(display=False)), colorByPoint=True)),
            by_platform=dict(type="bar", data=dict(labels=bp.index.tolist(), datasets=[dict(label=t, data=[r(v, 1) for v in bp[t].values]) for t in bp.columns]),
                             options=dict(scales=dict(x=dict(stacked=True), y=dict(stacked=True, max=100, title=dict(display=True, text="% of platform's comments"))),
                                          plugins=dict(legend=dict(position="bottom")))),
            sentiment=dict(type="bar", data=dict(labels=bs.index.tolist(), datasets=[dict(label=s, data=bs[s].astype(int).tolist(), backgroundColor=col[s]) for s in ["Positive", "Neutral", "Negative"] if s in bs]),
                           options=dict(indexAxis="y", scales=dict(x=dict(stacked=True), y=dict(stacked=True)), plugins=dict(legend=dict(position="bottom")))),
            language=dict(type="doughnut", data=dict(labels=lang.index.tolist(), datasets=[dict(data=lang.values.tolist())]), options=dict(plugins=dict(legend=dict(position="bottom")))),
            intent=dict(type="doughnut", data=dict(labels=intent.index.tolist(), datasets=[dict(data=intent.values.tolist())]), options=dict(plugins=dict(legend=dict(position="bottom")))),
            cities=dict(type="bar", data=dict(labels=[c.title() for c in cities.index], datasets=[dict(label="Mentions", data=cities.values.tolist())]),
                        options=dict(plugins=dict(legend=dict(display=False)), colorByPoint=True)),
        )
        examples = {t: comments[comments["topic"] == t].drop_duplicates("comment_text")["comment_text"].head(4).tolist() for t in order}
        rows = [dict(topic=t, n=int(vc[t]), share=float(share[t]), theme=comments.loc[comments.topic == t, "theme"].iloc[0],
                     neg=float((comments.loc[comments.topic == t, "sentiment"] == "Negative").mean()), ex=examples[t]) for t in order]
        return render_template("audience.html", page="audience", charts=charts, rows=rows, total=len(comments), themes=themes.to_dict())

    # ------------------------------------------------------------ Q4 segments
    @app.route("/segments")
    def segments():
        posts, comments = apply(*data(), filters())
        segs = db.query("SELECT * FROM segment")
        sizes = comments.groupby("segment_id").size()
        tot = max(len(comments), 1)
        pts = db.query("SELECT cm.comment_id, cm.segment_id, x, y FROM segment_map_point m JOIN comment cm USING(comment_id)")
        keep = set(comments["comment_id"])
        pts = [p for p in pts if p["comment_id"] in keep]
        cards = []
        for s in sorted(segs, key=lambda s: -int(sizes.get(s["segment_id"], 0))):
            sub = comments[comments["segment_id"] == s["segment_id"]]
            if sub.empty:
                continue
            tp = sub["topic"].value_counts(normalize=True)
            cards.append(dict(**s, n=len(sub), share=len(sub) / tot, purity=float(tp.iloc[0]), dominant=tp.index[0],
                              lang=sub["language_type"].value_counts(normalize=True).head(2).to_dict(),
                              top_brand=sub["brand"].value_counts(normalize=True).head(1).to_dict(),
                              top_platform=sub["platform"].value_counts(normalize=True).head(1).to_dict(),
                              neg=float((sub["sentiment"] == "Negative").mean()),
                              samples=sub.drop_duplicates("comment_text").sample(min(5, sub["comment_text"].nunique()), random_state=1)["comment_text"].tolist()))
        names = {s["segment_id"]: s["segment_name"] for s in segs}
        scatter = dict(type="scatter", data=dict(datasets=[dict(label=c["segment_name"], data=[dict(x=r(p["x"]), y=r(p["y"])) for p in pts if p["segment_id"] == c["segment_id"]], pointRadius=2.5) for c in cards]),
                       options=dict(scales=dict(x=dict(display=False), y=dict(display=False)), plugins=dict(legend=dict(position="bottom")), noGrid=True))
        m = meta()
        sil = [(int(a), float(b)) for a, b in (x.split(":") for x in m.get("silhouette_scores", "").split(";") if x)]
        silc = dict(type="line", data=dict(labels=[a for a, _ in sil], datasets=[dict(label="Silhouette score", data=[r(b, 3) for _, b in sil], tension=.3)]),
                    options=dict(plugins=dict(legend=dict(display=False)), scales=dict(x=dict(title=dict(display=True, text="Number of clusters (k)")), y=dict(title=dict(display=True, text="Silhouette")))))
        return render_template("segments.html", page="segments", cards=cards, scatter=scatter, silc=silc, k=m.get("k"), total=len(comments))

    # ------------------------------------------------------------ Q3 anomalies
    @app.route("/anomalies")
    def anomalies():
        posts, _ = apply(*data(), filters())
        typ = request.args.get("type", "")
        an = posts[posts["anomaly_type"].notna()]
        counts = an["anomaly_type"].value_counts().to_dict()
        shown = an[an["anomaly_type"] == typ] if typ else an
        shown = shown.sort_values("anomaly_score", ascending=False)
        base = posts[posts["anomaly_type"].isna() & posts["engagement_rate"].notna()]
        base = base.sample(min(700, len(base)), random_state=3)
        colors = {"Viral over-performer": "#2f9e6e", "Under-performer": "#e0a100", "Complaint spike": "#d6455d",
                  "Comment / demand spike": "#7a5ce0", "Unusual mix": "#e07a1f"}
        ds = [dict(label="Typical posts", data=[dict(x=r(a), y=r(b), id=i) for a, b, i in zip(base["engagement_rate"], base["comment_rate"], base["post_id"])],
                   backgroundColor="rgba(150,160,175,.35)", pointRadius=2.5)]
        for t, sub in an.groupby("anomaly_type"):
            ds.append(dict(label=t, data=[dict(x=r(a), y=r(b), id=i) for a, b, i in zip(sub["engagement_rate"], sub["comment_rate"], sub["post_id"])],
                           backgroundColor=colors.get(t, "#888"), pointRadius=5.5, pointStyle="triangle"))
        sc = dict(type="scatter", data=dict(datasets=ds),
                  options=dict(scales=dict(x=dict(type="logarithmic", title=dict(display=True, text="Engagement rate % (log)")),
                                           y=dict(type="logarithmic", title=dict(display=True, text="Comment rate % (log)"))),
                               plugins=dict(legend=dict(position="bottom")), clickPostId=True))
        page_df, page, pages = paginate(shown, args_page())
        return render_template("anomalies.html", page="anomalies", counts=counts, typ=typ, rows=page_df.to_dict("records"), pg=page, pages=pages,
                               total=len(shown), sc=sc, colors=colors, n_posts=len(posts))

    # ------------------------------------------------------------ recommendations
    @app.route("/recommendations")
    def recommendations():
        recs = db.query("SELECT r.*, s.segment_name FROM recommendation r LEFT JOIN segment s USING(segment_id) ORDER BY CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END, rec_id")
        areas = ["Content", "Promotions", "Customer service", "Campaign testing"]
        return render_template("recommendations.html", page="recommendations", recs=recs, areas=areas, meta=meta())

    # ------------------------------------------------------------ posts
    @app.route("/posts")
    def posts_list():
        posts, _ = apply(*data("all"), filters())
        q = request.args.get("q", "").strip()
        ct = request.args.get("content_type", "")
        sort = request.args.get("sort", "engagement_rate")
        asc = request.args.get("dir", "desc") == "asc"
        only_an = request.args.get("anomalies") == "1"
        if q: posts = posts[posts["post_id"].str.contains(q, case=False)]
        if ct: posts = posts[posts["content_type"] == ct]
        if only_an: posts = posts[posts["anomaly_type"].notna()]
        if sort not in posts.columns: sort = "engagement_rate"
        posts = posts.sort_values(sort, ascending=asc, na_position="last")
        df, page, pages = paginate(posts, args_page())
        all_ct = sorted(data("all")[0]["content_type"].unique())
        return render_template("posts.html", page="posts", rows=df.to_dict("records"), pg=page, pages=pages, total=len(posts),
                               q=q, ct=ct, sort=sort, asc=asc, only_an=only_an, all_ct=all_ct)

    @app.route("/posts/<post_id>")
    def post_detail(post_id):
        posts, comments = data("all")
        row = posts[posts["post_id"] == post_id]
        if row.empty: abort(404)
        p = row.iloc[0].to_dict()
        peers = posts[(posts.brand == p["brand"]) & (posts.platform == p["platform"]) & (posts.content_type == p["content_type"]) & (posts.days_since_post >= 3)]
        peer = dict(n=len(peers), er=r(peers["engagement_rate"].median()), likes=r(peers["likes"].median(), 0), comments=r(peers["comments_count"].median(), 0), shares=r(peers["shares"].median(), 0))
        cm_all = comments[comments["post_id"] == post_id]
        vc = cm_all["topic"].value_counts()
        cm = cm_all.sort_values("like_count", ascending=False, na_position="last").head(300)
        chart = dict(type="doughnut", data=dict(labels=vc.index.tolist(), datasets=[dict(data=vc.values.tolist())]), options=dict(plugins=dict(legend=dict(position="right"))))
        return render_template("post_detail.html", page="posts", p=p, peer=peer, cm=cm.to_dict("records"), topic_chart=chart, n_comments=len(cm_all))

    # ------------------------------------------------------------ comments
    @app.route("/comments")
    def comments_list():
        _, comments = apply(*data("all"), filters())
        sel = {k: request.args.get(k, "") for k in ("topic", "language_type", "sentiment", "purchase_intent", "segment")}
        q = request.args.get("q", "").strip()
        for k, v in sel.items():
            if v: comments = comments[comments[k] == v]
        if q: comments = comments[comments["comment_text"].str.contains(q, case=False, regex=False)]
        _, allc = data("all")
        opts = {k: sorted(allc[k].dropna().unique().tolist()) for k in sel}
        df, page, pages = paginate(comments, args_page())
        return render_template("comments.html", page="comments", rows=df.to_dict("records"), pg=page, pages=pages, total=len(comments), sel=sel, q=q, opts=opts)

    # ------------------------------------------------------------ try the classifier
    @lru_cache(maxsize=1)
    def model():
        return joblib.load(config.MODEL_PATH)

    @app.route("/analyze")
    def analyze_page():
        return render_template("analyze.html", page="analyze")

    @app.post("/api/analyze")
    def api_analyze():
        text = (request.get_json(silent=True) or {}).get("text", "").strip()
        if not text: return jsonify(error="Please type a comment first."), 400
        if len(text) > 500: return jsonify(error="Comments are limited to 500 characters."), 400
        out = nlp.analyze(text)
        try:
            idx = analytics.assign_segment(model(), text)
            sid = model()["segment_ids"][idx]
            seg = db.query("SELECT segment_name, suggested_action FROM segment WHERE segment_id=?", (sid,))[0]
            out.update(segment=seg["segment_name"], suggested_action=seg["suggested_action"])
        except Exception:
            out.update(segment=None, suggested_action=None)
        return jsonify(out)

    # ------------------------------------------------------------ database page + SQL console
    ER_LAYOUT = {  # table -> (x, y); boxes are 200 wide on a 1160 x 520 canvas
        "brand": (20, 20), "platform": (20, 100), "campaign": (20, 180), "content_type": (20, 260), "product_category": (20, 340),
        "account": (250, 20), "commenter": (250, 170), "run_metadata": (250, 300), "data_source": (250, 420),
        "post_anomaly": (480, 20), "post": (480, 150), "language_type": (480, 400),
        "segment_map_point": (710, 20), "comment": (710, 120), "topic": (710, 400),
        "recommendation": (940, 20), "segment": (940, 190), "sentiment": (940, 320), "purchase_intent": (940, 400),
    }

    @app.route("/database")
    def database_page():
        conn = db.connect(readonly=True)
        tables = []
        for (name,) in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            cols = conn.execute(f"PRAGMA table_info({name})").fetchall()
            fks = {f["from"]: f"{f['table']}.{f['to']}" for f in conn.execute(f"PRAGMA foreign_key_list({name})")}
            tables.append(dict(name=name, rows=conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0],
                               cols=[dict(name=c["name"], type=c["type"], pk=bool(c["pk"]), nn=bool(c["notnull"]), fk=fks.get(c["name"])) for c in cols]))
        views = [r_[0] for r_ in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")]
        conn.close()
        edges = [(t["name"], c["fk"].split(".")[0]) for t in tables for c in t["cols"] if c["fk"]]
        examples = [
            ("Engagement by content type", "SELECT content_type, platform, COUNT(*) AS posts,\n       ROUND(AVG(likes+comments_count+COALESCE(shares,0)) * 100.0 / AVG(followers), 2) AS er_pct\nFROM v_post_flat\nGROUP BY content_type, platform\nORDER BY er_pct DESC;"),
            ("Topic mix per brand", "SELECT p.brand, c.topic, COUNT(*) AS n\nFROM v_comment_flat c JOIN v_post_flat p USING(post_id)\nGROUP BY p.brand, c.topic\nORDER BY p.brand, n DESC;"),
            ("3-table join (normalised)", "SELECT b.brand_name, pl.platform_name, a.followers, COUNT(p.post_id) AS posts\nFROM account a\nJOIN brand b USING(brand_id)\nJOIN platform pl USING(platform_id)\nLEFT JOIN post p USING(account_id)\nGROUP BY a.account_id\nORDER BY posts DESC;"),
            ("Flagged posts", "SELECT a.post_id, a.anomaly_type, ROUND(a.anomaly_score,3) AS score, a.reason\nFROM post_anomaly a\nORDER BY a.anomaly_score DESC\nLIMIT 20;"),
            ("Segments and sizes", "SELECT s.segment_name, COUNT(*) AS comments\nFROM comment c JOIN segment s USING(segment_id)\nGROUP BY s.segment_id ORDER BY comments DESC;"),
        ]
        return render_template("database.html", page="database", tables=tables, views=views, edges=edges, layout=ER_LAYOUT, examples=examples)

    @app.post("/api/sql")
    def api_sql():
        sql = (request.get_json(silent=True) or {}).get("sql", "").strip().rstrip(";")
        if not sql: return jsonify(error="Type a SELECT query first."), 400
        if len(sql) > 4000: return jsonify(error="Query too long."), 400
        if not re.match(r"^(select|with)\b", sql, re.I) or ";" in sql:
            return jsonify(error="Only a single SELECT statement is allowed here."), 400
        conn = db.connect(readonly=True)
        allowed = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
        conn.set_authorizer(lambda action, *a: sqlite3.SQLITE_OK if action in allowed else sqlite3.SQLITE_DENY)
        ticks = {"n": 0}
        def guard():
            ticks["n"] += 1
            return 1 if ticks["n"] > 4000 else 0     # abort runaway queries
        conn.set_progress_handler(guard, 10000)
        try:
            cur = conn.execute(f"SELECT * FROM ({sql}) LIMIT 501")
            cols = [d[0] for d in cur.description]
            rows = [list(x) for x in cur.fetchall()]
        except sqlite3.Error as e:
            return jsonify(error=f"SQL error: {e}"), 400
        finally:
            conn.close()
        return jsonify(columns=cols, rows=rows[:500], truncated=len(rows) > 500)

    # ------------------------------------------------------------ YouTube sentiment (real data)
    _STOP = set("the a an and or but if so to of in on at for with is are was were be been it its this that these those i you he she we they them his her their my your our me us not no do does did have has had will would can could just very really more most than then there here what when who how why which all any some one from by as about out up like get got also too even only dont doesnt isnt im ive youre thats cant wont".split())

    @app.route("/youtube")
    def youtube():
        posts, comments = data("all")
        yt = comments[comments["platform"] == "YouTube"].copy()
        if yt.empty:
            return render_template("youtube.html", page="youtube", empty=True)
        yt["year"] = yt["published_at"].str[:4]
        order = ["Negative", "Neutral", "Positive"]
        col = {"Positive": "#2f9e6e", "Neutral": "#9aa5b1", "Negative": "#d6455d"}
        dist = yt["sentiment"].value_counts().reindex(order).fillna(0).astype(int)
        by_year = pd.crosstab(yt["year"], yt["sentiment"]).reindex(columns=order).fillna(0).astype(int)
        bins = pd.cut(yt["sentiment_score"], bins=np.linspace(-1, 1, 11), include_lowest=True)
        hist = bins.value_counts().sort_index()
        lk = yt.groupby("sentiment")["like_count"].mean().reindex(order)
        words = {}
        for s in order:
            toks = re.findall(r"[a-z']{3,}", " ".join(yt.loc[yt["sentiment"] == s, "comment_text"]).lower())
            words[s] = pd.Series([t for t in toks if t not in _STOP]).value_counts().head(10).to_dict()
        top = yt.sort_values("like_count", ascending=False).head(8)
        kp = dict(n=len(yt), people=int(yt["commenter"].nunique()), neg=float((yt["sentiment"] == "Negative").mean()),
                  pos=float((yt["sentiment"] == "Positive").mean()), neu=float((yt["sentiment"] == "Neutral").mean()),
                  score=r(yt["sentiment_score"].mean(), 2), likes=int(yt["like_count"].sum()), first=yt["published_at"].min()[:10], last=yt["published_at"].max()[:10],
                  conf=r(yt["sentiment_confidence"].mean(), 2))
        charts = dict(
            dist=dict(type="doughnut", data=dict(labels=order, datasets=[dict(data=dist.tolist(), backgroundColor=[col[s] for s in order])]), options=dict(plugins=dict(legend=dict(position="bottom")))),
            year=dict(type="bar", data=dict(labels=by_year.index.tolist(), datasets=[dict(label=s, data=by_year[s].tolist(), backgroundColor=col[s]) for s in order]),
                      options=dict(scales=dict(x=dict(stacked=True), y=dict(stacked=True, title=dict(display=True, text="Comments"))), plugins=dict(legend=dict(position="bottom")))),
            hist=dict(type="bar", data=dict(labels=[f"{i.left:+.1f} to {i.right:+.1f}" for i in hist.index], datasets=[dict(label="Comments", data=hist.tolist())]),
                      options=dict(plugins=dict(legend=dict(display=False)), scales=dict(x=dict(title=dict(display=True, text="Sentiment score (-1 negative … +1 positive)"))))),
            likes=dict(type="bar", data=dict(labels=order, datasets=[dict(label="Average likes per comment", data=[r(v) for v in lk.values], backgroundColor=[col[s] for s in order])]),
                       options=dict(plugins=dict(legend=dict(display=False)))),
        )
        return render_template("youtube.html", page="youtube", empty=False, kp=kp, charts=charts, words=words, top=top.to_dict("records"), order=order)

    # ------------------------------------------------------------ about
    @app.route("/about")
    def about():
        src = db.query("""SELECT ds.*, COUNT(p.post_id) AS posts FROM data_source ds LEFT JOIN post p USING(source_id) GROUP BY ds.source_id""")
        return render_template("about.html", page="about", src=src, meta=meta())

    # ------------------------------------------------------------ exports
    @app.route("/export/<name>.csv")
    def export(name):
        posts, comments = apply(*data("all"), filters())
        if name == "posts": df = posts.drop(columns=["shares_f"], errors="ignore")
        elif name == "comments": df = comments
        elif name == "anomalies": df = posts[posts["anomaly_type"].notna()][["post_id", "brand", "platform", "campaign", "content_type", "anomaly_type", "anomaly_score", "reason"]]
        elif name == "recommendations": df = pd.DataFrame(db.query("SELECT area,priority,title,evidence,action FROM recommendation"))
        else: abort(404)
        buf = io.StringIO(); df.to_csv(buf, index=False)
        return Response("\ufeff" + buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}.csv"})

    @app.route("/healthz")
    def health():
        return jsonify(status="ok")

    @app.errorhandler(404)
    def nf(e):
        return render_template("error.html", page="", code=404, msg="We couldn't find that page."), 404

    @app.errorhandler(500)
    def err(e):
        return render_template("error.html", page="", code=500, msg="Something went wrong on our side."), 500

    return app
