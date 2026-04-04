"""Session utilisateur — stocke l'utilisateur connecté et ses droits."""

_current_user = None


def set_user(user_dict):
    """Définit l'utilisateur connecté. user_dict = {id, nom, role, voir_ca}."""
    global _current_user
    _current_user = user_dict


def get_user():
    """Retourne l'utilisateur connecté ou None."""
    return _current_user


def can_see_ca():
    """Retourne True si l'utilisateur peut voir le CA."""
    if _current_user is None:
        return True  # Pas de protection si pas d'utilisateur
    return bool(_current_user.get("voir_ca", True))


def clear():
    """Déconnecte l'utilisateur."""
    global _current_user
    _current_user = None
