import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

FEATURES = {
    "likes_rel": "likes",
    "replies_rel": "replies",
    "words_rel": "comment length",
    "sentiment_score": "sentiment score",
    "confidence": "model confidence",
}


def detect_comment_anomalies(df, contamination=0.05, seed=42):
    out = df.copy()
    group = out.groupby("sentiment")
    out["likes_rel"] = np.log1p(out["like_count"] / group["like_count"].transform("median").clip(lower=1))
    out["replies_rel"] = np.log1p(out["reply_count"] / group["reply_count"].transform("mean").clip(lower=0.5))
    out["words_rel"] = np.log1p(out["word_count"] / group["word_count"].transform("median").clip(lower=1))
    cols = list(FEATURES)
    scaled = StandardScaler().fit_transform(out[cols])
    model = IsolationForest(contamination=contamination, random_state=seed).fit(scaled)
    out["anomaly_score"] = -model.decision_function(scaled)
    out["is_anomaly"] = model.predict(scaled) == -1
    strongest = np.abs(scaled).argmax(axis=1)
    sign = np.where(scaled[np.arange(len(out)), strongest] > 0, "High", "Low")
    out["reason"] = [f"{s} {FEATURES[cols[i]]}" for s, i in zip(sign, strongest)]
    return out.drop(columns=["likes_rel", "replies_rel", "words_rel"])


def detect_volume_spikes(df, threshold=3.0):
    monthly = df.groupby("month").size().rename("comments")
    months = pd.period_range(monthly.index.min(), monthly.index.max(), freq="M").strftime("%Y-%m")
    monthly = monthly.reindex(months, fill_value=0)
    median = monthly.median()
    spread = max(1.4826 * (monthly - median).abs().median(), 1.0)
    table = monthly.to_frame()
    table["z_score"] = (monthly - median) / spread
    table["is_spike"] = table["z_score"] > threshold
    return table
