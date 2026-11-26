"""Rule-based text normalization for streaming TTS.

No GPU and no model. Pure regex and dictionary lookups. Runs on CPU in the
request path and returns spoken text for the TTS engine.
"""

from __future__ import annotations

import json
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Any

from indic_numtowords import num2words as _indic_num2words

try:
    from num2words import num2words as _western_num2words
except ImportError:
    _western_num2words = None

SUPPORTED_LANGS = ("en", "hi", "mr", "ta", "te", "kn", "ml")

_TABLE_PATH = Path(__file__).with_name("normalize_tables.json")

_MULTIPLIERS: dict[str, int] = {
    "k": 1_000,
    "K": 1_000,
    "m": 1_000_000,
    "M": 1_000_000,
    "mn": 1_000_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
    "bn": 1_000_000_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "cr": 10_000_000,
    "Cr": 10_000_000,
    "l": 100_000,
    "L": 100_000,
    "लाख": 100_000,
    "करोड़": 10_000_000,
    "हज़ार": 1_000,
    "हजार": 1_000,
    "कोटी": 10_000_000,
}

_UNIT_TO_CURRENCY = {
    "rupee": "INR", "rupees": "INR", "rs": "INR", "rs.": "INR", "inr": "INR",
    "dollar": "USD", "dollars": "USD", "usd": "USD",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "pound": "GBP", "pounds": "GBP", "gbp": "GBP",
    "yen": "JPY", "jpy": "JPY",
}

_SCRIPT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\u0900-\u097F]"), "hi"),
    (re.compile(r"[\u0B80-\u0BFF]"), "ta"),
    (re.compile(r"[\u0C00-\u0C7F]"), "te"),
    (re.compile(r"[\u0C80-\u0CFF]"), "kn"),
    (re.compile(r"[\u0D00-\u0D7F]"), "ml"),
)

_LATIN = re.compile(r"[A-Za-z]")

_CURRENCY_NUM = r"(?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?"
_MULT_WORD = r"lakhs?|lacs?|crores?|million|mn|billion|bn|लाख|करोड़|हज़ार|हजार|कोटी"
_CURRENCY_SYMBOL_RE = re.compile(
    r"(?P<cur>₹|Rs\.?|INR|रु\.|\$|USD|€|EUR|£|GBP|¥|JPY)\s*"
    r"(?P<num>" + _CURRENCY_NUM + r")"
    r"(?:\s*(?P<mult>(?i:" + _MULT_WORD + r")|[cC]r|[kKmMlL]))?"
    r"(?![A-Za-z])"
)
_CURRENCY_SYMBOL_SUFFIX_RE = re.compile(
    r"(?<![\w.])(?P<num>" + _CURRENCY_NUM + r")\s*(?P<cur>₹|\$|€|£|¥)(?![\w])"
)

_CURRENCY_SUFFIX_RE = re.compile(
    r"(?<![\w.])(?P<num>" + _CURRENCY_NUM + r")"
    r"(?:\s*(?P<mult>(?i:" + _MULT_WORD + r")|[cC]r|[kKmMlL]))?\s*"
    r"(?P<unit>rupees?|rs\.?|inr|dollars?|usd|euros?|eur|pounds?|gbp|yen|jpy)\b",
    re.IGNORECASE,
)

