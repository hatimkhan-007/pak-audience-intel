import pytest
from campaign_engine import nlp

@pytest.mark.parametrize("text,topic", [
    ("Price please?", "Price inquiry"), ("Is this available in Karachi?", "Availability"),
    ("Very beautiful dress!", "Praise"), ("Price bohat zyada hai.", "Price concern"),
    ("Delivery kitne din mein hogi?", "Delivery inquiry"), ("Any discount on this suit?", "Discount request"),
    ("Ordered last week, still waiting.", "Delivery complaint"), ("Inbox me details send kar dein.", "Purchase intent"),
    ("قیمت بتائیں", "Price inquiry"), ("XL size mein milega?", "Sizing & fit"), ("Follow back please", "Other"),
])
def test_spec_examples(text, topic):
    assert nlp.classify_topic(text) == topic

def test_language_detection():
    assert nlp.detect_language("Very beautiful dress!") == "English"
    assert nlp.detect_language("Price bohat zyada hai") == "Roman Urdu"
    assert nlp.detect_language("بہت خوبصورت") == "Urdu"

def test_sentiment_and_intent():
    a = nlp.analyze("Ordered last week, still waiting.")
    assert a["sentiment"] == "Negative" and a["purchase_intent"] == "Post-purchase issue"
    assert nlp.analyze("Stunning 😍")["sentiment"] == "Positive"

def test_cluster_text_is_cross_lingual():
    assert nlp.cluster_text("Price please?") == nlp.cluster_text("قیمت بتائیں") == "price"
