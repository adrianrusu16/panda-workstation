"""Strict synthetic presentation data; no host observation or data providers."""
import json
import math
from pathlib import Path
import re

from desktop_io import read_regular
from desktop_layout import fields, string
def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def reject_constant(value):
    raise ValueError("non-finite JSON number")


APPLICATIONS = {
    "org.kde.dolphin.desktop": "files", "org.kde.konsole.desktop": "terminal",
    "org.kde.kate.desktop": "editor", "org.kde.ark.desktop": "archive",
    "org.kde.gwenview.desktop": "photos", "org.kde.elisa.desktop": "music",
    "systemsettings.desktop": "settings",
}


def number(value, label, low, high, nullable=False):
    if value is None and nullable:
        return
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(label + ": finite number out of range")


def choice(value, allowed, label):
    if not isinstance(value, str) or value not in allowed:
        raise ValueError(label + ": unknown value")


def text(value, label, empty=False):
    if empty and value == "":
        return
    string(value, label)


def validate_scene(scene):
    fields(scene, ("schema_version", "scope", "clock", "media", "weather", "cpu", "ram", "dock"), "visual fixture")
    if type(scene["schema_version"]) is not int or scene["schema_version"] != 1 or scene["scope"] != "panda-visual-synthetic":
        raise ValueError("explicit synthetic visual fixture schema required")
    clock = scene["clock"]
    fields(clock, ("time", "date", "short_date"), "clock")
    for key, value in clock.items():
        text(value, "clock." + key)
    if re.fullmatch(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", clock["time"]) is None:
        raise ValueError("clock time must be an explicit 24-hour sample")
    media = scene["media"]
    fields(media, ("state", "title", "artist", "artwork", "elapsed", "duration", "players"), "media")
    choice(media["state"], ("playing", "paused", "no-player", "unavailable"), "media state")
    choice(media["artwork"], ("sample", "none"), "artwork")
    for key in ("title", "artist"):
        text(media[key], "media." + key, empty=True)
    if type(media["players"]) is not int or not 0 <= media["players"] <= 16:
        raise ValueError("invalid player count")
    if media["state"] in ("no-player", "unavailable"):
        if media["players"] != 0 or media["artwork"] != "none" or any(media[k] is not None for k in ("elapsed", "duration")):
            raise ValueError("unavailable player must not contain playback readings")
    elif not media["players"]:
        raise ValueError("playing/paused requires a synthetic player")
    if (media["elapsed"] is None) != (media["duration"] is None):
        raise ValueError("elapsed/duration must be present together")
    if media["duration"] is not None:
        number(media["duration"], "duration", 1, 86400)
        number(media["elapsed"], "elapsed", 0, media["duration"])
    weather = scene["weather"]
    fields(weather, ("state", "location", "condition", "temperature", "low", "high"), "weather")
    choice(weather["state"], ("available", "stale", "offline", "unconfigured"), "weather state")
    for key in ("location", "condition"):
        text(weather[key], "weather." + key)
    for key in ("temperature", "low", "high"):
        number(weather[key], key, -100, 70, nullable=weather["state"] != "available")
    if weather["state"] in ("offline", "unconfigured") and any(weather[k] is not None for k in ("temperature", "low", "high")):
        raise ValueError("offline weather cannot present healthy readings")
    if weather["low"] is not None and weather["high"] is not None and weather["low"] > weather["high"]:
        raise ValueError("weather low exceeds high")
    cpu = scene["cpu"]
    fields(cpu, ("state", "percent", "history", "window_seconds"), "cpu")
    choice(cpu["state"], ("available", "missing"), "cpu state")
    number(cpu["window_seconds"], "window_seconds", 1, 3600)
    number(cpu["percent"], "cpu percent", 0, 100, nullable=cpu["state"] == "missing")
    if not isinstance(cpu["history"], list) or len(cpu["history"]) > 120:
        raise ValueError("bounded CPU history required")
    for value in cpu["history"]:
        number(value, "CPU sample", 0, 100, nullable=True)
    if cpu["state"] == "missing":
        if cpu["percent"] is not None or cpu["history"]:
            raise ValueError("missing CPU must have no readings")
    elif len(cpu["history"]) < 2 or not any(n is not None for n in cpu["history"]):
        raise ValueError("available CPU requires history samples")
    ram = scene["ram"]
    fields(ram, ("state", "used_gib", "total_gib"), "ram")
    choice(ram["state"], ("available", "partial", "missing"), "ram state")
    number(ram["used_gib"], "used RAM", 0, 65536, nullable=ram["state"] == "missing")
    number(ram["total_gib"], "total RAM", 0.001, 65536, nullable=ram["state"] != "available")
    if ram["state"] == "missing" and any(ram[k] is not None for k in ("used_gib", "total_gib")):
        raise ValueError("missing RAM must have no readings")
    if ram["state"] == "partial" and ram["total_gib"] is not None:
        raise ValueError("partial RAM denotes unknown total")
    if ram["total_gib"] is not None and ram["used_gib"] > ram["total_gib"]:
        raise ValueError("used RAM exceeds total")
    if not isinstance(scene["dock"], list) or len(scene["dock"]) > 32:
        raise ValueError("bounded dock samples required")
    seen, selected = set(), 0
    for app in scene["dock"]:
        fields(app, ("application", "icon", "running", "selected"), "dock slot")
        ident = app["application"]
        if not isinstance(ident, str) or ident not in APPLICATIONS or ident in seen or app["icon"] != APPLICATIONS[ident]:
            raise ValueError("unreviewed or duplicate application/icon identity")
        if type(app["running"]) is not bool or type(app["selected"]) is not bool:
            raise ValueError("dock states must be booleans")
        if app["selected"] and not app["running"]:
            raise ValueError("selected application must be running")
        selected += app["selected"]
        seen.add(ident)
    if selected > 1:
        raise ValueError("only one selected application permitted")
    return scene


def load_scene(path):
    return validate_scene(json.loads(read_regular(Path(path)).decode(),
                          object_pairs_hook=unique_object, parse_constant=reject_constant))
