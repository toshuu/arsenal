import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from batch.text_normalize import SUPPORTED_LANGS, normalize

LANGS = list(SUPPORTED_LANGS)


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize(
    "source",
    [
        "Rs. 1,502",
        "₹1,502.50",
        "$20.50",
        "₹5L",
        "₹2Cr",
        "$1.5k",
        "1st prize",
        "21st prize",
        "5:30 pm",
        "12/03/2025",
        "2025-03-12",
        "50% off",
        "5 kg",
        "Dr. Rao has 3 cats",
        "OTP is 4821",
        "call 9876543210",
        "3.14",
        "1,50,000",
        "1502 rupees",
        "user@example.com",
        "I paid 500.",
        "Call 9876543210.",
        "Score is 3.5.",
        "Pay 500, then 600.",
        "Items 1,2,3",
        "+91 98765 43210",
        "98765-43210",
        "at 5:00 pm",
        "at 9:05",
        "$5 Million",
        "₹2 Lakh.",
        "5 lakh people",
    ],
)
def test_no_written_digits_remain(lang, source):
    result = normalize(source, lang)
    assert result
    assert not any(ch.isdigit() for ch in result), result


@pytest.mark.parametrize("lang", LANGS)
def test_currency_word_order(lang):
    result = normalize("Rs. 1,502", lang)
    words = result.split()
    assert len(words) > 2
    assert "1502" not in result


@pytest.mark.parametrize("lang", LANGS)
def test_decimal_point_word(lang):
    assert normalize("3.14", lang).count(" ") >= 3


@pytest.mark.parametrize("lang", LANGS)
def test_phone_reads_digits(lang):
    result = normalize("call 9876543210", lang)
    assert len(result.split()) >= 11


@pytest.mark.parametrize("lang", LANGS)
def test_zero_width_removed(lang):
    result = normalize("1,50,000\u200b", lang)
    assert "\u200b" not in result


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize(
    "source",
    [
        "Rs. 1,502",
        "$20.50",
        "Dr. Rao has 3 cats",
        "12/03/2025",
        "50% off",
        "call 9876543210",
    ],
)
def test_idempotent(lang, source):
    once = normalize(source, lang)
    assert normalize(once, lang) == once


def test_english_currency_words():
    assert normalize("$1", "en") == "one dollar"
    assert normalize("$20", "en") == "twenty dollars"


def test_sentence_final_number():
    assert normalize("I paid 500.", "en") == "I paid five hundred."


def test_comma_between_numbers_is_kept():
    result = normalize("Pay 500, then 600.", "en")
    assert "five hundred," in result
    assert "six hundred." in result


def test_digit_list_not_merged():
    assert normalize("Items 1,2,3", "en").count(",") == 2


def test_indian_phone_with_country_code():
    result = normalize("+91 98765 43210", "en")
    assert not any(ch.isdigit() for ch in result)
    assert len(result.split()) >= 10


def test_time_on_the_hour_and_past_the_hour():
    assert "o'clock" in normalize("at 5:00 pm", "en")
    assert "oh five" in normalize("at 9:05", "en")


def test_capitalized_multiplier():
    result = normalize("$5 Million", "en")
    assert "Million" not in result
    assert not any(ch.isdigit() for ch in result)
    assert "Lakh" not in normalize("₹2 Lakh.", "en")


def test_domain_guard_keeps_broken_sentence_text():
    assert "dot" not in normalize("Okay.In a moment", "en")


def test_version_string_is_untouched():
    assert normalize("v1.2.3", "en") == "v1.2.3"


def test_abbreviation_expanded_before_sentence_split():
    assert "Dr." not in normalize("Dr. Rao is here.", "en")
    assert "डॉक्टर" in normalize("Dr. Rao is here.", "hi")


def test_cpu_speed():
    text = "Rs. 1,502 paid on 12/03/2025 at 5:30 pm, 50% off, call 9876543210."
    start = time.perf_counter()
    for _ in range(200):
        normalize(text, "hi")
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, elapsed