_CURRENCY_RANGE_RE = re.compile(
    r"(?P<cur>₹|\$|€|£|¥)\s*(?P<a>" + _CURRENCY_NUM + r")\s*[-–]\s*"
    r"(?:(?P<cur2>₹|\$|€|£|¥)\s*)?(?P<b>" + _CURRENCY_NUM + r")(?![\w.])"
)
_TIME_SIDE = r"\d{1,2}:\d{2}(?::\d{2})?\s*(?:[ap]\.?\s?m\.?)?"
_TIME_RANGE_RE = re.compile(
    r"(?<!\d)(?P<a>" + _TIME_SIDE + r")\s*[-–]\s*(?P<b>" + _TIME_SIDE + r")(?!\w)",
    re.IGNORECASE,
)
_RANGE_NUM_RE = re.compile(
    r"(?<![\w.])(?P<a>" + r"\d{1,3}(?:,\d{2,3})+|\d+" + r")\s*[-–]\s*"
    r"(?P<b>" + r"\d{1,3}(?:,\d{2,3})+|\d+" + r")(?![\w.])"
)
_FRACTION_RE = re.compile(r"(?<![\w.])(\d+)/(\d+)(?![\w.])")
_RATIO_RE = re.compile(r"(?<![\w.])(\d+):(\d{1,2})(?![\w.])")
_ALNUM_LETTERS_FIRST_RE = re.compile(
    r"\b(?P<letters>[A-Za-z]{1,6})(?:-(?P<hyphen>\d+))?(?P<digits>\d+)?\b(?![\d.])"
)
_ALNUM_DIGITS_FIRST_RE = re.compile(
    r"(?<![\w.])(?P<digits>\d+)(?P<letters>[A-Za-z]{1,6})\b(?![\d.])"
)
_NEGATIVE_RE = re.compile(r"(?P<prefix>^|[\s(])-(?=\d)")
_SQFT_RE = re.compile(
    r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*(?:sq\.?\s*ft\.?|square\s+feet|square\s+foot)(?!\w)",
    re.IGNORECASE,
)
_COMMA_SPACE_RE = re.compile(r",(?=\S)")

_DATE_DMY_RE = re.compile(r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})(?!\d)")
_DATE_ISO_RE = re.compile(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)")
_TIME_RE = re.compile(
    r"(?<!\d)(\d{1,2}):(\d{2})(?::(\d{2}))?\s*([ap]\.?\s?m\.?)?"
    r"(?:\s*(?P<tail>बजे|वाजता))?(?!\w)",
    re.IGNORECASE,
)
_ORDINAL_RE = re.compile(r"(?<![\w.])(\d+)(st|nd|rd|th)\b", re.IGNORECASE)
_OTP_RE = re.compile(
    r"\b(OTP|PIN|code|ID|verification code|one time password)\s*(?:is|:)?\s*(\d{4,8})\b",
    re.IGNORECASE,
)
_PHONE_RE = re.compile(
    r"(?<![\w.])(?:\+?91[\s-]?)?[6-9]\d{4}[\s-]?\d{5}(?!\w)"
    r"|(?<![\w.])\+?\d{10,15}(?!\w)"
)
_GROUPED = r"\d{1,3}(?:,\d{2,3})+|\d+"
_DECIMAL_RE = re.compile(r"(?<![\w.])(" + _GROUPED + r")\.(\d+)(?!\w)(?!\.\d)")
_INTEGER_RE = re.compile(r"(?<![\w.])(" + _GROUPED + r")(?!\w)(?!\.\d)")
_MULTIPLIER_RE = re.compile(
    r"(?<![\w.])(?P<num>" + _CURRENCY_NUM + r")\s*"
    r"(?P<mult>(?i:" + _MULT_WORD + r")|[cC]r|[kKmMlL])(?![A-Za-z\u0900-\u0D7F])"
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_DOMAIN_RE = re.compile(
    r"\b(?:[a-z0-9][a-z0-9-]*\.)+(?:com|in|org|net|io|ai|co|edu|gov)(?:/[^\s<>\"']*)?\b",
    re.IGNORECASE,
)
_URL_RE = re.compile(r"\b(?:https?://|www\.)[^\s<>\"']+", re.IGNORECASE)
_ACRONYM_RE = re.compile(
    r"\b(OTP|ATM|UPI|PIN|API|URL|SMS|GPS|KYC|EMI|GST|FAQ|CEO|CFO|CPU|GPU|PDF|ID|AI)\b"
)
_ZERO_WIDTH_RE = re.compile(r"[\u200b-\u200f\u2060\ufeff]")
_WHITESPACE_RE = re.compile(r"\s+")
_JUNK_RE = re.compile(r"[*_~^|]+")
_SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.;:!?])")
_VOWELS = set("aeiou")


@lru_cache(maxsize=1)
def _tables() -> dict[str, Any]:
    with _TABLE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _lang_cfg(lang: str) -> dict[str, Any]:
    data = _tables()
    languages = data["languages"]
    return languages.get(lang) or languages[data["default_lang"]]


def _num_words(number: int, lang: str) -> str:
    if number < 0:
        return "minus " + _num_words(-number, lang)
    try:
        words = _indic_num2words(int(number), lang=lang)
    except Exception:
        if abs(number) >= 10**15:
            return _digit_words(str(abs(number)), lang)
        try:
            words = _indic_num2words(int(number), lang="en")
        except Exception:
            return _digit_words(str(abs(number)), lang)
    return str(words).replace(",", " ").strip()


