"""The safety rules (no guarantee, no brand, no dose) hold in Hindi and Marathi, not just English.
The numbers are in the context on purpose, so that only the safety rules can flag these answers."""
import pytest

from app.domain.farm import DOMAIN
from app.guardrails.validators import run_all

CTX = "dose numbers present: 20 500 2"


def flagged(text: str) -> bool:
    return bool(run_all(DOMAIN.validators, text, CTX))


@pytest.mark.parametrize("bad", [
    "इस भाव पर बेचने से पक्का मुनाफा होगा।",
    "आप गारंटी के साथ कमाएंगे।",
    "आता विकल्यास नक्की नफा होईल.",
    "याची खात्री आहे, भाव वाढणार.",
    "प्रति लीटर पानी में 20 मिली दवा मिलाकर छिड़कें।",
    "एकरी 500 ग्रॅम खत टाका.",
    "2 मिली प्रति लिटर फवारा.",
    "राउंडअप का छिड़काव करें।", "रिडोमिल गोल्ड फवारा.", "कॉन्फिडोर वापरा.",
    "Spray Confidor on the leaves.",
])
def test_unsafe_hindi_and_marathi_answers_are_rejected(bad):
    assert flagged(bad), bad


@pytest.mark.parametrize("good", [
    "मैं मुनाफे की गारंटी नहीं दे सकता; यह केवल निर्णय सहायता है।",
    "नफ्याची हमी देता येत नाही; ही फक्त मदत आहे.",
    "कोई गारंटी नहीं है, इसलिए कृषि अधिकारी से पूछें।",
    "दवा के लेबल का पालन करें और कृषि अधिकारी की सलाह लें।",
    "औषधाच्या लेबलप्रमाणे फवारणी करा आणि कृषी अधिकाऱ्याला विचारा.",
    "आज भाव स्थिर है।",
])
def test_refusals_and_plain_advice_are_left_alone(good):
    assert not flagged(good), good
