"""Unsupervised analytics: audience segments (clustering), anomaly detection
and rule-based, evidence-backed recommendations."""
from __future__ import annotations
import re
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import IsolationForest
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.manifold import TSNE
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import normalize as l2norm

from .nlp import cluster_text, CITIES

# =========================================================================
# 1.  Audience segments  (TF-IDF -> SVD -> K-Means, k chosen by silhouette)
# =========================================================================
SEGMENT_PROFILES = {
    "Discount request":   ("Discount hunters", "Waiting for sales, promo codes or price cuts before buying.",
                           "Run time-boxed offers (11.11 / 12.12 style), put the promo code in caption + bio, and announce sale dates in advance."),
    "Delivery complaint": ("Delivery-concerned shoppers", "Existing customers whose order is late, missing or wrong and who cannot reach support.",
                           "Reply publicly within hours, move the conversation to DM with the order ID, and publish realistic delivery times during sale periods."),
    "Delivery inquiry":   ("Delivery-timeline askers", "Prospects checking delivery time, charges or cash-on-delivery before committing.",
                           "Add delivery time, charges and COD info to captions or a pinned comment."),
    "Availability":       ("Availability seekers", "Asking whether a design is in stock, in their city or coming back.",
                           "Show stock status and city/store availability in the post; add a 'notify me' or restock note for sold-out designs."),
    "Sizing & fit":       ("Fit & size askers", "Unsure about size, length or fit and need reassurance.",
                           "Pin the size chart, show the model's size, and add fit notes to product posts and styling videos."),
    "Fabric quality":     ("Fabric evaluators", "Want to know the fabric, wash behaviour and quality before paying.",
                           "Show close-ups of the fabric, state the material in the first line, and add care instructions."),
    "Price inquiry":      ("Price askers", "Simply asking for the price; a sign the price is missing from the content.",
                           "Put the price in the caption or the first frame; pin a price list."),
    "Price concern":      ("Price-sensitive critics", "Think the price is too high for the product.",
                           "Justify price with fabric/embroidery detail, test value bundles, and avoid price-only messaging."),
    "Purchase intent":    ("Ready-to-buy leads", "Explicitly want to buy: asking to be contacted, to order, or for a WhatsApp number.",
                           "Auto-reply with an order link / WhatsApp number and route to sales within minutes."),
    "Praise":             ("Admirers", "Positive reactions and compliments with no question attached.",
                           "Engage with a reply and re-use their words as social proof; invite them to tag or share."),
    "Other":              ("Casual engagers", "Giveaway, model-ID and follow-back style comments.",
                           "Low priority; answer the model/credits questions in the caption."),
}


def segment_comments(comments: pd.DataFrame, seed=42, k_range=range(8, 15)):
    """comments needs columns: comment_text, topic, language_type."""
    texts = comments["comment_text"].map(cluster_text)
    vec = TfidfVectorizer(ngram_range=(1, 2), min_df=3, sublinear_tf=True)
    X = vec.fit_transform(texts)
    svd = TruncatedSVD(n_components=min(50, X.shape[1] - 1), random_state=seed)
    Z = l2norm(svd.fit_transform(X))

    scores, models = {}, {}
    for k in k_range:
        km = KMeans(n_clusters=k, n_init=5, random_state=seed).fit(Z)
        n = min(4000, len(Z))
        scores[k] = float(silhouette_score(Z, km.labels_, sample_size=n, random_state=seed))
        models[k] = km
    best_k = max(scores, key=scores.get)
    km = models[best_k]
    labels = km.labels_

    df = comments[["topic", "language_type"]].copy()
    df["c"] = labels
    terms = np.array(vec.get_feature_names_out())
    segs, used = [], {}
    for c in range(best_k):
        m = labels == c
        sub = df[m]
        topic_share = sub["topic"].value_counts(normalize=True)
        dom, purity = topic_share.index[0], float(topic_share.iloc[0])
        profile = SEGMENT_PROFILES[dom]
        name = profile[0] if purity >= 0.55 else "Mixed: " + profile[0].lower() + " & " + SEGMENT_PROFILES[topic_share.index[1]][0].lower() if len(topic_share) > 1 else profile[0]
        lang = sub["language_type"].value_counts().index[0]
        used[name] = used.get(name, 0) + 1
        centroid = np.asarray(X[m].mean(axis=0)).ravel()
        top = [t for t in terms[np.argsort(centroid)[::-1][:12]] if not t.startswith("x")][:6]
        mix = ", ".join(f"{t} {s:.0%}" for t, s in topic_share.head(3).items())
        segs.append(dict(cluster=c, size=int(m.sum()), dominant_topic=dom, purity=purity, base_name=name,
                         language=lang, description=f"{profile[1]} (Mix: {mix}.)", suggested_action=profile[2],
                         top_terms=", ".join(top)))
    for s in segs:   # disambiguate duplicate names: language first, then the cluster's key term
        if used[s["base_name"]] > 1:
            s["segment_name"] = f'{s["base_name"]} ({s["language"]})'
        else:
            s["segment_name"] = s["base_name"]
    from collections import Counter
    dup = Counter(s["segment_name"] for s in segs)
    for s in segs:
        if dup[s["segment_name"]] > 1:
            key = s["top_terms"].split(", ")[0]
            s["segment_name"] += f' · "{key}"'
    segs.sort(key=lambda s: -s["size"])
    order = {s["cluster"]: i for i, s in enumerate(segs)}      # cluster -> display order
    # 2-D map (t-SNE on a stratified sample)
    rng = np.random.default_rng(seed)
    idx = np.sort(rng.choice(len(Z), size=min(2600, len(Z)), replace=False))
    emb = TSNE(n_components=2, perplexity=35, init="pca", random_state=seed, learning_rate="auto").fit_transform(Z[idx])
    emb += rng.normal(0, 0.6, emb.shape)                            # tiny jitter: many comments are identical
    model = dict(vec=vec, svd=svd, km=km, order=order)
    return labels, segs, scores, best_k, idx, emb, model