def _amount_num_words(number: int, code: str, lang: str) -> str:
    if lang == "en" and code in ("USD", "EUR", "GBP", "JPY") and _western_num2words:
        try:
            words = _western_num2words(int(number), lang="en")
            return words.replace(",", "").replace("-", " ").strip()
        except Exception:
            pass
    return _num_words(number, lang)


def _digit_words(digits: str, lang: str) -> str:
    return " ".join(_num_words(int(ch), lang) for ch in digits if ch.isdigit())


def _lang_for(text: str, start: int, end: int, default: str) -> str:
    window = text[max(0, start - 40):start] + " " + text[end:end + 40]
    for pattern, lang in _SCRIPT_PATTERNS:
        if pattern.search(window):
            if lang == "hi" and default in ("hi", "mr"):
                return default
            return lang
    if _LATIN.search(window):
        return "en"
    return default


def _read_number(num: str, lang: str) -> str:
    clean = num.replace(",", "").strip()
    if not clean:
        return ""
    if "." in clean:
        whole, frac = clean.split(".", 1)
        return (
            _num_words(int(whole or "0"), lang)
            + " "
            + _lang_cfg(lang)["point"]
            + " "
            + _digit_words(frac, lang)
        )
    return _num_words(int(clean), lang)


def _scale(num: str, mult: str | None) -> Decimal | None:
    try:
        value = Decimal(num.replace(",", ""))
    except InvalidOperation:
        return None
    if mult:
        factor = _MULTIPLIERS.get(mult)
        if factor is None:
            factor = _MULTIPLIERS.get(mult.lower())
        if factor:
            value *= factor
    return value


def _plural_pair(pair: list[str], count: Decimal) -> str:
    return pair[0] if count == 1 else pair[1]


def _currency_words(num: str, mult: str | None, code: str, lang: str) -> str:
    value = _scale(num, mult)
    if value is None:
        return num
    cfg = _lang_cfg(lang)
    entry = (cfg.get("currency") or _lang_cfg("en")["currency"]).get(code)
    if not entry:
        entry = _lang_cfg("en")["currency"]["USD"]
    major, minor = entry["major"], entry["minor"]
    whole = int(value)
    rest = value - whole
    parts: list[str] = []
    if whole or rest == 0:
        parts.append(_amount_num_words(whole, code, lang))
        parts.append(_plural_pair(major, Decimal(whole)))
    if rest and not mult:
        minor_value = int((rest * 100).quantize(Decimal("1")))
        if minor_value:
            parts.append(_num_words(minor_value, lang))
            parts.append(_plural_pair(minor, Decimal(minor_value)))
    elif rest and mult:
        parts.append(cfg["point"])
        parts.append(_digit_words(str(rest).split(".")[-1], lang))
    return " ".join(part for part in parts if part)


def _replace_abbreviations(text: str, lang: str) -> str:
    table = _lang_cfg(lang).get("abbreviations") or {}
    if not table:
        return text
    pattern = re.compile(
        r"(?<![\w])(" + "|".join(re.escape(key) for key in sorted(table, key=len, reverse=True)) + r")"
    )
    return pattern.sub(lambda m: table[m.group(1)], text)


def _replace_currency(text: str, lang: str) -> str:
    symbols = _tables()["symbols"]

    def currency_range(match: re.Match[str]) -> str:
        code = symbols.get(match.group("cur"))
        if not code:
            return match.group(0)
        cfg = _lang_cfg(lang)
        entry = cfg["currency"].get(code) or _lang_cfg("en")["currency"][code]
        a = _amount_num_words(int(match.group("a").replace(",", "")), code, lang)
        b = _amount_num_words(int(match.group("b").replace(",", "")), code, lang)
        return f"{a} {cfg['to']} {b} {entry['major'][1]}"

    def prefix(match: re.Match[str]) -> str:
        code = symbols.get(match.group("cur"))
        if not code:
            return match.group(0)
        return _currency_words(match.group("num"), match.group("mult"), code, lang)

    def suffix(match: re.Match[str]) -> str:
        unit = match.group("unit").lower().rstrip(".")
        code = _UNIT_TO_CURRENCY.get(unit)
        if not code:
            return match.group(0)
        return _currency_words(match.group("num"), match.group("mult"), code, lang)

    def suffix_symbol(match: re.Match[str]) -> str:
        code = symbols.get(match.group("cur"))
        if not code:
            return match.group(0)
        return _currency_words(match.group("num"), None, code, lang)

    text = _CURRENCY_RANGE_RE.sub(currency_range, text)
    text = _CURRENCY_SYMBOL_RE.sub(prefix, text)
    text = _CURRENCY_SYMBOL_SUFFIX_RE.sub(suffix_symbol, text)
    return _CURRENCY_SUFFIX_RE.sub(suffix, text)


