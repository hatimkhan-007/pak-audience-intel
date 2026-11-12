import pandas as pd
from sklearn.cluster import KMeans
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import Normalizer

EXTRA_STOP = {"gillette", "video", "ad", "ads", "commercial", "just", "like", "don", "ve", "really", "people"}


def cluster_comments(df, k=8, seed=42):
    vectorizer = TfidfVectorizer(
        stop_words=list(ENGLISH_STOP_WORDS | EXTRA_STOP), ngram_range=(1, 2), min_df=3, max_df=0.4, sublinear_tf=True
    )
    matrix = vectorizer.fit_transform(df["text_for_model"])
    reduced = Normalizer().fit_transform(TruncatedSVD(50, random_state=seed).fit_transform(matrix))
    model = KMeans(n_clusters=k, n_init=10, random_state=seed).fit(reduced)
    labelled = df.assign(cluster=model.labels_)

    terms = vectorizer.get_feature_names_out()
    rows = []
    for c in range(k):
        members = labelled[labelled["cluster"] == c]
        best = members.sort_values("like_count", ascending=False).iloc[0]
        weights = matrix[(model.labels_ == c).nonzero()[0]].mean(axis=0).A1
        rows.append({
            "cluster": c,
            "comments": len(members),
            "share": len(members) / len(labelled),
            "top_terms": ", ".join(terms[i] for i in weights.argsort()[::-1][:5]),
            "negative_share": (members["sentiment"] == "Negative").mean(),
            "median_likes": members["like_count"].median(),
            "mean_replies": members["reply_count"].mean(),
            "share_of_likes": members["like_count"].sum() / max(labelled["like_count"].sum(), 1),
            "top_comment": best["clean_comment"][:160],
        })
    summary = pd.DataFrame(rows).sort_values("comments", ascending=False)
    score = silhouette_score(reduced, model.labels_, sample_size=min(2000, len(labelled)), random_state=seed)
    return labelled, summary, score
