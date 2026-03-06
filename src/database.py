import logging
import sqlite3
import textwrap
from datetime import datetime
from typing import NamedTuple

from src.events import Events


class EventSettings(NamedTuple):
    event: Events
    channel_id: int
    ping_role_id: int


_DB_FILE_NAME = "direct_scraper.db"
_LOGGER = logging.getLogger(f"dabot.{__name__}")

# region DDL
_CREATE_GUILDS_TABLE = textwrap.dedent(
    """
    CREATE TABLE IF NOT EXISTS guilds
    (
        guild_id              INTEGER PRIMARY KEY,
        channel_id            INTEGER DEFAULT NULL,
        direct_ping_role_id   INTEGER DEFAULT NULL,
        pokemon_ping_role_id  INTEGER DEFAULT NULL,
        direct_pings_enabled  BOOLEAN DEFAULT FALSE,
        pokemon_pings_enabled BOOLEAN DEFAULT FALSE
    );
    """.strip(),
)
_CREATE_TIMESTAMPS_TABLE = textwrap.dedent(
    """
    CREATE TABLE IF NOT EXISTS timestamps
    (
        key               INTEGER PRIMARY KEY,
        pokemon_timestamp TEXT,
        direct_timestamp  TEXT
    );
    """.strip(),
)
_CREATE_LOGS_TABLE = textwrap.dedent(
    """
    CREATE TABLE IF NOT EXISTS logs
    (
        check_timestamp TEXT,
        event           TEXT
    )
    """.strip(),
)
# endregion

# region Events DML
_DELETE_DIRECT_TIMESTAMP = (
    "UPDATE timestamps SET direct_timestamp = NULL WHERE key = 1;"
)
_DELETE_POKEMON_TIMESTAMP = (
    "UPDATE timestamps SET pokemon_timestamp = NULL WHERE key = 1;"
)

_INSERT_DIRECT_TIMESTAMP = (
    "INSERT OR REPLACE INTO timestamps (key, direct_timestamp) VALUES (1, ?);"
)
_INSERT_POKEMON_TIMESTAMP = (
    "INSERT OR REPLACE INTO timestamps (key, pokemon_timestamp) VALUES (1, ?);"
)

_SELECT_DIRECT_TIMESTAMP = (
    "SELECT direct_timestamp FROM timestamps WHERE key = 1 LIMIT 1;"
)
_SELECT_POKEMON_TIMESTAMP = (
    "SELECT pokemon_timestamp FROM timestamps WHERE key = 1 LIMIT 1;"
)
# endregion

# region Guilds DML
_INSERT_OR_IGNORE_GUILD_WITH_ID_ONLY = (
    "INSERT OR IGNORE INTO guilds (guild_id) VALUES (?);"
)
_SELECT_DIRECT_ENABLED_GUILDS = textwrap.dedent(
    """
    SELECT guild_id, channel_id, direct_ping_role_id
    FROM guilds WHERE direct_pings_enabled = TRUE;
    """.strip(),
)
_SELECT_POKEMON_ENABLED_GUILDS = textwrap.dedent(
    """
    SELECT guild_id, channel_id, pokemon_ping_role_id
    FROM guilds WHERE pokemon_pings_enabled = TRUE;
    """.strip(),
)

_SET_PING_CHANNEL = "UPDATE guilds SET channel_id = ? WHERE guild_id = ?;"
_SELECT_PING_CHANNEL = "SELECT channel_id FROM guilds WHERE guild_id = ? LIMIT 1;"

_SET_DIRECT_PINGS_ENABLED = (
    "UPDATE guilds SET direct_pings_enabled = ? WHERE guild_id = ?;"
)
_SELECT_DIRECT_PINGS_ENABLED = (
    "SELECT direct_pings_enabled FROM guilds WHERE guild_id = ? LIMIT 1;"
)