def _replace_sqft(text: str, lang: str) -> str:
    unit = _lang_cfg(lang)["sqft"]
    number_lang = "en" if lang == "en" else lang

    def repl(match: re.Match[str]) -> str:
        return _read_number(match.group(1), number_lang) + " " + unit

    return _SQFT_RE.sub(repl, text)


def _replace_units(text: str, lang: str, units: dict[str, str]) -> str:
    if not units:
        return text
    keys = sorted(units, key=len, reverse=True)
    pattern = re.compile(
        r"(?<![\w.])(\d[\d,]*(?:\.\d+)?)\s*("
        + "|".join(re.escape(key) for key in keys)
        + r")(?![A-Za-z])"
    )

    def repl(match: re.Match[str]) -> str:
        number = _read_number(match.group(1), lang)
        return f"{number} {units[match.group(2)]}"

    return pattern.sub(repl, text)


def _replace_multipliers(text: str, lang: str) -> str:
    def repl(match: re.Match[str]) -> str:
        value = _scale(match.group("num"), match.group("mult"))
        if value is None:
            return match.group(0)
        if value == int(value):
            return _num_words(int(value), lang)
        whole = int(value)
        frac = str(value - whole).split(".")[-1]
        return _num_words(whole, lang) + " " + _lang_cfg(lang)["point"] + " " + _digit_words(frac, lang)

    return _MULTIPLIER_RE.sub(repl, text)


def _replace_dates(text: str, lang: str) -> str:
    months = _lang_cfg(lang)["months"]

    def dmy(match: re.Match[str]) -> str:
        day, month, year = int(match.group(1)), int(match.group(2)), match.group(3)
        if day > 31 or month > 12:
            return match.group(0)
        return f"{_num_words(day, lang)} {months[month - 1]} {_read_number(year, lang)}"

    def iso(match: re.Match[str]) -> str:
        year, month, day = match.group(1), int(match.group(2)), int(match.group(3))
        if day > 31 or month > 12:
            return match.group(0)
        return f"{_num_words(day, lang)} {months[month - 1]} {_read_number(year, lang)}"

    text = _DATE_ISO_RE.sub(iso, text)
    return _DATE_DMY_RE.sub(dmy, text)


def _format_time(hour: int, minute: int, ampm: str | None, lang: str) -> str:
    cfg = _lang_cfg(lang)
    hour_words = _num_words(hour, lang)
    if lang in ("hi", "mr"):
        if minute == 0:
            parts = [hour_words, cfg["oclock"]]
        else:
            parts = [hour_words, cfg["past"], _num_words(minute, lang), cfg["minutes"]]
        if ampm:
            parts.insert(0, cfg["am"] if ampm.lower().startswith("a") else cfg["pm"])
    elif minute == 0:
        parts = [hour_words, cfg["oclock"]]
    elif minute < 10:
        parts = [hour_words, cfg["oh"], _num_words(minute, lang)]
    else:
        parts = [hour_words, _num_words(minute, lang)]
    if ampm and lang not in ("hi", "mr"):
        parts.append("a m" if ampm.lower().startswith("a") else "p m")
    return " ".join(parts)


def _replace_time_ranges(text: str, lang: str) -> str:
    def repl(match: re.Match[str]) -> str:
        left = re.match(r"(\d{1,2}):(\d{2})(?:\d{2})?\s*([ap]\.?\s?m\.?)?$", match.group("a"), re.IGNORECASE)
        right = re.match(r"(\d{1,2}):(\d{2})(?:\d{2})?\s*([ap]\.?\s?m\.?)?$", match.group("b"), re.IGNORECASE)
        if not left or not right or int(left.group(2)) > 59 or int(right.group(2)) > 59:
            return match.group(0)
        a = _format_time(int(left.group(1)), int(left.group(2)), left.group(3), lang)
        b = _format_time(int(right.group(1)), int(right.group(2)), right.group(3), lang)
        return f"{a} {_lang_cfg(lang)['to']} {b}"

    return _TIME_RANGE_RE.sub(repl, text)


