import pandas as pd
import streamlit as st

from src.anomaly import detect_comment_anomalies, detect_volume_spikes
from src.engagement_analysis import length_bucket, summarize, top_comments
from src.preprocess import DATA_DIR, load_data
from src.recommendations import build_recommendations
from src.theme_clustering import cluster_comments

st.set_page_config(page_title="Campaign Intelligence Engine", layout="wide")


@st.cache_data
def get_data():
    return load_data()


@st.cache_data
def get_anomalies(df, contamination):
    return detect_comment_anomalies(df, contamination)

@st.cache_data
def get_clusters(df, k):
    return cluster_comments(df, k)


df_all = get_data()
st.title("Audience & Campaign Intelligence Engine")
st.caption("YouTube comments on a brand campaign video | Scraped and classified data")

with st.sidebar:
    st.header("Filters")
    sentiments = st.multiselect("Sentiment", ["Positive", "Neutral", "Negative"], default=["Positive", "Neutral", "Negative"])
    years = st.slider("Comment year", int(df_all["year"].min()), int(df_all["year"].max()),
                      (int(df_all["year"].min()), int(df_all["year"].max())))
    k = st.slider("Number of audience themes", 4, 12, 8)
    contamination = st.slider("Unusual comment share", 0.02, 0.10, 0.05, 0.01)

anomalies_all = get_anomalies(df_all, contamination)
mask = df_all["sentiment"].isin(sentiments) & df_all["year"].between(*years)
df = df_all[mask]
anomalies = anomalies_all[mask]

if len(df) < k * 5:
    st.warning("Not enough comments for the selected filters.")
    st.stop()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Comments", f"{len(df):,}")
c2.metric("Negative share", f"{(df['sentiment'] == 'Negative').mean():.1%}")
c3.metric("Median likes", f"{df['like_count'].median():.0f}")
c4.metric("Comments with replies", f"{(df['reply_count'] > 0).mean():.1%}")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Engagement", "Audience voice", "Unusual activity", "Audience themes", "Next steps",
])

with tab1:
    st.subheader("Which kinds of comments attract attention?")
    left, right = st.columns(2)
    by_sent = summarize(df, "sentiment")
    left.markdown("**By sentiment**")
    left.bar_chart(by_sent["share_of_likes"])
    left.dataframe(by_sent, width="stretch")
    by_len = summarize(df.assign(length=length_bucket(df)), "length")
    right.markdown("**By comment length**")
    right.bar_chart(by_len["share_of_likes"])
    right.dataframe(by_len, width="stretch")
    st.markdown("**By year**")
    st.dataframe(summarize(df, "year").sort_index(), width="stretch")
    st.markdown("**Most liked comments**")
    st.dataframe(top_comments(df), width="stretch", hide_index=True)

with tab2:
    st.subheader("How does the audience feel over time?")
    st.bar_chart(df["sentiment"].value_counts(normalize=True).rename("share"))
    monthly = df.groupby(["month", "sentiment"]).size().unstack(fill_value=0)
    st.line_chart(monthly)

with tab3:
    st.subheader("Which patterns are unusual?")
    flagged = anomalies[anomalies["is_anomaly"]].sort_values("anomaly_score", ascending=False)
    st.markdown(f"**{len(flagged)} comments flagged for review**")
    st.dataframe(flagged[["clean_comment", "sentiment", "like_count", "reply_count", "reason"]].head(50),
                 width="stretch", hide_index=True)
    spikes = detect_volume_spikes(df)
    st.markdown("**Monthly comment volume**")
    st.bar_chart(spikes["comments"])
    st.dataframe(spikes[spikes["is_spike"]], width="stretch")

with tab4:
    st.subheader("Which audience themes should the brand address?")
    labelled, summary, score = get_clusters(df, k)
    st.metric("Silhouette score", f"{score:.2f}")
    st.dataframe(summary.round(3), width="stretch", hide_index=True)
    chosen = st.selectbox("Inspect a theme", summary["cluster"].tolist())
    st.dataframe(labelled[labelled["cluster"] == chosen][["clean_comment", "sentiment", "like_count"]].head(20),
                 width="stretch", hide_index=True)

with tab5:
    st.subheader("What should the team do next?")
    review = pd.read_csv(DATA_DIR / "review_sample.csv")
    recs = build_recommendations(df, summary, anomalies, detect_volume_spikes(df), int(review["manual_label"].isna().sum()))
    st.dataframe(recs, width="stretch", hide_index=True)
    st.download_button("Download recommendations", recs.to_csv(index=False), "recommendations.csv", "text/csv")
