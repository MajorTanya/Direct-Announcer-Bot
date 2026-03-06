import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv

from src.bot import DirectAnnouncerBot
from src.database import bootstrap_db


def main() -> int:
    load_dotenv("./config/.env")

    token = os.getenv("TOKEN")
    if token is None:
        print("Missing TOKEN!", file=sys.stderr)
        return 1

    in_debug_mode = "--debug" in sys.argv

    base_level = logging.DEBUG if in_debug_mode else logging.INFO
    logging.getLogger().setLevel(base_level)
    log_formatter = logging.Formatter(
        fmt="[{asctime}.{msecs:03.0f}] [{levelname:<8}] [{name:<20}]: {message}",
        datefmt="%Y-%m-%d %H:%M:%S",
        style="{",
    )

    stream_handler = logging.StreamHandler(stream=sys.stdout)
    stream_handler.setFormatter(log_formatter)
    stream_handler.setLevel(logging.DEBUG if in_debug_mode else logging.WARNING)

    bot_logger = logging.getLogger("dabot")
    bot_logger.setLevel(base_level)
    bot_logger.addHandler(stream_handler)

    discord_py_logger = logging.getLogger("discord")
    discord_py_logger.setLevel(logging.INFO)
    discord_py_logger.addHandler(stream_handler)

    if not in_debug_mode:
        log_path = os.path.join(os.getcwd(), ".logs")
        if not os.path.exists(log_path):
            os.mkdir(log_path)

        now_iso_safe = (
            datetime.now().isoformat(sep="_", timespec="seconds").replace(":", "-")
        )
        file_name = f"{now_iso_safe}.log"
        file_handler = logging.FileHandler(
            filename=os.path.join(log_path, file_name),
            mode="w",
            encoding="utf8",
        )
        file_handler.setFormatter(log_formatter)
        file_handler.setLevel(logging.INFO)

        bot_logger.addHandler(file_handler)
        discord_py_logger.addHandler(file_handler)

    bootstrap_db()

    bot = DirectAnnouncerBot(debug_mode=in_debug_mode)
    bot.run(token, log_handler=None)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