def _replace_times(text: str, lang: str) -> str:
    def repl(match: re.Match[str]) -> str:
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return match.group(0)
        ampm = match.group(4)
        if ampm and lang in ("hi", "mr"):
            before = match.string[max(0, match.start() - 16):match.start()]
            word = _lang_cfg(lang)["am"] if ampm.lower().startswith("a") else _lang_cfg(lang)["pm"]
            if word in before:
                ampm = None
        return _format_time(hour, minute, ampm, lang)

    return _TIME_RE.sub(repl, text)


def _english_ordinal(number: int) -> str:
    table = _lang_cfg("en")["ordinals"]
    if 1 <= number <= 10:
        return table[number]
    if number < 20:
        return _num_words(number, "en") + "th"
    if number < 100:
        tens, unit = divmod(number, 10)
        base = _num_words(tens * 10, "en")
        return base if unit == 0 else f"{base} {table[unit]}"
    return _num_words(number, "en") + "th"


def _replace_ordinals(text: str, lang: str) -> str:
    cfg = _lang_cfg(lang)

    def repl(match: re.Match[str]) -> str:
        number = int(match.group(1))
        if lang == "en":
            return _english_ordinal(number)
        table = cfg["ordinals"]
        if 1 <= number < len(table):
            return table[number]
        return _num_words(number, lang) + cfg["ordinal_suffix"]

    return _ORDINAL_RE.sub(repl, text)


def _replace_phones(text: str, lang: str) -> str:
    def otp(match: re.Match[str]) -> str:
        start = match.start(2) - match.start(0)
        return match.group(0)[:start] + _digit_words(match.group(2), lang)

    def phone(match: re.Match[str]) -> str:
        return _digit_words(match.group(0).lstrip("+"), lang)

    text = _OTP_RE.sub(otp, text)
    return _PHONE_RE.sub(phone, text)


def _replace_numbers(text: str, lang: str) -> str:
    def decimal(match: re.Match[str]) -> str:
        span_lang = _lang_for(text, match.start(), match.end(), lang)
        cfg = _lang_cfg(span_lang)
        return (
            _num_words(int(match.group(1).replace(",", "")), span_lang)
            + " "
            + cfg["point"]
            + " "
            + _digit_words(match.group(2), span_lang)
        )

    def integer(match: re.Match[str]) -> str:
        span_lang = _lang_for(text, match.start(), match.end(), lang)
        return _num_words(int(match.group(0).replace(",", "")), span_lang)

    text = _DECIMAL_RE.sub(decimal, text)
    return _INTEGER_RE.sub(integer, text)


def _replace_negatives(text: str, lang: str) -> str:
    word = "minus" if lang == "en" else _lang_cfg(lang).get("minus", "minus")
    return _NEGATIVE_RE.sub(lambda m: m.group("prefix") + word + " ", text)


def _replace_ranges(text: str, lang: str) -> str:
    to = _lang_cfg(lang)["to"]

    def repl(match: re.Match[str]) -> str:
        a = _read_number(match.group("a"), lang)
        b = _read_number(match.group("b"), lang)
        return f"{a} {to} {b}"

    return _RANGE_NUM_RE.sub(repl, text)


def _replace_fractions(text: str, lang: str) -> str:
    cfg = _lang_cfg(lang)

    def fraction(match: re.Match[str]) -> str:
        a, b = int(match.group(1)), int(match.group(2))
        if a == 1 and b == 2:
            return _num_words(1, lang) + " " + cfg["half"]
        if a == 24 and b == 7:
            return _num_words(24, lang) + " " + _num_words(7, lang)
        return match.group(0)

    def ratio(match: re.Match[str]) -> str:
        a, b = int(match.group(1)), int(match.group(2))
        if b == 1:
            return _num_words(a, lang) + " " + cfg["to"] + " " + _num_words(b, lang)
        return match.group(0)

    text = _FRACTION_RE.sub(fraction, text)
    return _RATIO_RE.sub(ratio, text)


