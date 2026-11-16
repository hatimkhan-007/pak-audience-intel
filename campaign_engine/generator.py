"""Simulated Table A (posts) and Table B (comments) for women's lawn-suit campaigns.

IMPORTANT: everything produced here is SIMULATED.  Brand names are fictional.
The records exist so the engine can be demonstrated end-to-end; real public data
can be loaded with `python manage.py import ...` and is stored with
provenance='observed' so the two are never mixed up.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

BRANDS = {
    #  name           followers(IG)  trait
    "Noor Lawn":     (2_400_000, "premium"),       # price-concern heavy
    "Zari House":    (1_700_000, "delivery"),      # delivery problems
    "Rang Mahal":    (1_300_000, "discount"),      # discount hunters
    "Mehr Couture":  (  900_000, "sizing"),        # sizing / fit questions
    "Sitara Studio": (  650_000, "stock"),         # sells out, availability asks
    "Gulabo Prints": (3_100_000, "balanced"),      # biggest reach
}
PLATFORMS = {"Instagram": 1.0, "TikTok": 0.55, "Facebook": 0.8}
PLATFORM_WEIGHTS = {"Instagram": 0.48, "TikTok": 0.24, "Facebook": 0.28}
CAMPAIGNS = ["Eid Collection", "11.11 Sale", "12.12 Sale", "Summer Lawn Launch", "Spring Festive Edit"]
CONTENT_TYPES = ["Reel", "Product Photo", "Influencer Post", "Styling Video", "Sale Announcement", "Eid Campaign"]
ALLOWED = {
    "Instagram": CONTENT_TYPES,
    "Facebook": ["Product Photo", "Sale Announcement", "Eid Campaign", "Influencer Post", "Reel"],
    "TikTok": ["Reel", "Styling Video", "Influencer Post"],
}
CATEGORIES = ["Lawn suit", "Unstitched lawn", "Embroidered lawn", "Printed lawn"]

# content type: (reach multiplier, like rate, comment rate, share rate)
CT = {
    "Reel":              (1.9, 0.045, 0.0040, 0.0070),
    "Product Photo":     (0.7, 0.032, 0.0055, 0.0015),
    "Influencer Post":   (1.2, 0.040, 0.0060, 0.0040),
    "Styling Video":     (1.5, 0.050, 0.0050, 0.0055),
    "Sale Announcement": (0.9, 0.028, 0.0120, 0.0030),
    "Eid Campaign":      (1.3, 0.050, 0.0070, 0.0050),
}
PLAT_RATE = {"Instagram": 1.0, "TikTok": 1.5, "Facebook": 0.6}

BASE_TOPIC = {
    "Price inquiry": .17, "Price concern": .05, "Fabric quality": .07, "Sizing & fit": .07,
    "Delivery inquiry": .07, "Delivery complaint": .03, "Discount request": .10, "Availability": .10,
    "Purchase intent": .09, "Praise": .22, "Other": .03,
}

T = {  # templates: topic -> language -> list
"Price inquiry": {
  "en": ["Price please?", "What is the price of this suit?", "Price?", "How much for this lawn 3 piece?", "price of {code}?", "Can you tell me the price?"],
  "ru": ["Price bata dein", "Price kya hai is ka?", "Kitne ka hai ye suit?", "Rate kya hai?", "Price pls", "Is ka price batao"],
  "ur": ["قیمت بتائیں", "اس کی قیمت کیا ہے؟", "یہ کتنے کا ہے؟"]},
"Price concern": {
  "en": ["Way too expensive for lawn.", "Overpriced honestly.", "Price is too high for this quality.", "Not worth this price.", "Prices keep going up every season"],
  "ru": ["Price bohat zyada hai.", "Itna mehnga kyun hai?", "Bohat mehngi hai yaar", "Quality ke hisaab se price zyada hai", "Price kam karen, bohat zyada hai"],
  "ur": ["قیمت بہت زیادہ ہے", "بہت مہنگا ہے", "اتنی مہنگی قیمت؟"]},
"Fabric quality": {
  "en": ["What fabric is this?", "Is it pure cotton or lawn?", "How is the fabric quality?", "Does it shrink after washing?", "Is the fabric transparent?", "Last season the colour faded after wash, is the material better now?"],
  "ru": ["Fabric kaisa hai? Lawn hai ya cotton?", "Kapra kaisa hai?", "Fabric quality kesi hai?", "Kya ye kapra dhulne ke baad sikarta hai?", "Kapre ki quality kaisi hai"],
  "ur": ["کپڑا کیسا ہے؟", "کپڑا کون سا ہے لان یا کاٹن؟", "کپڑے کا معیار کیسا ہے؟"]},
"Sizing & fit": {
  "en": ["Is this available in XL?", "Please share the size chart", "What is the shirt length?", "Is medium loose or fitted?", "Do you have extra large?", "Size ran small last time, any fix?"],
  "ru": ["Size chart bhej dein", "XL size mein milega?", "Shirt ki length kitni hai?", "Medium size mein available hai?", "Size chota aya tha last time"],
  "ur": ["سائز کتنا ہے؟", "کیا یہ ایکسٹرا لارج میں ملے گا؟", "ناپ بتا دیں"]},
"Delivery inquiry": {
  "en": ["How many days for delivery?", "Do you deliver to {city}?", "What are the delivery charges?", "Is COD available?", "How long will shipping take?"],
  "ru": ["Delivery kitne din mein hogi?", "{city} mein delivery kab tak hogi?", "Delivery charges kitne hain?", "COD hai?", "Courier kitne din lega?"],
  "ur": ["ڈلیوری کتنے دن میں ہوگی؟", "لاہور میں ڈلیوری کا کتنا وقت لگے گا؟"]},
"Delivery complaint": {
  "en": ["Ordered last week, still waiting.", "Order not received yet, no reply from customer care.", "Delivery is very late!", "Got the wrong size, nobody is responding", "My parcel is still not delivered after 10 days"],
  "ru": ["Order kiya tha last week, abhi tak nahi aya.", "Mera parcel abhi tak nahi pohancha", "Delivery bohat late hai", "Customer care reply nahi kar raha order ka", "Order ko 2 hafte ho gaye abhi tak nahi mila"],
  "ur": ["آرڈر کیے ہوئے ہفتہ ہو گیا ابھی تک نہیں ملا", "میرا آرڈر ابھی تک نہیں پہنچا"]},
"Discount request": {
  "en": ["Any discount on this suit?", "When is the sale?", "Is there a promo code?", "Will it be on sale on 11.11?", "Please give some discount", "Any offer for bulk order?"],
  "ru": ["Koi discount hai is par?", "Sale kab lag rahi hai?", "Kuch kam karen na", "11.11 par discount milega?", "Promo code hai koi?"],
  "ur": ["کوئی ڈسکاؤنٹ ہے؟", "سیل کب لگے گی؟", "کیا اس پر رعایت ملے گی؟"]},
"Availability": {
  "en": ["Is this available in {city}?", "Is it in stock?", "Do you have a store in {city}?", "When will it be restocked?", "Available in stores or online only?", "Sold out already? Please restock {code}"],
  "ru": ["Kya ye {city} mein available hai?", "Stock mein hai?", "Store {city} mein hai?", "Ye suit abhi available hai?", "Dobara kab aye ga stock?"],
  "ur": ["کیا یہ کراچی میں دستیاب ہے؟", "یہ اسٹاک میں ہے؟", "اسٹور میں مل جائے گا؟"]},
"Purchase intent": {
  "en": ["Inbox me details", "I want to order this, how?", "Please send details on WhatsApp", "DM sent, please reply", "I need 2 of {code}", "Contact number please, I want to buy"],
  "ru": ["Inbox me details send kar dein.", "Order kaise karun?", "Mujhe ye chahiye, WhatsApp number dein", "Main ye lena chahti hun", "DM kiya hai please reply karen"],
  "ur": ["مجھے یہ چاہیے ان باکس میں تفصیل بھیجیں", "آرڈر کیسے کریں؟", "میں یہ خریدنا چاہتی ہوں"]},
"Praise": {
  "en": ["Very beautiful dress!", "Gorgeous colours 😍", "Love this design", "Stunning!", "So elegant ❤️", "Absolutely perfect for Eid", "Wow 🔥"],
  "ru": ["Bohat khoobsurat!", "Mashallah bohat pyara hai", "Colour kamal ka hai", "Zabardast design 😍", "Bohat acha laga"],
  "ur": ["بہت خوبصورت", "ماشاءاللہ بہت پیارا ہے", "رنگ بہت اچھا ہے"]},
"Other": {
  "en": ["First", "Follow back please", "Who is the model?", "Giveaway?", "🔥🔥🔥", "Which city is this shot in?"],
  "ru": ["Model kaun hai?", "Follow back karen", "Ye kahan shoot hua?", "Giveaway kab hai"],
  "ur": ["ماڈل کون ہے؟"]},
}
CITIES_FREQ = {"Karachi": .27, "Lahore": .20, "Islamabad": .14, "Rawalpindi": .06, "Multan": .08,
               "Faisalabad": .08, "Peshawar": .07, "Quetta": .03, "Sialkot": .04, "Gujranwala": .03}
SUFFIX = ["", "", "", "", " plz", " please", " 🙏", " ??", " asap", " 🙄"]


def _topic_weights(brand_trait, ctype, campaign, anomaly):
    w = dict(BASE_TOPIC)
    if ctype == "Sale Announcement":
        for k, m in {"Discount request": 2.2, "Price inquiry": 1.4, "Availability": 1.5, "Praise": .5}.items(): w[k] *= m
    elif ctype == "Styling Video":
        for k, m in {"Fabric quality": 2.0, "Sizing & fit": 1.8, "Praise": 1.1}.items(): w[k] *= m
    elif ctype == "Influencer Post":
        for k, m in {"Purchase intent": 1.5, "Price inquiry": 1.2, "Other": 3}.items(): w[k] *= m
    elif ctype == "Reel":
        w["Praise"] *= 1.3; w["Other"] *= 2
    elif ctype == "Eid Campaign":
        for k, m in {"Availability": 1.4, "Delivery inquiry": 1.6, "Purchase intent": 1.2}.items(): w[k] *= m
    if campaign in ("11.11 Sale", "12.12 Sale"):
        for k, m in {"Discount request": 1.7, "Delivery complaint": 1.8, "Delivery inquiry": 1.3}.items(): w[k] *= m
    if campaign == "Eid Collection":
        for k, m in {"Availability": 1.3, "Delivery inquiry": 1.4}.items(): w[k] *= m
    trait = {"premium": {"Price concern": 4.5, "Price inquiry": 1.2},
             "delivery": {"Delivery complaint": 6.0, "Delivery inquiry": 1.5},
             "discount": {"Discount request": 2.6},
             "sizing": {"Sizing & fit": 2.8, "Fabric quality": 1.2},
             "stock": {"Availability": 2.6},
             "balanced": {}}[brand_trait]
    for k, m in trait.items(): w[k] *= m
    if anomaly == "complaint_storm":
        w["Delivery complaint"] *= 14; w["Price concern"] *= 5
    if anomaly == "discount_frenzy":
        w["Discount request"] *= 8; w["Availability"] *= 3
    s = sum(w.values())
    return list(w.keys()), np.array([v / s for v in w.values()])


def _render(rng, topic, lang_p):
    lang = rng.choice(["en", "ru", "ur"], p=lang_p)
    text = rng.choice(T[topic][lang])
    city = rng.choice(list(CITIES_FREQ), p=np.array(list(CITIES_FREQ.values())) / sum(CITIES_FREQ.values()))
    text = text.replace("{city}", city).replace("{code}", f"{rng.choice(['LN','ZH','RM','MC'])}-{rng.integers(100, 999)}")
    if lang != "ur":
        if rng.random() < 0.18: text = text.lower()
        if rng.random() < 0.05 and len(text) > 6:
            i = int(rng.integers(1, len(text) - 1)); text = text[:i] + text[i + 1:]       # typo
        text += str(rng.choice(SUFFIX))
    return text


def generate(n_posts=3000, seed=42):
    rng = np.random.default_rng(seed)
    brands = list(BRANDS)
    accounts = [(b, p, int(BRANDS[b][0] * PLATFORMS[p] * rng.uniform(0.85, 1.15))) for b in brands for p in PLATFORMS]
    acc_followers = {(b, p): f for b, p, f in accounts}

    anomalies = rng.choice(n_posts, int(n_posts * 0.04), replace=False)
    kinds = ["viral", "flop", "complaint_storm", "discount_frenzy"]
    anomaly_of = {int(i): kinds[k % 4] for k, i in enumerate(anomalies)}

    posts, comments, truth = [], [], []
    for i in range(n_posts):
        brand = brands[rng.integers(len(brands))]
        trait = BRANDS[brand][1]
        platform = rng.choice(list(PLATFORM_WEIGHTS), p=list(PLATFORM_WEIGHTS.values()))
        ctype = rng.choice(ALLOWED[platform])
        campaign = rng.choice(CAMPAIGNS, p=[.28, .2, .18, .2, .14])
        if ctype == "Eid Campaign" and campaign in ("11.11 Sale", "12.12 Sale"): campaign = "Eid Collection"
        if ctype == "Sale Announcement" and campaign == "Eid Collection": campaign = "11.11 Sale"
        category = rng.choice(CATEGORIES, p=[.4, .25, .2, .15])
        days = int(rng.integers(1, 61))
        followers = acc_followers[(brand, platform)]
        reach_m, lr, cr, sr = CT[ctype]
        lr *= PLAT_RATE[platform]; cr *= (1.15 if platform == "Facebook" else 1.0); sr *= PLAT_RATE[platform]
        sale_boost = 1.12 if campaign in ("11.11 Sale", "12.12 Sale") else 1.0
        age = 1 - np.exp(-days / 2.0)
        views = followers * 0.18 * reach_m * rng.lognormal(0, 0.55) * sale_boost
        ln = rng.lognormal(0, 0.25, 3)
        likes, comm, shares = views * lr * ln[0] * age, views * cr * ln[1] * age, views * sr * ln[2] * age
        kind = anomaly_of.get(i)
        if kind == "viral": views *= rng.uniform(5, 9); likes *= rng.uniform(5, 9); shares *= rng.uniform(6, 12); comm *= rng.uniform(4, 8)
        elif kind == "flop": views *= 0.12; likes *= 0.1; comm *= 0.12; shares *= 0.1
        elif kind == "complaint_storm": comm *= rng.uniform(5, 9); likes *= 0.8
        elif kind == "discount_frenzy": comm *= rng.uniform(6, 10); shares *= 2
        has_views = ctype in ("Reel", "Styling Video") or platform == "TikTok" or (platform == "Instagram" and rng.random() < .3)
        has_shares = platform != "Instagram" or rng.random() < 0.7
        pid = f"P{i + 1:04d}"
        posts.append(dict(post_id=pid, brand=brand, platform=platform, campaign=campaign, content_type=ctype,
                          product_category=category, followers=followers, likes=int(max(likes, 1)),
                          comments_count=int(max(comm, 2)), shares=int(shares) if has_shares else None,
                          views=int(views) if has_views else None, days_since_post=days))
        n_c = int(min(posts[-1]["comments_count"], rng.integers(3, 17) + (8 if kind in ("complaint_storm", "discount_frenzy") else 0)))
        names, probs = _topic_weights(trait, ctype, campaign, kind)
        lang_p = [.42, .45, .13] if platform != "Facebook" else [.34, .48, .18]
        for t in rng.choice(names, size=n_c, p=probs):
            text = _render(rng, t, lang_p)
            if rng.random() < 0.08:   # mixed-intent comment
                t2 = rng.choice(["Availability", "Delivery inquiry", "Discount request", "Price inquiry"])
                text += " " + _render(rng, t2, [.5, .5, 0])
            comments.append(dict(post_id=pid, comment_text=text))
            truth.append(dict(post_id=pid, true_topic=t))
    return pd.DataFrame(posts), pd.DataFrame(comments), pd.DataFrame(truth), pd.Series(anomaly_of).rename("kind")
