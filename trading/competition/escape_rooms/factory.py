from collections.abc import Callable
from typing import Any

from .base import EscapeRoomEnvironment
from .cipher import CipherPuzzle
from .cybersecurity import CybersecurityEnvironment
from .deterministic import DeterministicRoom
from .filesystem import FileSystemPuzzle
from .gauntlet import GauntletEnvironment
from .infinite_city import InfiniteCityEnvironment
from .negotiation import NegotiationEnvironment
from .werewolf import WerewolfEnvironment

_ROOM_TYPES: dict[str, Callable[[dict[str, Any]], EscapeRoomEnvironment]] = {
    "cipher": CipherPuzzle,
    "cybersecurity": CybersecurityEnvironment,
    "deterministic": DeterministicRoom,
    "filesystem": FileSystemPuzzle,
    "gauntlet": GauntletEnvironment,
    "infinite_city": InfiniteCityEnvironment,
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
