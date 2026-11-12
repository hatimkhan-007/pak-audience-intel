import pandas as pd

from src.engagement_analysis import summarize


def build_recommendations(df, summary, anomalies, spikes, unlabeled_reviews=0):
    rows = []
    neg_share = (df["sentiment"] == "Negative").mean()
    by_sent = summarize(df, "sentiment")
    neg_likes = by_sent.loc["Negative", "share_of_likes"] if "Negative" in by_sent.index else 0
    rows.append({
        "area": "Reputation",
        "recommendation": "Prepare a clear public response position and monitor negative sentiment weekly.",
        "evidence": f"{neg_share:.1%} of comments are negative and they hold {neg_likes:.1%} of all likes.",
    })

    top_likes = summary.sort_values("share_of_likes", ascending=False).iloc[0]
    rows.append({
        "area": "Messaging",
        "recommendation": "Address the most-endorsed audience theme directly in future campaign messaging.",
        "evidence": f"Theme '{top_likes['top_terms']}' earns {top_likes['share_of_likes']:.1%} of likes from {top_likes['share']:.1%} of comments.",
    })

    top_replies = summary.sort_values("mean_replies", ascending=False).iloc[0]
    rows.append({
        "area": "Community management",
        "recommendation": "Join discussions in the most reply-heavy theme with moderated, factual responses.",
        "evidence": f"Theme '{top_replies['top_terms']}' averages {top_replies['mean_replies']:.1f} replies per comment.",
    })

    flagged = anomalies[anomalies["is_anomaly"]]
    if len(flagged):
        reason = flagged["reason"].value_counts().index[0].lower()
        rows.append({
            "area": "Moderation",
            "recommendation": "Review flagged comments first; they steer the conversation more than typical ones.",
            "evidence": f"{len(flagged)} comments are unusual, mostly due to {reason}.",
        })

    peaks = spikes[spikes["is_spike"]]
    if len(peaks):
        top = peaks["comments"].idxmax()
        rows.append({
            "area": "Monitoring",
            "recommendation": "Increase monitoring around known spike periods and anniversaries.",
            "evidence": f"{len(peaks)} months show spikes; the largest is {top} with {int(peaks.loc[top, 'comments'])} comments.",
        })

    if unlabeled_reviews:
        rows.append({
            "area": "Data quality",
            "recommendation": "Complete the manual labels in the review sample before relying on sentiment results.",
            "evidence": f"{unlabeled_reviews} sampled comments still have no manual label; sarcasm is a known risk.",
        })
    return pd.DataFrame(rows)
