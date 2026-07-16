import os


def is_kapsule_borne():
    """True si Kapsule Bar est installe sur cette borne (health.json present)."""
    return os.path.exists(
        os.path.join(os.environ.get("APPDATA", ""), "kapsule-bar", "health.json")
    )
