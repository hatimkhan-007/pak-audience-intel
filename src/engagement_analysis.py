import pandas as pd


def summarize(df, by):
    table = df.groupby(by).agg(
        comments=("comment_id", "count"),
        median_likes=("like_count", "median"),
        mean_replies=("reply_count", "mean"),
        total_likes=("like_count", "sum"),
        reply_rate=("reply_count", lambda s: (s > 0).mean()),
    )
    table["share_of_likes"] = table["total_likes"] / max(table["total_likes"].sum(), 1)
    return table.round(3).sort_values("share_of_likes", ascending=False)


def length_bucket(df):
    return pd.cut(df["word_count"], [0, 5, 15, 40, 10000], labels=["1-5 words", "6-15 words", "16-40 words", "41+ words"])


def top_comments(df, n=10):
    cols = ["clean_comment", "sentiment", "like_count", "reply_count", "published_at"]
    return df.sort_values("like_count", ascending=False)[cols].head(n)
