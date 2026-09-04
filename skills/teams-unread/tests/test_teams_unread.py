import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import teams_unread as tu


def test_parse_chat_item_group_chat_unread_pinned_muted():
    raw = (
        "Unread message Group chat Widgets Team Has pinned messages "
        "Last message Alice Example: Deploy is done Muted AM 10:52"
    )
    result = tu.parse_chat_item(raw)
    assert result == {
        "chat_type": "Group chat",
        "name": "Widgets Team",
        "presence": "",
        "pinned": True,
        "muted": True,
        "unread": True,
        "last_sender": "Alice Example",
        "last_message": "Deploy is done",
        "timestamp_raw": "AM 10:52",
    }