def assign_segment(model, text: str) -> int:
    """Return the display-order index of the nearest segment for a new comment."""
    X = model["vec"].transform([cluster_text(text)])
    Z = l2norm(model["svd"].transform(X))
    return model["order"][int(model["km"].predict(Z)[0])]


# =========================================================================
# 2.  Anomalies  (peer-relative robust z-scores + Isolation Forest)
# =========================================================================
def _robust_z(s: pd.Series, groups: pd.Series, floor_factor=0.25) -> pd.Series:
    med = s.groupby(groups).transform("median")
    mad = (s - med).abs().groupby(groups).transform("median") * 1.4826
    floor = s.groupby(groups).transform("std").fillna(0) * floor_factor + 1e-6
    return ((s - med) / np.maximum(mad, floor)).clip(-12, 12)


def detect_anomalies(posts: pd.DataFrame, comments: pd.DataFrame, seed=42, contamination=0.04):
    df = posts[posts["days_since_post"] >= 2].dropna(subset=["engagement_rate"]).copy()
    # "comparable posts" = same brand, platform and format; fall back to broader groups when thin
    df["peer"] = df["brand"] + " | " + df["platform"] + " " + df["content_type"]
    for fallback in (df["platform"] + " " + df["content_type"], df["platform"]):
        small = df.groupby("peer")["post_id"].transform("size") < 12
        df.loc[small, "peer"] = fallback[small]

    g = comments.groupby("post_id")
    cm = pd.DataFrame({
        "n_c": g.size(),
        "neg": g["sentiment"].apply(lambda s: (s == "Negative").mean()),
        "compl": g["topic"].apply(lambda s: (s == "Delivery complaint").mean()),
        "promo": g["topic"].apply(lambda s: s.isin(["Discount request", "Availability"]).mean()),
    })
    df = df.merge(cm, left_on="post_id", right_index=True, how="left")
    enough = df["n_c"].fillna(0) >= 3
    cnt = comments.assign(neg=comments["sentiment"].eq("Negative"), compl=comments["topic"].eq("Delivery complaint"),
                          promo=comments["topic"].isin(["Discount request", "Availability"])).groupby("post_id")[["neg", "compl", "promo"]].sum()
    for c in ("neg", "compl", "promo"):
        df.loc[~enough, c] = np.nan
        raw = df["post_id"].map(cnt[c]).fillna(0)
        df.loc[raw < 3, c] = np.nan           # a handful of comments is noise, not a pattern

    feats = {
        "engagement rate": np.log(df["engagement_rate"].clip(lower=1e-4)),
        "comment rate": np.log(df["comment_rate"].clip(lower=1e-5)),
        "share rate": np.log1p(df["share_rate"] * 100),
        "views per follower": np.log(df["views"] / df["followers"].where(df["followers"] > 0)),
        "negative-comment share": df["neg"], "complaint share": df["compl"], "promo-comment share": df["promo"],
    }
    share_feats = {"negative-comment share", "complaint share", "promo-comment share"}
    Z = pd.DataFrame({k: _robust_z(v, df["peer"], 0.6 if k in share_feats else 0.25) for k, v in feats.items()}).fillna(0.0)
    iso = IsolationForest(n_estimators=300, contamination=contamination, random_state=seed).fit(Z)
    df["anomaly_score"] = -iso.score_samples(Z)
    flagged = (iso.predict(Z) == -1) & (Z.abs().max(axis=1) >= 3.0)

    med = {k: v.groupby(df["peer"]).transform("median") for k, v in feats.items()}
    rows = []
    for i in np.where(flagged)[0]:
        r, z = df.iloc[i], Z.iloc[i]
        peer = r["peer"]
        er_med = df.loc[df["peer"] == peer, "engagement_rate"].median()
        parts = []
        top = z.abs().sort_values(ascending=False).index[:2]
        for f in top:
            d = "above" if z[f] > 0 else "below"
            if f == "engagement rate":
                parts.append(f"Engagement rate {r['engagement_rate']:.2f}% vs {er_med:.2f}% median ({r['engagement_rate'] / er_med:.1f}x) for comparable posts ({peer})")
            elif f in ("negative-comment share", "complaint share", "promo-comment share"):
                col = {"negative-comment share": "neg", "complaint share": "compl", "promo-comment share": "promo"}[f]
                typical = df.loc[df["peer"] == peer, col].median()
                parts.append(f"{f} {r[col]:.0%} vs {typical:.0%} typical")
            else:
                parts.append(f"{f} far {d} the norm for comparable posts (z={z[f]:+.1f})")
        if z["engagement rate"] >= 3:
            typ = "Viral over-performer"
        elif z["engagement rate"] <= -3:
            typ = "Under-performer"
        elif max(z["complaint share"], z["negative-comment share"]) >= 3:
            typ = "Complaint spike"
        elif max(z["comment rate"], z["promo-comment share"]) >= 3:
            typ = "Comment / demand spike"
        else:
            typ = "Unusual mix"
        txt = "; ".join(parts) + "."
        rows.append((r["post_id"], float(r["anomaly_score"]), typ, txt[0].upper() + txt[1:]))
    return pd.DataFrame(rows, columns=["post_id", "anomaly_score", "anomaly_type", "reason"])


