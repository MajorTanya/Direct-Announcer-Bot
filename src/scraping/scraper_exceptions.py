from typing import Literal


class ScrapeException(Exception):

    def __init__(
        self,
        source: Literal["Bulbapedia", "Sunappu"],
        status: int,
        raw_payload: bytes,
    ) -> None:
        self.msg = (
            f"Could not scrape {source}: Failed with status {status}. Raw payload: "
            f"{raw_payload!r}"
        )
        super().__init__()


class ParseException(Exception):

    def __init__(self, source: Literal["Bulbapedia", "Sunappu"], context: str) -> None:
        self.msg = f"Could not parse {source} response. {context}"
        super().__init__()
