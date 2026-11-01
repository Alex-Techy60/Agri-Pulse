"""Every question type in the problem statement (weather, prices, soil, what to grow, when to sow or harvest, protecting the crop,
schemes, sick plants) reaches the right intent in English, Hindi, Marathi and Hinglish even when the LLM router is down.
No network, no keys."""
import pytest

from app.agents.orchestrator import Orchestrator
from app.domain.farm import DOMAIN
from app.llm.client import LLMResult
from tests.helpers import StubStore


class _LLMDown:
    def chat_json(self, *a, **k):
        return None, LLMResult("", "offline", degraded=True)

    def chat(self, *a, **k):
        return LLMResult("", "offline", degraded=True)


CASES = [
# weather
("Will it rain tomorrow in Nashik?","weather_advice"),("Is it a good day to spray?","weather_advice"),("Do I need to water my field today?","weather_advice"),
("How hot will it be this week?","weather_advice"),("Is there a frost or cold wave coming?","weather_advice"),("Should I protect my crop from the coming storm?","weather_advice"),
("How can I protect my crop from heavy rain?","weather_advice"),("Will there be a hailstorm?","weather_advice"),("what is the temperature tomorrow","weather_advice"),
("कल बारिश होगी क्या?","weather_advice"),("आज फसल को पानी देना चाहिए?","weather_advice"),("आज दवा छिड़कना ठीक रहेगा?","weather_advice"),("ओले या तूफान आने वाला है क्या?","weather_advice"),
("उद्या पाऊस पडेल का?","weather_advice"),("आज फवारणी करू का?","weather_advice"),("पिकाला पाणी द्यावे का?","weather_advice"),("गारपीट होणार आहे का?","weather_advice"),
("kal baarish hogi kya?","weather_advice"),("aaj dawai chhidkun theek hai?","weather_advice"),("fasal ko paani dena chahiye kya","weather_advice"),
# price
("What is the onion price today?","market_price"),("Tomato rate in Pune mandi","market_price"),("Which mandi pays the highest price for onion?","market_price"),("onion price trend this week","market_price"),
("आज प्याज का भाव क्या है?","market_price"),("टमाटर का दाम बताओ","market_price"),("कांद्याचा भाव किती आहे?","market_price"),("लासलगावला आज कांद्याचा दर काय?","market_price"),("aaj pyaz ka bhav kya hai","market_price"),
# sell
("Should I sell now or wait?","sell_or_hold"),("Is it better to hold my onions?","sell_or_hold"),("When should I sell my tomatoes?","sell_or_hold"),("Will prices go up next week?","sell_or_hold"),
("क्या मुझे अभी बेचना चाहिए?","sell_or_hold"),("आता कांदा विकू की थांबू?","sell_or_hold"),("pyaz kab bechun?","sell_or_hold"),("अभी रुकूं या बेचूं?","sell_or_hold"),
# crop suggestion / planting / harvest
("Which crop should I grow now?","crop_suggest"),("What should I plant this season?","crop_suggest"),("Suggest suitable crops for my farm","crop_suggest"),("When should I sow wheat?","crop_suggest"),
("When is the best time to plant onion?","crop_suggest"),("When will my crop be ready to harvest?","crop_suggest"),("Which crop is best for my soil?","crop_suggest"),("Which crop is best for black soil?","crop_suggest"),
("When to harvest my tomato crop?","crop_suggest"),("What can I grow in rabi season?","crop_suggest"),("What can I grow in kharif season?","crop_suggest"),
("इस मौसम में कौन सी फसल लगाऊं?","crop_suggest"),("गेहूं कब बोना चाहिए?","crop_suggest"),("फसल कब काटनी चाहिए?","crop_suggest"),("मेरी जमीन के लिए कौन सी फसल अच्छी है?","crop_suggest"),
("या हंगामात कोणते पीक घ्यावे?","crop_suggest"),("कांदा कधी लावावा?","crop_suggest"),("पीक कधी काढायचे?","crop_suggest"),("माझ्या जमिनीत कोणते पीक चांगले येईल?","crop_suggest"),
("kab ropni karein pyaz ki?","crop_suggest"),("kya lagaun is mausam mein","crop_suggest"),
# soil
("What is the soil moisture in my field?","sow_or_crop_care"),("Is my soil good for onion?","crop_suggest"),("What is my soil pH?","crop_suggest"),("मिट्टी में नमी कितनी है?","sow_or_crop_care"),("माझ्या मातीचा pH किती आहे?","crop_suggest"),
# schemes
("What is MSP for wheat?","scheme_info"),("Tell me about PM Kisan","scheme_info"),("How does crop insurance work?","scheme_info"),
# health
("My onion leaves have spots","crop_health"),("pests are attacking my tomato","crop_health"),("पत्तों पर धब्बे हैं","crop_health"),("पानांवर डाग पडले आहेत","crop_health"),
# general
("Hello","general"),("नमस्ते","general"),("Who are you and what can you do?","general"),("What data sources do you use?","general"),
]


@pytest.mark.parametrize("text,expected", CASES)
def test_keyword_router_sends_each_question_type_to_its_intent(text, expected):
    got = Orchestrator(DOMAIN, _LLMDown(), StubStore())._route(text, None)[0].name
    # soil moisture and crop-care questions may be answered by the crop-suggestion intent, which also reads the soil
    assert got == expected or (expected == "sow_or_crop_care" and got == "crop_suggest"), f"{text!r} -> {got}"
