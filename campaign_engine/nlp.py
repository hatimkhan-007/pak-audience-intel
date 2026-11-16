"""Lightweight, dependency-free comment understanding for Pakistani social media.

Handles English, Roman Urdu and Urdu script.  Returns language, topic,
sentiment and purchase intent for one comment.  Rule-based on purpose: it is
transparent (every decision can be explained) and works on code-mixed text
where off-the-shelf English models fail.
"""
from __future__ import annotations
import re
import unicodedata

TOPICS = [  # (name, theme)  -- order = tie-break priority
    ("Delivery complaint", "Fulfilment"),
    ("Price concern", "Pricing"),
    ("Purchase intent", "Purchase"),
    ("Sizing & fit", "Product"),
    ("Availability", "Product"),
    ("Discount request", "Pricing"),
    ("Delivery inquiry", "Fulfilment"),
    ("Fabric quality", "Product"),
    ("Price inquiry", "Pricing"),
    ("Praise", "General"),
    ("Other", "General"),
]
TOPIC_NAMES = [t for t, _ in TOPICS]
LANGUAGES = ["English", "Roman Urdu", "Urdu"]
SENTIMENTS = ["Positive", "Neutral", "Negative"]
INTENTS = ["Ready to buy", "Possible inquiry", "Post-purchase issue", "No intent"]

CITIES = ("karachi lahore islamabad rawalpindi multan faisalabad peshawar quetta "
          "sialkot gujranwala hyderabad").split()
_CITY_RE = re.compile(r"\b(" + "|".join(CITIES) + r")\b")

# --- Roman-Urdu spelling variants -> canonical form --------------------------
_VARIANTS = {
    "bohat": "bohat", "bahut": "bohat", "boht": "bohat", "bht": "bohat", "bohot": "bohat", "bhut": "bohat",
    "zyada": "zyada", "ziada": "zyada", "zyadah": "zyada", "zada": "zyada", "ziyada": "zyada",
    "mehnga": "mehnga", "mehngi": "mehnga", "mahnga": "mehnga", "mahngi": "mehnga",
    "mehenga": "mehnga", "mehengi": "mehnga", "mehngay": "mehnga", "menga": "mehnga",
    "kitne": "kitne", "kitny": "kitne", "kitnay": "kitne", "kitni": "kitne", "kitna": "kitne", "ktny": "kitne",
    "nahi": "nahi", "nahin": "nahi", "nai": "nahi", "nhi": "nahi", "nahe": "nahi",
    "dein": "dein", "den": "dein", "dain": "dein", "dayn": "dein", "dejiye": "dein", "dijiye": "dein",
    "karen": "karen", "karain": "karen", "krain": "karen", "kren": "karen", "karein": "karen", "kryn": "karen",
    "mein": "mein", "mai": "mein",
    "chahiye": "chahiye", "chahie": "chahiye", "chahye": "chahiye", "chaiye": "chahiye", "chahiyea": "chahiye",
    "kapra": "kapra", "kapray": "kapra", "kapre": "kapra", "kaprey": "kapra",
    "milega": "milega", "milay": "milega", "milegi": "milega", "mile": "milega", "milta": "milega", "milti": "milega",
    "kesa": "kaisa", "kesi": "kaisa", "kaisi": "kaisa", "kaise": "kaisa", "kese": "kaisa", "kaisa": "kaisa",
    "acha": "acha", "achi": "acha", "achha": "acha", "achhi": "acha", "accha": "acha", "acchi": "acha",
    "hy": "hai", "he": "hai", "hay": "hai", "hain": "hai", "hai": "hai",
    "kia": "kya", "kiya": "kya", "kya": "kya",
    "btao": "batao", "bata": "batao", "batain": "batao", "batayen": "batao", "btaen": "batao", "batao": "batao",
    "pohancha": "pohancha", "pohanchi": "pohancha", "pohnchi": "pohancha", "pahunchi": "pohancha", "pahuncha": "pohancha",
    "plz": "please", "pls": "please", "plzz": "please", "pleasee": "please",
}
_ROMAN_MARKERS = set("""hai hain ho hoga hogi hogaa kya kia kitne kitna kitni kab kahan kahaan kaise kaisa
 mein ka ki ke ko se par pe nahi nai bohat zyada thoda aap ap mujhe mujhy hum yeh ye woh wo is us
 chahiye chahie dein den karen karein kar karo kijiye lena leni lun lungi milega milegi mil
 abhi tak phir bhi lekin magar aur sab bhut bht boht kapra kapre rang joda
 mehnga mehngi sasta batao bata bhej bhejein bhejain inbox shukriya mashallah khoobsurat
 pyara pyari acha achi kamal zabardast pohancha pohanchi kiya kiye tha thi hue hui""".split())

