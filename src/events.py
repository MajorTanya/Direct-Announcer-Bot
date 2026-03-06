import enum
from typing import assert_never


class Events(enum.Enum):
    # fmt: off
    DIRECT  = 0  # noqa: E221
    POKEMON = 1
    # fmt: on

    @classmethod
    def from_str(cls, s: str) -> Events:
        if s == Events.DIRECT.to_str():
            return Events.DIRECT
        elif s == Events.POKEMON.to_str():
            return Events.POKEMON
        else:
            raise ValueError(f"Unknown Event type {s!r}")

    def to_str(self) -> str:
        if self is Events.DIRECT:
            return "direct"
        elif self is Events.POKEMON:
            return "pokemon"
        else:
            assert_never(self)

    def to_job_id(self) -> str:
        if self is Events.DIRECT:
            return f"{self.to_str()}_notify"
        elif self is Events.POKEMON:
            return f"{self.to_str()}_notify"
        else:
            assert_never(self)

    def to_display_str(self) -> str:
        if self is Events.DIRECT:
            return "Nintendo Direct"
        elif self is Events.POKEMON:
            return "Pokémon Presents"
        else:
            assert_never(self)
