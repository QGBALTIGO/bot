import os
os.environ.setdefault("DATABASE_URL", "postgresql://source:source@127.0.0.1:9/source")

from commands.quizopening import _parse_theme


def test_opening_quiz_parser_uses_safe_theme_audio():
    payload = {
        "anime": [{
            "animethemes": [{
                "type": "OP",
                "song": {"title": "Test Song"},
                "animethemeentries": [{
                    "nsfw": False,
                    "spoiler": False,
                    "videos": [{"filename": "Example-NCBD1080"}],
                }],
            }],
        }],
    }
    result = _parse_theme(payload)
    assert result == {
        "audio": "https://a.animethemes.moe/Example-NCBD1080.ogg",
        "type": "OP",
        "song": "Test Song",
    }


def test_opening_quiz_parser_rejects_spoiler_and_nsfw_entries():
    payload = {"anime": [{"animethemes": [
        {"type": "OP", "animethemeentries": [{"spoiler": True, "videos": [{"filename": "A"}]}]},
        {"type": "ED", "animethemeentries": [{"nsfw": True, "videos": [{"filename": "B"}]}]},
    ]}]}
    assert _parse_theme(payload) is None