# =========================================================================
# 3.  Recommendations
# =========================================================================
def _pct(x): return f"{x:.1%}"


def build_recommendations(posts, comments, segments):
    """segments: DataFrame(segment_id, segment_name, dominant_topic, size). Returns list of dicts."""
    recs = []
    seg_for = {r.dominant_topic: int(r.segment_id) for r in segments.sort_values("size", ascending=False).itertuples()}
    P = posts[(posts["days_since_post"] >= 3) & posts["engagement_rate"].notna()]
    N = len(comments)

    def add(area, priority, title, evidence, action, topic=None):
        recs.append(dict(area=area, priority=priority, title=title, evidence=evidence, action=action,
                         segment_id=seg_for.get(topic) if topic else None))

    # ---- Content ----------------------------------------------------------------
    by_ct = P.groupby("content_type")["er_index"].agg(["median", "size"]).sort_values("median", ascending=False)
    if len(by_ct) >= 2:
        best, worst = by_ct.index[0], by_ct.index[-1]
        add("Content", "High", f"Shift more budget and effort into {best}s",
            f"After adjusting for platform norms, {best} posts have the highest engagement index ({by_ct.loc[best,'median']:.2f}, where 1.00 = typical post on the same platform; n={int(by_ct.loc[best,'size'])}); "
            f"{worst} is lowest ({by_ct.loc[worst,'median']:.2f}, n={int(by_ct.loc[worst,'size'])}), a {by_ct.loc[best,'median']/by_ct.loc[worst,'median']:.1f}x gap.",
            f"Plan the next campaign calendar around {best} and re-purpose {worst} content into that format.")
    for plat, sub in P.groupby("platform"):
        t = sub.groupby("content_type")["engagement_rate"].agg(["median", "size"])
        t = t[t["size"] >= 15].sort_values("median", ascending=False)
        if len(t) >= 2:
            add("Content", "Medium", f"On {plat}, lead with {t.index[0]}",
                f"Median engagement rate on {plat}: {t.index[0]} {t.iloc[0]['median']:.2f}% vs {t.index[-1]} {t.iloc[-1]['median']:.2f}% (n={int(t.iloc[0]['size'])} and {int(t.iloc[-1]['size'])}).",
                f"Make {t.index[0]} the default format for {plat} launches; keep {t.index[-1]} for supporting detail only.")
    by_camp = P.groupby("campaign")["er_index"].median().sort_values(ascending=False)
    if len(by_camp) >= 2:
        add("Content", "Low", f"Replicate the creative approach of '{by_camp.index[0]}'",
            f"'{by_camp.index[0]}' posts have a platform-adjusted engagement index of {by_camp.iloc[0]:.2f} vs {by_camp.iloc[-1]:.2f} for '{by_camp.index[-1]}' (1.00 = platform norm).",
            "Review the top posts of the best campaign (hook, model, caption) and brief the next campaign from them.")

    # ---- Customer service --------------------------------------------------------
    comp = comments[comments["topic"] == "Delivery complaint"]
    if N and len(comp):
        share = len(comp) / N
        by_b = (comments.assign(c=comments["topic"] == "Delivery complaint").groupby("brand")["c"].mean().sort_values(ascending=False))
        worst_b = by_b.index[0]
        prio = "High" if share > .03 or by_b.iloc[0] > share * 2 else "Medium"
        add("Customer service", prio, "Fix delivery complaints before they spread publicly",
            f"{_pct(share)} of all comments are delivery complaints; {worst_b} is worst at {_pct(by_b.iloc[0])} ({by_b.iloc[0]/max(share,1e-9):.1f}x the average).",
            f"Assign a support owner for {worst_b}, answer complaints within hours, and publish realistic delivery times during 11.11/12.12.", "Delivery complaint")
        sale = comments.assign(c=comments["topic"] == "Delivery complaint").groupby("campaign")["c"].mean().sort_values(ascending=False)
        add("Customer service", "Medium", f"Staff up support for '{sale.index[0]}'",
            f"Delivery complaints peak during '{sale.index[0]}' ({_pct(sale.iloc[0])} of comments) vs {_pct(sale.iloc[-1])} in '{sale.index[-1]}'.",
            "Add temporary support capacity and a pre-written reply set for the peak campaign window.", "Delivery complaint")
    inq = comments["topic"].value_counts(normalize=True)
    faq = [t for t in ["Price inquiry", "Sizing & fit", "Delivery inquiry", "Fabric quality", "Availability"] if t in inq.index]
    faq = sorted(faq, key=lambda t: -inq[t])[:3]
    if faq:
        add("Customer service", "Medium", "Answer the top repeat questions in the content itself",
            "The most frequent questions are " + ", ".join(f"{t.lower()} ({_pct(inq[t])})" for t in faq) + " of all comments.",
            "Pin an FAQ comment and add price, size and delivery info to every product caption; set up saved replies.", faq[0])
    ready = comments[comments["topic"] == "Purchase intent"]
    if len(ready):
        r_ct = comments.assign(c=comments["topic"] == "Purchase intent").groupby("content_type")["c"].mean().sort_values(ascending=False)
        add("Customer service", "High" if len(ready) / N > .06 else "Medium", "Capture ready-to-buy comments with a fast DM/WhatsApp flow",
            f"{len(ready):,} comments ({_pct(len(ready)/N)}) explicitly ask to order or be contacted; they appear most on {r_ct.index[0]} content ({_pct(r_ct.iloc[0])}).",
            "Auto-reply with the order link/WhatsApp number and track response time for these leads.", "Purchase intent")

    # ---- Promotions --------------------------------------------------------------
    disc = comments[comments["topic"] == "Discount request"]
    if len(disc):
        by_c = comments.assign(c=comments["topic"] == "Discount request").groupby("campaign")["c"].mean().sort_values(ascending=False)
        add("Promotions", "High" if len(disc) / N > .1 else "Medium", "Give discount hunters a structured offer instead of ad-hoc replies",
            f"{_pct(len(disc)/N)} of comments ask for a discount; highest in '{by_c.index[0]}' ({_pct(by_c.iloc[0])}).",
            "Test a code-based or tiered offer (e.g. 2 suits = extra %), announce sale dates early, and keep non-sale posts price-stable.", "Discount request")
    pc = comments[comments["topic"] == "Price concern"]
    if len(pc):
        by_b = comments.assign(c=comments["topic"] == "Price concern").groupby("brand")["c"].mean().sort_values(ascending=False)
        add("Promotions", "Medium", f"Reframe value for {by_b.index[0]}'s price-sensitive audience",
            f"{by_b.index[0]} gets {_pct(by_b.iloc[0])} price-concern comments vs {_pct(len(pc)/N)} overall.",
            "Lead with fabric and embroidery detail, test a lower-priced entry line or bundle, and monitor price-concern share after each launch.", "Price concern")
    av = comments[comments["topic"] == "Availability"]
    if len(av):
        cities = pd.Series(re.findall("|".join(CITIES), " ".join(comments["comment_text"].str.lower())))
        top_c = cities.value_counts().head(3)
        city_txt = ", ".join(f"{c.title()} ({n:,})" for c, n in top_c.items()) if len(top_c) else "several cities"
        add("Promotions", "Medium", "Publish stock and city availability, and plan restocks",
            f"{_pct(len(av)/N)} of comments ask about availability; cities mentioned most: {city_txt}.",
            "Show stock status in posts, add a restock notification, and prioritise inventory/delivery hubs in the most-mentioned cities.", "Availability")

    # ---- Campaign testing --------------------------------------------------------
    lang = comments["language_type"].value_counts(normalize=True)
    if "Roman Urdu" in lang.index:
        add("Campaign testing", "Medium", "A/B test Roman Urdu vs English captions",
            f"{_pct(lang['Roman Urdu'])} of comments are in Roman Urdu and {_pct(lang.get('English', 0))} in English" + (f"; {_pct(lang['Urdu'])} use Urdu script." if "Urdu" in lang.index else "."),
            "Run the same product post with an English and a Roman Urdu caption (same time slot) and compare comment rate and DM requests.")
    if len(by_ct) >= 2 and by_ct.iloc[0]["median"] / by_ct.iloc[1]["median"] < 1.15:
        add("Campaign testing", "Low", f"Run a head-to-head test: {by_ct.index[0]} vs {by_ct.index[1]}",
            f"The two formats are within {by_ct.iloc[0]['median']/by_ct.iloc[1]['median']-1:.0%} of each other on platform-adjusted engagement.",
            "Publish matched posts for one product line and let reach, saves and DM requests decide.")
    pr = comments[comments["topic"].isin(["Price inquiry"])]
    if len(pr):
        add("Campaign testing", "Medium", "Test price-in-caption vs price-on-request",
            f"{_pct(len(pr)/N)} of comments are plain price questions, a sign the price is missing from the creative.",
            "Split similar posts: one with the price in the first line, one without; compare price-question rate and click/DM conversions.", "Price inquiry")

    # ---- anomalies ---------------------------------------------------------------
    a = posts[posts["anomaly_type"].notna()]
    if len(a):
        counts = a["anomaly_type"].value_counts()
        viral = a[a["anomaly_type"] == "Viral over-performer"]
        if len(viral):
            top_ct = viral["content_type"].value_counts().index[0]
            add("Content", "High", "Study the viral over-performers and repeat what worked",
                f"{len(viral)} posts are statistically viral vs comparable posts; most are {top_ct} content (best: {viral.sort_values('anomaly_score', ascending=False).iloc[0]['post_id']}).",
                "Open the flagged posts on the Anomalies page, identify the shared hook/creator/timing, and brief the next shoot from them.")
        cs = a[a["anomaly_type"].isin(["Complaint spike"])]
        if len(cs):
            add("Customer service", "High", f"Investigate {len(cs)} posts with complaint spikes",
                f"These posts have unusually high negative/complaint comment shares vs comparable posts (e.g. {cs.sort_values('anomaly_score', ascending=False).iloc[0]['post_id']}).",
                "Triage the comment threads, reply to affected customers and check what product or fulfilment issue sits behind them.", "Delivery complaint")
        ds = a[a["anomaly_type"] == "Comment / demand spike"]
        if len(ds):
            add("Promotions", "Medium", f"Follow up {len(ds)} posts with demand spikes",
                f"Comment volume or discount/availability asks are unusually high on {len(ds)} posts (e.g. {ds.iloc[0]['post_id']}).",
                "Check whether stock, price or an offer is driving the demand and respond with a targeted promotion or restock.", "Discount request")
        us = a[a["anomaly_type"] == "Under-performer"]
        if len(us):
            add("Campaign testing", "Low", f"Review {len(us)} under-performing posts",
                f"{len(us)} posts earn far less engagement than comparable posts.",
                "Compare their timing, caption and creative with peers before repeating the format.")
    order = {"High": 0, "Medium": 1, "Low": 2}
    recs.sort(key=lambda r: order[r["priority"]])
    return recs