_ARABIC_RE = re.compile(r"[\u0600-\u06FF\u0750-\u077F]")
_URL_RE = re.compile(r"https?://\S+|www\.\S+")
_MENTION_RE = re.compile(r"@\w+")
_EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF\u2764\uFE0F]")
_REPEAT_RE = re.compile(r"(.)\1{2,}")


def normalize(text: str) -> str:
    """Lowercase, strip urls/mentions, squeeze repeats and canonicalise Roman Urdu spellings."""
    t = unicodedata.normalize("NFKC", str(text)).lower()
    t = _URL_RE.sub(" ", t)
    t = _MENTION_RE.sub(" ", t)
    t = _REPEAT_RE.sub(r"\1\1", t)
    toks = re.findall(r"[\w']+|[^\w\s]", t, flags=re.UNICODE)
    toks = [_VARIANTS.get(w, w) for w in toks]
    return " ".join(toks)


def detect_language(text: str) -> str:
    letters = [c for c in str(text) if c.isalpha()]
    if not letters:
        return "English"
    arabic = sum(1 for c in letters if _ARABIC_RE.match(c))
    if arabic / len(letters) > 0.4:
        return "Urdu"
    words = re.findall(r"[a-z']+", normalize(text))
    if not words:
        return "English"
    hits = sum(1 for w in words if w in _ROMAN_MARKERS)
    # ambiguous short tokens that are also English words must not trigger alone
    strong = [w for w in words if w in _ROMAN_MARKERS and w not in {"is", "us", "ya", "se", "par", "pe", "me", "ho", "ko", "ka", "ki", "ke", "to", "order", "inbox", "or", "hum", "main", "ab"}]
    if len(strong) >= 1 and hits / len(words) >= 0.2:
        return "Roman Urdu"
    return "English"


# ------------------------- topic rules ---------------------------------------
def _c(*pats):
    return [re.compile(p) for p in pats]


