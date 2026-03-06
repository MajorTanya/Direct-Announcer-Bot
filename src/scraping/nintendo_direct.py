import asyncio
from datetime import UTC, datetime
from xml.etree.ElementTree import XMLParser

import aiohttp

from src.database import EventDB
from src.events import Events
from src.scraping.scraper_exceptions import ParseException, ScrapeException


async def get_next_nintendo_direct() -> datetime | None:
    call_time = datetime.now(tz=UTC)

    stored_dt = EventDB.get_event_timestamp(Events.DIRECT)
    if stored_dt is not None and call_time < stored_dt:
        return stored_dt

    scraped_dt = await _scrape_sunappu_rss()

    if call_time > scraped_dt:  # no future direct known at this time
        EventDB.delete_event_timestamp(Events.DIRECT)
        return None

    EventDB.store_event_timestamp(Events.DIRECT, scraped_dt)

    return scraped_dt


async def _scrape_sunappu_rss() -> datetime:
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
    first_item = channel.find("item")
    if first_item is None:
        raise ParseException("Sunappu", "First 'item' not found")
    title = first_item.find("title")
    if title is None or title.text is None:
        raise ParseException("Sunappu", "First 'title' not found or text was None")

    direct_date = title.text
    dt = datetime.strptime(direct_date, "%B %d, %Y %I:%M %p %Z")
    dt = dt.replace(tzinfo=UTC)

    return dt


if __name__ == "__main__":
    asyncio.run(_scrape_sunappu_rss())
