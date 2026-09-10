import asyncio
from datetime import UTC, datetime
from xml.etree.ElementTree import XMLParser

import aiohttp

from src.database import EventDB
from src.events import Events
from src.scraping.scraper_exceptions import ParseException, ScrapeException


async def get_upcoming_nintendo_directs() -> list[datetime]:
    call_time = datetime.now(tz=UTC)

    stored_events = EventDB.get_events(Events.DIRECT)
    if stored_events is not None:
        upcoming: list[datetime] = []
        for event_dt in stored_events:
            if call_time < event_dt:
                upcoming.append(event_dt)
            else:
                EventDB.delete_event(Events.DIRECT, event_dt)

        return upcoming

    scraped_upcoming = await _scrape_sunappu_rss()

    if len(scraped_upcoming) == 0:
        EventDB.delete_all_events(Events.DIRECT)

    for dt in scraped_upcoming:
        EventDB.store_event(Events.DIRECT, dt)

    return scraped_upcoming


async def _scrape_sunappu_rss() -> list[datetime]:
    now = datetime.now(tz=UTC)
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://nintendodirect.sunappu.net/rss/nintendo-direct",
        ) as res:
            body = await res.read()
            if res.status != 200:
                raise ScrapeException("Sunappu", res.status, body)

    parser = XMLParser()
    parser.feed(body)
    xml_data = parser.close()

    channel = xml_data.find("channel")
    if channel is None:
        raise ParseException("Sunappu", "XML element 'channel' not found")

    upcoming_dts: list[datetime] = []
    for item in channel.iterfind("item"):
        title = item.find("title")
        if title is None or title.text is None:
            raise ParseException("Sunappu", "'title' not found or text was None")

        direct_date = title.text
        dt = datetime.strptime(direct_date, "%B %d, %Y %I:%M %p %Z")
        dt = dt.replace(tzinfo=UTC)

        if now > dt:
            # events are ordered newest -> oldest, so if this is in the past, stop
            break

        upcoming_dts.append(dt)

    return upcoming_dts


if __name__ == "__main__":
    asyncio.run(_scrape_sunappu_rss())