_RULES = {
    "Delivery complaint": (4, _c(
        r"still waiting", r"not (yet )?(received|delivered|arrived|come)", r"(abhi|ab) tak.{0,25}nahi",
        r"order.{0,40}(last week|days ago|din ho|hafta|hafte|week)", r"waiting.{0,30}(order|parcel|delivery)",
        r"(late|delay\w*).{0,25}(deliver|parcel|order)", r"deliver\w*.{0,25}(bohat late|too late|very late|delay)",
        r"parcel.{0,25}(nahi|not|lost)", r"wrong (size|item|colou?r|piece)", r"no (response|reply)",
        r"(customer|care|support).{0,25}(reply|respond|response|jawab).{0,15}(nahi|not|no)",
        r"ہفتہ", r"ابھی تک.{0,12}نہیں", r"نہیں پہنچا", r"نہیں ملا", r"تاخیر")),
    "Price concern": (4, _c(
        r"too (expensive|much|costly|high)", r"(bohat|itna|itni|very) (zyada|mehnga|costly|expensive|high)",
        r"mehnga", r"overpriced", r"price.{0,12}(very |too )?high", r"price.{0,12}(kam|less|reduce|lower)",
        r"price.{0,20}zyada", r"zyada.{0,12}price", r"not worth", r"قیمت بہت زیادہ", r"مہنگ", r"اتنی مہنگی")),
    "Discount request": (3, _c(
        r"discount", r"\bsale\b", r"\boffers?\b", r"promo", r"coupon", r"voucher", r"\bkam kar",
        r"\bdeal\b", r"bargain", r"cheaper", r"\bsasta\b", r"رعایت", r"ڈسکاؤنٹ", r"سیل", r"آفر")),
    "Availability": (3, _c(
        r"availab", r"in stock", r"\bstock\b", r"\bstores?\b", r"outlet", r"branch", r"sold out", r"restock",
        r"dobara", r"دستیاب", r"اسٹاک", r"اسٹور", r"ملے گا", r"مل جائے گا")),
    "Sizing & fit": (3, _c(
        r"\bsizes?\b", r"sizing", r"\b(xs|xl|xxl|xxxl|small|medium|large|extra large)\b",
        r"\blength\b", r"\bchest\b", r"\bbust\b", r"\bfitting\b", r"\bfit\b", r"\bloose\b", r"\btight\b",
        r"\bchota\b|\bchhota\b|\bbara\b|\bbada\b", r"naap", r"measure", r"سائز", r"ناپ", r"لارج")),
    "Fabric quality": (3, _c(
        r"fabric", r"\bkapra\b", r"quality", r"material", r"shrink|sikar", r"\bfade|colou?r run|rang (utar|nikal)",
        r"transparent|see.?through", r"stitch", r"\bgsm\b", r"کپڑ", r"معیار")),
    "Delivery inquiry": (2, _c(
        r"deliver", r"shipping", r"courier", r"\bcod\b", r"cash on delivery", r"kitne din", r"how many days",
        r"how long", r"ڈلیوری", r"کتنے دن")),
    "Price inquiry": (2, _c(
        r"\bprice", r"\brate\b", r"how much", r"\bcost\b", r"kitne ka", r"kitne ki\b", r"\bpkr\b", r"\brs\.?\s?\d",
        r"قیمت", r"کتنے کا", r"ریٹ")),
    "Purchase intent": (4, _c(
        r"inbox", r"\bdm\b", r"whats ?app|watsapp", r"details? (send|bhej|dein|chahiye)", r"send (me )?(the )?details",
        r"(i )?(want|need) (to )?(buy|order|this|it)", r"how (to|can i) (order|buy)", r"order kaise",
        r"mujhe .{0,25}chahiye", r"\bchahiye\b", r"lena chahti|lena chahta|lena hai|le lun", r"book (kar|this|it)",
        r"contact (number|no)", r"ان باکس", r"چاہیے", r"خریدنا", r"آرڈر کیسے", r"رابطہ", r"واٹس")),
    "Praise": (2, _c(
        r"beautiful|gorgeous|stunning|lovely|love (it|this)|pretty|elegant|amazing|awesome|\bnice\b|superb|classy",
        r"perfect|fabulous|\bwow\b|ma ?sha ?allah|khoobsurat|khubsurat|pyara|pyari|kamal|zabardast|behtareen",
        r"\bacha\b|\bbest\b|\bgreat\b|خوبصورت|ماشاءاللہ|پیارا|پیاری|زبردست|بہت اچھا", r"[😍❤🥰💕😘🔥👌]")),
}
_PRIORITY = {name: i for i, (name, _) in enumerate(TOPICS)}


def classify_topic(text: str) -> str:
    t = normalize(text)
    scores = {}
    for topic, (weight, pats) in _RULES.items():
        n = sum(1 for p in pats if p.search(t))
        if n:
            scores[topic] = weight * min(n, 2)
    if _CITY_RE.search(t):
        scores["Availability"] = scores.get("Availability", 0) + 1
    if not scores:
        return "Other"
    return max(scores, key=lambda k: (scores[k], -_PRIORITY[k]))


# ------------------------- sentiment -------------------------------------------
_POS = set("""beautiful gorgeous stunning lovely love pretty elegant amazing awesome nice superb classy perfect
 fabulous wow great good best excellent thanks thank shukriya mashallah khoobsurat khubsurat pyara pyari kamal
 zabardast behtareen acha happy مزے خوبصورت ماشاءاللہ پیارا پیاری زبردست شکریہ""".split())
_NEG = set("""expensive mehnga overpriced late delay delayed waiting worst bad poor fake scam fraud disappointed
 disappointing terrible horrible rude useless wrong cheap waste pathetic ghalat bekar fazool مہنگ مہنگا مہنگی
 تاخیر بیکار""".split())
_TOPIC_PRIOR = {"Delivery complaint": -0.7, "Price concern": -0.45, "Praise": 0.55}


def sentiment_score(text: str, topic: str | None = None) -> float:
    t = normalize(text)
    words = re.findall(r"[\w']+", t)
    score = 0.0
    for i, w in enumerate(words):
        negated = i > 0 and words[i - 1] in {"not", "no", "never", "nahi", "na"}
        if w in _POS:
            score += -0.4 if negated else 0.4
        elif w in _NEG:
            score += 0.25 if negated else -0.4
    score += 0.2 * len(re.findall(r"[😍❤🥰💕😘🔥👌]", str(text)))
    score -= 0.3 * len(re.findall(r"[😡😠👎😤😞😢]", str(text)))
    if topic in _TOPIC_PRIOR:
        score += _TOPIC_PRIOR[topic]
    return max(-1.0, min(1.0, score))