_SET_POKEMON_PINGS_ENABLED = (
    "UPDATE guilds SET pokemon_pings_enabled = ? WHERE guild_id = ?;"
)
_SELECT_POKEMON_PINGS_ENABLED = (
    "SELECT pokemon_pings_enabled FROM guilds WHERE guild_id = ? LIMIT 1;"
)

_SET_DIRECT_PING_ROLE_ID = (
    "UPDATE guilds SET direct_ping_role_id = ? WHERE guild_id = ?;"
)
_SELECT_DIRECT_PING_ROLE_ID = (
    "SELECT direct_ping_role_id FROM guilds WHERE guild_id = ? LIMIT 1;"
)

_SET_POKEMON_PING_ROLE_ID = (
    "UPDATE guilds SET pokemon_ping_role_id = ? WHERE guild_id = ?;"
)
_SELECT_POKEMON_PING_ROLE_ID = (
    "SELECT pokemon_ping_role_id FROM guilds WHERE guild_id = ? LIMIT 1;"
)
# endregion

# region Logs DML
_INSERT_LOG_TIMESTAMP = "INSERT INTO logs (check_timestamp, event) VALUES (?, ?);"
# endregion


def bootstrap_db() -> None:
    try:
        with sqlite3.connect(_DB_FILE_NAME) as conn:
            cur = conn.cursor()
            cur.execute(_CREATE_GUILDS_TABLE)
            cur.execute(_CREATE_LOGS_TABLE)
            cur.execute(_CREATE_TIMESTAMPS_TABLE)
    except sqlite3.Error as e:
        _LOGGER.error("Failed to initialise sqlite3 db!", exc_info=e)
        raise
    else:
        _LOGGER.info("Initialised sqlite3 db successfully!")

    return None


class GuildDB:
    @staticmethod
    def add_guild(guild_id: int) -> None:
        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(_INSERT_OR_IGNORE_GUILD_WITH_ID_ONLY, (guild_id,))
                conn.commit()
        except sqlite3.Error as e:
            _LOGGER.error("Error adding guild %d:", guild_id, exc_info=e)

        return None

    @staticmethod
    def get_all_guilds_for_event(event: Events) -> dict[int, EventSettings]:
        if event is Events.DIRECT:
            query = _SELECT_DIRECT_ENABLED_GUILDS
        else:
            query = _SELECT_POKEMON_ENABLED_GUILDS

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query)
                rows = cur.fetchall()
        except sqlite3.Error as e:
            _LOGGER.error("Error getting enabled guilds for %r", event, exc_info=e)
            return {}
        else:
            out: dict[int, EventSettings] = {}

            for row in rows:
                guild_id = int(row[0])
                channel_id = int(row[1])
                role_id = int(row[2])
                out[guild_id] = EventSettings(
                    event=event,
                    channel_id=channel_id,
                    ping_role_id=role_id,
                )

            return out

    @staticmethod
    def set_channel(guild_id: int, channel_id: int | None) -> None:
        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(_SET_PING_CHANNEL, (channel_id, guild_id))
                conn.commit()
        except sqlite3.Error as e:
            _LOGGER.error(
                "Error setting channel %d for guild %d:",
                channel_id,
                guild_id,
                exc_info=e,
            )

        return None

    @staticmethod
    def get_channel(guild_id: int) -> int | None:
        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(_SELECT_PING_CHANNEL, (guild_id,))
                row = cur.fetchone()
        except sqlite3.Error as e:
            _LOGGER.error("Error getting ping channel for guild {guild_id}:", e)
            return None
        else:
            return int(row[0])

    @staticmethod
    def set_ping_role(
        guild_id: int,
        event: Events,
        role_id: int,
    ) -> None:
        query = (
            _SET_DIRECT_PING_ROLE_ID
            if event == Events.DIRECT
            else _SET_POKEMON_PING_ROLE_ID
        )

        _LOGGER.debug("Query: %r", query)

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query, (role_id, guild_id))
                conn.commit()
        except sqlite3.Error as e:
            _LOGGER.error(
                "Error setting ping role %d for %r in guild %d",
                role_id,
                event,
                guild_id,
                exc_info=e,
            )

        return None

    @staticmethod
    def get_ping_role(guild_id: int, event: Events) -> int | None:
        query = (
            _SELECT_DIRECT_PING_ROLE_ID
            if event == Events.DIRECT
            else _SELECT_POKEMON_PING_ROLE_ID
        )

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query, (guild_id,))
                row = cur.fetchone()
        except sqlite3.Error as e:
            _LOGGER.error(
                "Error getting ping role for %r in guild %d",
                event,
                guild_id,
                exc_info=e,
            )
            return None
        else:
            return int(row[0])

    @staticmethod
    def set_pings_enabled(
        guild_id: int,
        event: Events,
        pings_enabled: bool,
    ) -> None:
        query = (
            _SET_DIRECT_PINGS_ENABLED
            if event is Events.DIRECT
            else _SET_POKEMON_PINGS_ENABLED
        )

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query, (pings_enabled, guild_id))
                conn.commit()
        except sqlite3.Error as e:
            _LOGGER.error(
                "Error setting pings state to %r for %r in %d",
                pings_enabled,
                event,
                guild_id,
                exc_info=e,
            )

        return None

    @staticmethod
    def get_pings_enabled(guild_id: int, event: Events) -> bool:
        query = (
            _SELECT_DIRECT_PINGS_ENABLED
            if event is Events.DIRECT
            else _SELECT_POKEMON_PINGS_ENABLED
        )

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query, (guild_id,))
                row = cur.fetchone()
        except sqlite3.Error as e:
            _LOGGER.error(
                "Error getting ping state for %r in guild %d",
                event,
                guild_id,
                exc_info=e,
            )
            return False
        else:
            return int(row[0]) == 1


