"""Crop-specific advice from the live forecast + cited rules (decision/crop_rules.py). Runs after the weather tool."""
from __future__ import annotations

import datetime as dt

from app.decision.crop_rules import crop_advice, has_rules
from app.decision.crop_water import crop_entry, crop_water_need, parse_sowing
from app.tools import PlaceNotFound, SourceUnavailable, ToolResult, guarded
from app.tools.mandi import crop_key
from app.tools.weather import get_weather


def _water(crop: str, profile: dict, days: list[dict]) -> tuple[list[str], list[dict], dict | None]:
    """FAO-56 crop water need (decision/crop_water.py). Returns (text lines, UI cards, facts). Needs a sowing date:
    without one the tool says so and estimates nothing."""
    if crop_entry(crop) is None:
        return [], [], None
    sowing = parse_sowing(profile.get("sowing_date"))
    if sowing is None:
        return ["CROP WATER: no sowing date given, so the crop's water need is not computed. Ask the farmer when the crop was sown (YYYY-MM-DD)."], [], None
    if not days or not days[0].get("date"):
        return [], [], None
    today = dt.date.fromisoformat(days[0]["date"])
    res = crop_water_need(crop, sowing, today, days)
    if res is None:
        return [], [], None
    st = res["today"]
    if st["stage"] == "not_sown":
        return [f"CROP WATER: {crop.title()} is to be sown on {sowing.isoformat()}, {-st['day']} day(s) from today. No crop water need yet."], [], res
    if st["stage"] == "cycle_complete":
        return [f"CROP WATER: {crop.title()} sown {sowing.isoformat()} has passed the FAO-56 cycle length ({st['total_days']} days). Check the harvest with the agriculture officer."], [], res
    head = (f"CROP WATER (FAO-56, computed in code): {crop.title()} sown {sowing.isoformat()}, day {st['day'] + 1} of {st['total_days']}, "
            f"stage {st['stage'].replace('_', ' ')}, Kc today {st['kc']}.")
    lines = [head]
    if res["days"]:
        lines.append(
            f"Next {res['days']} days: crop water need {res['need_mm']} mm (ET0 x Kc) against forecast rain {res['rain_mm']} mm "
            f"-> {res['label']} by {abs(res['balance_mm'])} mm. Timing is indicative FAO-56 for {res['row']}, not tuned to Nashik: say so, and say that the figure is a reference, not an exact need."
        )
    if res["skipped"]:
        lines.append(f"NOTE: {res['skipped']} forecast day(s) had no rain or ET0 value and are left out of the crop water sum.")
    card = {"type": "crop_water", "title": f"Crop water - {crop.title()}", "stage": st["stage"], "day": st["day"] + 1, "total_days": st["total_days"],
            "kc": st["kc"], "days": res["days"], "need_mm": res["need_mm"], "rain_mm": res["rain_mm"], "balance_mm": res["balance_mm"],
            "label": res["label"], "row": res["row"], "note": res["note"], "source": res["source"]}
    return lines, [card] if res["days"] else [], res


def get_crop_stage(profile: dict) -> ToolResult:
    crop = crop_key(profile.get("crop") or "")
    if not crop:
        return ToolResult("CROP RULES: no crop selected, so no crop-specific rules were checked.")
    try:
        w = get_weather(profile)  # same URL + params as the weather tool: served from the http cache, no second live call
    except (SourceUnavailable, PlaceNotFound):
        return ToolResult("CROP RULES: not checked because the forecast is unavailable.")
    state = w.facts["location"]["state"]
    water_lines, water_cards, water = _water(crop, profile, w.facts["days"])
    facts: dict = {"crop_water": water}
    if not has_rules(crop, state):
        head = f"CROP RULES: no verified crop-specific rule is available for {crop.title()} in {state}. Do not invent crop-stage advice."
        facts["crop_advice"] = []
        return ToolResult("\n".join([head] + water_lines), sources=[], cards=water_cards, facts=facts)
    adv = crop_advice(crop, state, w.facts["days"])
    facts["crop_advice"] = adv
    if not adv:
        head = f"CROP RULES for {crop.title()} in {state}: no crop-specific risk triggered by the forecast."
        return ToolResult("\n".join([head] + water_lines), cards=water_cards, facts=facts)
    lines = [f"CROP RULES for {crop.title()} in {state} (computed in code from the live forecast):"]
    lines += [f"- {a['code']}: {a['text']} Source: {a['source']}" for a in adv]
    return ToolResult("\n".join(lines + water_lines), cards=water_cards, facts=facts)


crop_stage = guarded("crop_stage")(lambda text, profile: get_crop_stage(profile))