def sentiment_label(score: float) -> str:
    return "Positive" if score >= 0.25 else "Negative" if score <= -0.25 else "Neutral"


_INTENT = {
    "Purchase intent": "Ready to buy",
    "Delivery complaint": "Post-purchase issue",
    "Praise": "No intent",
    "Other": "No intent",
}


def intent_for(topic: str) -> str:
    return _INTENT.get(topic, "Possible inquiry")


def analyze(text: str) -> dict:
    topic = classify_topic(text)
    score = sentiment_score(text, topic)
    return {
        "language_type": detect_language(text),
        "topic": topic,
        "sentiment": sentiment_label(score),
        "sentiment_score": round(score, 3),
        "purchase_intent": intent_for(topic),
    }


# ------------------------- text for clustering -----------------------------------
# Cross-lingual concept map: English / Roman Urdu / Urdu words -> one concept token,
# so "قیمت", "price" and "rate kya hai" land in the same region of the vector space.
_CONCEPTS = {
    "price": "price rate qeemat قیمت ریٹ cost pkr kitne_ka", "expensive": "expensive mehnga overpriced costly مہنگا مہنگی مہنگ zyada",
    "delivery": "delivery deliver delivered shipping courier ڈلیوری cod charges", "order": "order ordered orders parcel آرڈر",
    "discount": "discount sale offer promo coupon voucher deal ڈسکاؤنٹ رعایت سیل آفر kam",
    "available": "available availability stock restock restocked store outlet branch milega دستیاب اسٹاک اسٹور dobara",
    "size": "size sizes xsize naap ناپ سائز length chart fit fitting loose tight شیٹ لارج",
    "fabric": "fabric kapra material quality cotton lawn shrink کپڑا کپڑے کپڑ معیار کاٹن لان wash faded transparent",
    "inbox": "inbox dm whatsapp watsapp details contact number ان باکس تفصیل واٹس",
    "want": "want need chahiye lena lun buy purchase چاہیے خریدنا",
    "praise": "beautiful gorgeous stunning lovely love pretty elegant amazing awesome nice superb perfect wow mashallah "
              "khoobsurat khubsurat pyara pyari kamal zabardast acha خوبصورت ماشاءاللہ پیارا پیاری زبردست اچھا",
    "waiting": "waiting waited انتظار", "late": "late delay delayed تاخیر", "still": "still abhi ابھی",
    "week": "week hafta hafte ہفتہ days", "not": "not nahi نہیں no na", "wrong": "wrong ghalat",
    "reply": "reply respond response jawab care customer", "tell": "kitne",
    "social": "first follow back giveaway model who shot ماڈل کون kahan shoot kaun",
}
CONCEPT_MAP = {w: c for c, ws in _CONCEPTS.items() for w in ws.split()}
_STOP = set("""the is in it this that you your for of to a an on at and or be are was do does can will i me my we
 hai ka ki ke mein ye yeh is par kya ho hogi hoga kab se aur bhi ko hain tha thi hue hui kar karen karein dein
 batao bhej send please pls plz asap yaar ji tak ek koi kuch aap ap mujhe hum is us wo woh how what when where which many would any much
 اس کی کا کے ہے میں یہ کیا ہو گا گی ہیں اور سے کو پر بھی ایک کوئی کچھ آپ مجھے بتائیں کریں دیں ہوگی ہوگا ہوں""".split())


def cluster_text(text: str) -> str:
    """Language-agnostic 'meaning tokens': cities / sizes / numbers masked, words mapped to
    concepts, filler removed - so clusters form around *what is asked*, not the language."""
    t = normalize(text)
    t = _CITY_RE.sub(" xcity ", t)
    t = re.sub(r"\b(xs|xl|xxl|xxxl|small|medium|large|extra large)\b", " xsize ", t)
    t = re.sub(r"\d+(\.\d+)?", " xnum ", t)
    t = t.replace("kitne ka", "price").replace("کتنے کا", "price")
    t = _EMOJI_RE.sub(" praise ", t)
    words = re.findall(r"[\w]+", t, flags=re.UNICODE)
    out = []
    for w in words:
        w = CONCEPT_MAP.get(w, w)
        if w in _STOP or w in ("ordered",):
            continue
        out.append(w)
    return " ".join(out)
