from collections.abc import Callable
from typing import Any

from .base import EscapeRoomEnvironment
from .cipher import CipherPuzzle
from .deterministic import DeterministicRoom
from .filesystem import FileSystemPuzzle
from .gauntlet import GauntletEnvironment
from .negotiation import NegotiationEnvironment
from .werewolf import WerewolfEnvironment

_ROOM_TYPES: dict[str, Callable[[dict[str, Any]], EscapeRoomEnvironment]] = {
    "cipher": CipherPuzzle,
    "deterministic": DeterministicRoom,
    "filesystem": FileSystemPuzzle,
    "gauntlet": GauntletEnvironment,
    "negotiation": NegotiationEnvironment,
    "werewolf": WerewolfEnvironment,
}


def create_room(
    room_type: str,
    config: dict[str, Any],
) -> EscapeRoomEnvironment:
    room_class = _ROOM_TYPES.get(room_type)
    if not room_class:
        raise ValueError(
            f"Unknown room type: {room_type}. Available: {list(_ROOM_TYPES.keys())}"
        )
    return room_class(config)


def get_available_room_types() -> list[str]:
    return list(_ROOM_TYPES.keys())
