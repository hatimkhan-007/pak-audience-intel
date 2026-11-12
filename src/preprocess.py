import re
import pandas as pd
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def clean_text(text):
    text = re.sub(r"https?://\S+", " ", str(text).lower())
    text = re.sub(r"[^a-z0-9\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_data():
    df = pd.read_csv(DATA_DIR / "classified_comments.csv")
    spam = pd.read_csv(DATA_DIR / "spam_comments.csv")
    df = df[~df["comment_id"].isin(spam["comment_id"])].copy()
    df["published_at"] = pd.to_datetime(df["published_at"], utc=True)
    df["year"] = df["published_at"].dt.year
    df["month"] = df["published_at"].dt.strftime("%Y-%m")
    df["word_count"] = df["clean_comment"].str.split().str.len()
    df["engagement"] = df["like_count"] + df["reply_count"]
    df["text_for_model"] = df["clean_comment"].map(clean_text)
    df = df[df["text_for_model"].str.len() > 0]
    return df.reset_index(drop=True)
