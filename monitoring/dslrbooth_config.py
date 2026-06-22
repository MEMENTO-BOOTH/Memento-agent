"""Resolution dynamique du chemin de base de dslrBooth."""

import os
import json


_FALLBACK_LEGACY = r"C:\dslrBooth"
_SETTINGS_FILENAME = "app_settings_2021.json"


def _read_images_path_from_settings():
    settings_path = os.path.join(
        os.environ.get("APPDATA", ""), "dslrBooth", _SETTINGS_FILENAME
    )
    if not os.path.exists(settings_path):
        return None
    try:
        with open(settings_path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    path = data.get("ImagesPath") or data.get("imagesPath")
    if not path:
        return None
    cleaned = path.rstrip("\\").rstrip("/")
    return cleaned or None


def _user_pictures_dslrbooth():
    profile = os.environ.get("USERPROFILE")
    if not profile:
        return None
    candidate = os.path.join(profile, "Pictures", "dslrBooth")
    return candidate if os.path.isdir(candidate) else None


def get_dslrbooth_base():
    return (
        _read_images_path_from_settings()
        or _user_pictures_dslrbooth()
        or _FALLBACK_LEGACY
    )


if __name__ == "__main__":
    print(get_dslrbooth_base())