def test_suffix_currency_symbol():
    assert normalize("20$", "en") == "twenty dollars"


def test_comma_after_amount_survives():
    assert normalize("Pay ₹1,502, thanks.", "en") == (
        "Pay one thousand five hundred and two rupees, thanks."
    )


def test_otp_keeps_connector_word():
    assert " is " in normalize("Your OTP is 482916.", "en")


def test_hindi_currency_keeps_following_space():
    assert normalize("मेरा balance ₹1,502 है", "hi") == (
        "मेरा balance एक हज़ार पाँच सौ दो रुपये है"
    )


def test_very_large_number_does_not_crash():
    result = normalize("1" * 30, "en")
    assert result
    assert not any(ch.isdigit() for ch in result)


def test_devanagari_multiplier():
    assert normalize("₹5 लाख", "hi") == "पाँच लाख रुपये"
    assert normalize("₹2.5 करोड़", "hi") == "दो करोड़ पचास लाख रुपये"


def test_western_money_for_english_non_inr():
    assert normalize("$5 Million", "en") == "five million dollars"
    assert normalize("$2.5M", "en") == "two million five hundred thousand dollars"
    assert normalize("₹2.5 crore", "en") == "two crore fifty lakh rupees"


def test_ranges():
    assert normalize("10-12 days", "en") == "ten to twelve days"
    assert normalize("₹500-₹800", "en") == "five hundred to eight hundred rupees"
    assert normalize("9:00 am-5:00 pm", "en") == (
        "nine o'clock a m to five o'clock p m"
    )


def test_fractions_and_ratios():
    assert normalize("1/2", "en") == "one half"
    assert normalize("24/7", "en") == "twenty four seven"
    assert normalize("3:1", "en") == "three to one"


def test_alphanumerics():
    assert normalize("2BHK", "en") == "two B H K"
    assert normalize("3G", "en") == "three G"
    assert normalize("GST123", "en") == "G S T one two three"
    assert normalize("Flat A-203", "en") == "Flat A two zero three"


def test_negatives():
    assert normalize("-5", "en") == "minus five"
    assert normalize("It is -5°C today", "en") == (
        "It is minus five degrees Celsius today"
    )
    assert normalize("Room 5-6", "en") == "Room five to six"


def test_comma_spacing_between_numbers():
    assert normalize("Items 1,2,3", "en") == "Items one, two, three"


def test_hindi_point_and_time():
    assert normalize("3.5", "hi") == "तीन दशमलव पाँच"
    assert normalize("शाम 5:00 बजे", "hi") == "शाम पाँच बजे"
    assert normalize("9:05", "hi") == "नौ बजकर पाँच मिनट"
    assert normalize("सुबह 10:30 बजे", "hi") == "सुबह दस बजकर तीस मिनट"


def test_hindi_title_abbreviation():
    assert normalize("Mr. Sharma ने ₹500 दिए", "hi") == (
        "मिस्टर Sharma ने पाँच सौ रुपये दिए"
    )


def test_hindi_ampm_uses_words_not_letters():
    assert normalize("5:00 pm", "hi") == "शाम पाँच बजे"
    assert normalize("10:30 am", "hi") == "सुबह दस बजकर तीस मिनट"
    assert normalize("शाम 5:00 pm", "hi") == "शाम पाँच बजे"


def test_hindi_acronyms_use_devanagari_letters():
    assert normalize("OTP 482916 है", "hi") == "ओ टी पी चार आठ दो नौ एक छः है"
    assert normalize("Use UPI or ATM.", "hi") == "Use यू पी आई or ए टी एम."


def test_square_footage_uses_transliterated_unit():
    assert normalize("2,000 sq. ft.", "en") == "two thousand स्क्वायर फीट"
    assert normalize("1,00,000 sq ft", "en") == "one lakh स्क्वायर फीट"
    assert normalize("2,000 square feet", "hi") == "दो हज़ार स्क्वायर फीट"