def _replace_alnum(text: str, lang: str) -> str:
    def letters_first(match: re.Match[str]) -> str:
        digits = match.group("hyphen") or match.group("digits")
        if not digits:
            return match.group(0)
        spelled = " ".join(match.group("letters").upper())
        return spelled + " " + _digit_words(digits, lang)

    def digits_first(match: re.Match[str]) -> str:
        spelled = " ".join(match.group("letters").upper())
        return _num_words(int(match.group("digits")), lang) + " " + spelled

    text = _ALNUM_LETTERS_FIRST_RE.sub(letters_first, text)
    return _ALNUM_DIGITS_FIRST_RE.sub(digits_first, text)


def _replace_urls(text: str, lang: str) -> str:
    at = _lang_cfg(lang)["symbol_words"].get("@", "at")

    def email(match: re.Match[str]) -> str:
        return match.group(0).replace("@", f" {at} ").replace(".", " dot ").replace("_", " ")

    def url(match: re.Match[str]) -> str:
        original = match.group(0)
        if "://" not in original and not original.lower().startswith("www."):
            if original != original.lower():
                return original
        raw = re.sub(r"^https?://", "", original, flags=re.IGNORECASE)
        raw = re.sub(r"^www\.", "", raw, flags=re.IGNORECASE)
        raw = raw.replace(".", " dot ").replace("/", " slash ").replace(":", " colon ")
        raw = raw.replace("-", " ").replace("_", " ").replace("?", " ").replace("=", " ")
        return " " + raw + " "

    text = _URL_RE.sub(url, text)
    text = _EMAIL_RE.sub(email, text)
    return _DOMAIN_RE.sub(url, text)


def _replace_symbols(text: str, lang: str) -> str:
    cfg = _lang_cfg(lang)
    words = dict(_lang_cfg("en")["symbol_words"])
    words.update(cfg.get("symbol_words") or {})
    for symbol in sorted(words, key=len, reverse=True):
        if symbol in text:
            text = text.replace(symbol, f" {words[symbol]} ")
    for symbol, code in _tables()["symbols"].items():
        if symbol in text and len(symbol) > 1:
            entry = cfg["currency"].get(code)
            if entry:
                text = text.replace(symbol, " " + entry["major"][1] + " ")
    text = _JUNK_RE.sub(" ", text)
    text = text.replace("(", " ").replace(")", " ").replace("[", " ").replace("]", " ")
    text = text.replace("{", " ").replace("}", " ")
    return text


def _replace_acronyms(text: str, lang: str) -> str:
    table = _lang_cfg(lang).get("acronyms") or {}

    def repl(match: re.Match[str]) -> str:
        word = match.group(1)
        if word in table:
            return table[word]
        return " ".join(word)

    return _ACRONYM_RE.sub(repl, text)


def normalize(text: str, lang: str = "en") -> str:
    """Convert written text to a spoken form for the TTS engine."""
    if not text:
        return ""
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    result = unicodedata.normalize("NFC", text)
    result = _ZERO_WIDTH_RE.sub("", result).replace("\u00a0", " ")
    result = _WHITESPACE_RE.sub(" ", result).strip()

    result = _replace_urls(result, lang)
    result = _replace_abbreviations(result, lang)
    result = _replace_sqft(result, lang)
    result = _replace_time_ranges(result, lang)
    result = _replace_currency(result, lang)
    result = _replace_multipliers(result, lang)
    result = _replace_dates(result, lang)
    result = _replace_times(result, lang)
    result = _replace_ordinals(result, lang)
    result = _replace_phones(result, lang)
    result = _replace_negatives(result, lang)
    result = _replace_ranges(result, lang)
    result = _replace_fractions(result, lang)
    result = _replace_alnum(result, lang)
    result = _replace_units(result, lang, _lang_cfg(lang).get("units") or {})
    result = _replace_numbers(result, lang)
    result = _replace_symbols(result, lang)
    result = _replace_acronyms(result, lang)

    result = unicodedata.normalize("NFC", result)
    result = _ZERO_WIDTH_RE.sub("", result)
    result = _SPACE_BEFORE_PUNCT_RE.sub(r"\1", result)
    result = _COMMA_SPACE_RE.sub(", ", result)
    return _WHITESPACE_RE.sub(" ", result).strip()
