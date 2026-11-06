"""TF2 class name / id helpers shared across bounded contexts.

Pure taxonomy helpers only — rating math lives in the query service.
"""

from __future__ import annotations

CLASS_MAP = {
    "scout": 0,
    "soldier": 1,
    "pyro": 2,
    "demoman": 3,
    "heavyweapons": 4,
    "engineer": 5,
    "medic": 6,
    "sniper": 7,
    "spy": 8,
}

CLASS_ID_TO_NAME = {class_id: name for name, class_id in CLASS_MAP.items()}


def normalize_class_name(raw: str | None) -> str:
    value = (raw or "unknown").strip().lower()
    aliases = {
        "heavy": "heavyweapons",
        "heavyweapons": "heavyweapons",
        "demo": "demoman",
        "demoman": "demoman",
        "med": "medic",
        "engi": "engineer",
    }
    return aliases.get(value, value or "unknown")


def class_id_from_name(name: str | None) -> int:
    return CLASS_MAP.get(normalize_class_name(name), 0)


def class_name_from_id(class_id: int) -> str:
    return CLASS_ID_TO_NAME.get(int(class_id), "unknown")


def primary_class(classes_played: list[str] | None) -> str:
    if not classes_played:
        return "unknown"
    return normalize_class_name(classes_played[0])
