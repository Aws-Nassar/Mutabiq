"""Arabic text normalization.

This module is responsible for producing the two representations of a fatwa
required by AGENTS.md:

1. text_display — shown to the user. **Never** touched. Callers must preserve
   the original byte-for-byte string.
2. text_search — used for matching only. Normalized conservatively to avoid
   mangling Arabic verbs (أصلي, صلاة) while collapsing trivial variants.

Do NOT over-stem. Over-aggressive normalization loses exact matches.
"""

from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# Tashkeel (diacritics) and tatweel
# ---------------------------------------------------------------------------
# Arabic diacritics range U+064B–U+0652 plus Sukun. Tatweel is U+0640.
_TASHKEEL_RE = re.compile(
    r"[\u064B\u064C\u064D\u064E\u064F\u0650\u0651\u0652\u06E1\u0670\u0610-\u061A\u0640]"
)

# ---------------------------------------------------------------------------
# Alef variants → ا
# ---------------------------------------------------------------------------
ALEF_NORMALIZE_MAP = str.maketrans(
    {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",  # Alef wasla
        "\u0672": "ا",  # Alef with wavy hamza above/below variants
        "\u0673": "ا",
        "\u0675": "ا",
    }
)

# ---------------------------------------------------------------------------
# Yaa variants → ي
# ---------------------------------------------------------------------------
YAA_NORMALIZE_MAP = str.maketrans({"ى": "ي", "ئ": "ي", "\u0620": "ي"})

# ---------------------------------------------------------------------------
# Taa marbuta variants → ه
# ---------------------------------------------------------------------------
TAA_MARBUTA_NORMALIZE_MAP = str.maketrans({"ة": "ه"})

# ---------------------------------------------------------------------------
# Digits: Arabic-Indic → European, and others collapsed
# ---------------------------------------------------------------------------
ARABIC_INDIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
EUROPEAN_DIGITS = "0123456789"
DIGIT_TRANSLATION = str.maketrans(ARABIC_INDIC_DIGITS, EUROPEAN_DIGITS)

# ---------------------------------------------------------------------------
# Arabic punctuation that can be safely stripped for search
# ---------------------------------------------------------------------------
ARABIC_PUNCTUATION = "،؛؟«»–_[]{}()…‹›·•"
PUNCT_MAP = str.maketrans(dict.fromkeys(ARABIC_PUNCTUATION, " "))

# Common non-Arabic punctuation and symbols to collapse
SYMBOL_MAP = str.maketrans({".": " ", ",": " ", ";": " ", ":": " ", "?": " ", "!": " ", '"': " ", "'": " ", "`": " ", "\u201C": " ", "\u201D": " ", "\u2018": " ", "\u2019": " ", "\u2010": " ", "\u2011": " ", "\u2012": " ", "\u2013": " ", "\u2014": " ", "\u2015": " ", "-": " ", "/": " ", "\\": " ", "|": " ", "@": " ", "#": " ", "$": " ", "%": " ", "^": " ", "&": " ", "*": " ", "(": " ", ")": " ", "[": " ", "]": " ", "{": " ", "}": " ", "<": " ", ">": " ", "=": " ", "+": " ", "~": " ", "_": " "})

# Whitespace collapse
_WHITESPACE_RE = re.compile(r"\s+")

# Common Arabic stopwords. Kept conservative — removing function words only.
# The goal is not topic modeling, it's improving precision without hurting recall.
ARABIC_STOPWORDS = {
    # particles / conjunctions
    "و", "ف", "في", "على", "من", "إلى", "الى", "عن", "ب", "ل", "ك",
    # negation and modal verbs
    "لا", "لم", "لن", "لو", "لولا", "ليس", "لست", "ليست", "ما",
    # pronouns
    "هو", "هي", "هما", "هم", "هن", "نحن", "أنت", "انتم", "انتن",
    "أنها", "انها", "أنه", "انه", "إنه", "إنها", "اني", "اننا",
    "الذي", "التي", "الذين", "اللاتي",
    "هذا", "هذه", "ذلك", "تلك", "هؤلاء", "أولئك",
    "به", "بها", "له", "لها", "لهم", "منه", "منها", "عليه", "عليها",
    "إليه", "إليها", "إليكم", "إياك",
    # verbs that carry no topical content
    "أن", "ان", "إن", "كان", "كانت", "يكون", "تكون", "كن", "كنت",
    "قد", "لقد", "ثم", "حتى", "عدم", "غير", "سوى", "سواء",
    # question words
    "هل", "هلا", "كيف", "متى", "أين", "أينما", "لماذا", # time / place / quantity function words
    "قبل", "بعد", "عند", "حين", "بين", "مع", "حول", "دون",
    "خلال", "ضد", "نحو", "بعض", "كل", "كافة", "بما", "بمن",
    "آخر", "اخر", "أولى", "اول", "أكثر", "اكثر", "أقل", "اقل",
    # connectors
    "أو", "او", "أم", "اما", "لكن", "بل", "بلا", "إما", "أما", "إلا",
    "ألا", "لما", "منذ", "كما", "فقط", "أيضا", "ايضا", "كذلك",
    # reflexive / emphatics
    "نفسه", "نفسها", "بعضهم", "بعضها",
    # honorific / family terms that appear in nearly every fatwa framing
    "بن", "ابن", "رضي", "الله", "تعالى",
}


def remove_tashkeel(s: str) -> str:
    """Remove Arabic diacritics (tashkeel) and tatweel."""
    if not s:
        return s
    return _TASHKEEL_RE.sub("", s)


def normalize_arabic_text(s: str) -> str:
    """Return a conservative normalized string for search.

    Transformations (search-only):
        - Remove tashkeel and tatweel (U+0640)
        - Unify alef variants (أإآٱ → ا)
        - Yaa variants (ى → ي), hamza-on-yaa forms normalized toward ي
        - Taa marbuta (ة → ه)
        - Arabic-Indic digits → European digits
        - Normalize punctuation and symbols to spaces
        - Collapse whitespace and trim
    """
    if not s:
        return s

    # 1) Unicode NFKC can help unify some forms without being destructive
    s = unicodedata.normalize("NFKC", s)

    # 2) Remove diacritics first so downstream maps don't see them
    s = remove_tashkeel(s)

    # 3) Character-level normalizations
    s = s.translate(ALEF_NORMALIZE_MAP)
    s = s.translate(YAA_NORMALIZE_MAP)
    s = s.translate(TAA_MARBUTA_NORMALIZE_MAP)
    s = s.translate(DIGIT_TRANSLATION)
    s = s.translate(PUNCT_MAP)
    s = s.translate(SYMBOL_MAP)

    # 4) Collapse whitespace
    s = _WHITESPACE_RE.sub(" ", s).strip()

    return s


def remove_stopwords(s: str) -> str:
    """Remove a conservative set of Arabic stopwords (space-delimited)."""
    if not s:
        return s
    tokens = s.split()
    kept = [t for t in tokens if t not in ARABIC_STOPWORDS]
    return " ".join(kept)


def text_search_from_display(display_text: str) -> str:
    """Build the search string from the untouched display text.

    This is the canonical way to get the search copy per the schema:
    take text_display (untouched) → normalize_arabic_text → optionally
    remove_stopwords. We do remove stopwords here because they add noise
    without helping retrieval for short fatwa queries; the normalization
    itself is conservative.
    """
    if not display_text:
        return display_text
    n = normalize_arabic_text(display_text)
    n = remove_stopwords(n)
    return n