class EventDB:
    @staticmethod
    def delete_event_timestamp(event: Events) -> bool:
        query = (
            _DELETE_DIRECT_TIMESTAMP
            if event is Events.DIRECT
            else _DELETE_POKEMON_TIMESTAMP
        )

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query)
                conn.commit()
        except sqlite3.Error as e:
            _LOGGER.error("Error deleting %r timestamp", event, exc_info=e)
            return False

        return True

    @staticmethod
    def get_event_timestamp(event: Events) -> datetime | None:
        query = (
            _SELECT_DIRECT_TIMESTAMP
            if event is Events.DIRECT
            else _SELECT_POKEMON_TIMESTAMP
        )

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query)
                row = cur.fetchone()
        except sqlite3.Error as e:
            _LOGGER.error("Error getting %r timestamp", event, exc_info=e)
            return None
        else:
            if row is None or row[0] is None:
                return None
            return datetime.fromisoformat(row[0])

    @staticmethod
    def store_event_timestamp(event: Events, timestamp: datetime) -> None:
        query = (
            _INSERT_DIRECT_TIMESTAMP
            if event is Events.DIRECT
            else _INSERT_POKEMON_TIMESTAMP
        )

        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(query, (timestamp.isoformat(),))
                conn.commit()
        except sqlite3.Error as e:
            _LOGGER.error(
                "Error inserting %r timestamp (%r)",
                event,
                timestamp.isoformat(),
                exc_info=e,
            )

        return None


class LogDB:
    @staticmethod
    def log_run(event: Events, dt: datetime) -> None:
        try:
            with sqlite3.connect(_DB_FILE_NAME) as conn:
                cur = conn.cursor()
                cur.execute(
                    _INSERT_LOG_TIMESTAMP,
                    (dt.isoformat(), event.to_str()),
                )
                conn.commit()
        except sqlite3.Error as e:
            _LOGGER.error(
                "Error inserting log timestamp (%r)",
                dt.isoformat(),
                exc_info=e,
            )

        return None
