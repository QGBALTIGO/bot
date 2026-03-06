from typing import Dict


def get_rank_tag(level: int) -> str:
    level = int(level)

    if level >= 120:
        return "👑 Soberano"
    if level >= 100:
        return "💠 Lendário"
    if level >= 80:
        return "🔥 Mestre"
    if level >= 70:
        return "⚔️ Elite"
    if level >= 60:
        return "🛡️ Veterano"
    if level >= 40:
        return "🌟 Especialista"
    if level >= 20:
        return "🚀 Explorador"
    if level >= 5:
        return "✨ Aprendiz"
    return "🌱 Iniciante"


def build_progress_bar(current: int, total: int, size: int = 10) -> str:
    current = max(0, int(current))
    total = max(1, int(total))
    filled = int((current / total) * size)
    filled = max(0, min(size, filled))
    return "█" * filled + "░" * (size - filled)


def format_rank_position(pos: int) -> str:
    pos = int(pos)
    if pos <= 0:
        return "—"
    return f"#{pos}"


def get_level_theme(level: int) -> Dict[str, str]:
    tag = get_rank_tag(level)

    if level >= 100:
        return {"icon": "👑", "tag": tag}
    if level >= 50:
        return {"icon": "🔥", "tag": tag}
    if level >= 10:
        return {"icon": "⭐", "tag": tag}
    return {"icon": "🌿", "tag": tag}
