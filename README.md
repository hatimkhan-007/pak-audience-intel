# Audience & Campaign Intelligence Engine

**Author:** Uzair Khan
**Student ID:** F2024376506 | **Section:** A4
**Instructor:** Dr. Raja Noshad Jamil

A Streamlit application that analyses 2,600 scraped and sentiment-classified YouTube comments on a brand campaign video. It shows what attracts attention, what the audience says, which activity is unusual and what the marketing team should do next.

## Marketing questions answered

| Question | Method | Tab |
| --- | --- | --- |
| Which comments attract attention? | Likes and replies by sentiment, length and year | Engagement |
| How does the audience feel? | Sentiment mix and monthly trend | Audience voice |
| Which patterns are unusual? | Isolation Forest on comments, robust z-score on monthly volume | Unusual activity |
| Which themes should the brand address? | TF-IDF, SVD and K-Means clustering | Audience themes |
| What should the team do next? | Rule-based recommendations backed by evidence | Next steps |

## Project structure

```
app.py                          Streamlit interface
src/preprocess.py               Loading, spam removal, text cleaning
src/engagement_analysis.py      Engagement summaries
src/theme_clustering.py         Audience theme clustering
src/anomaly.py                  Unusual comments and volume spikes
src/recommendations.py          Action generator
data/classified_comments.csv    Main dataset (2,600 comments with sentiment)
data/raw_comments.csv           Original scraped comments
data/spam_comments.csv          Comments flagged as spam
data/review_sample.csv          105 comments for manual label review
data/eda_*.csv                  Descriptive statistics from the EDA step
```

## Run

```
pip install -r requirements.txt
streamlit run app.py
```

## Key results

- 71.9% of comments are negative and they hold 71.4% of all likes.
- 129 comments (5%) are flagged as unusual, mostly because of very high likes.
- Six months show comment spikes; the largest is September 2025 (189 comments).
- Eight themes were found, including toxic masculinity debate, lost customers and razor buying.

## Limitations

- All comments come from one video, so content types and platforms cannot be compared.
- The silhouette score is low (0.08), which is normal for short, overlapping comments; treat themes as guides.
- Sentiment is model-predicted and misses sarcasm; `manual_label` in the review sample is still empty.
- 37 comments with no letters or numbers (emoji only) are excluded from the analysis.
