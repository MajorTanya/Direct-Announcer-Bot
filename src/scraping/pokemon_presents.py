import asyncio
from datetime import UTC, datetime, timedelta

import aiohttp
from bs4 import BeautifulSoup

from src.database import EventDB
from src.events import Events
from src.scraping.scraper_exceptions import ParseException, ScrapeException


async def get_next_pokemon_presents() -> datetime | None:
    call_time = datetime.now(tz=UTC)

    stored_dt = EventDB.get_event_timestamp(Events.POKEMON)
    if stored_dt is not None and call_time < stored_dt:
        return stored_dt

    scraped_dt = await _scrape_bulbapedia()

    if call_time > scraped_dt:  # no future presents known at this time
        EventDB.delete_event_timestamp(Events.POKEMON)
        return None

    EventDB.store_event_timestamp(Events.POKEMON, scraped_dt)

    return scraped_dt


async def _scrape_bulbapedia() -> datetime:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://bulbapedia.bulbagarden.net/wiki/Pok%C3%A9mon_Presents",
        ) as res:
            body = await res.read()
            if res.status != 200:
                raise ScrapeException("Bulbapedia", res.status, body)

    soup = BeautifulSoup(body, "html.parser")

    toc = soup.find(id="toc")
    assert toc is not None

    found_newest = False
    latest_a_tag = None
    for li in toc.find_all("li")[::-1]:
        if found_newest:
            break
        spans = li.find_all("span", class_="tocnumber")
        for span in spans:
            # actual presents headings are subpoints of the year they aired in
            # (e.g. 2026 is span 13, first Presents in 2026 is span 13.1, etc)
            if span.string is not None and "." in span.string:
                found_newest = True
                latest_a_tag = span.find_parent()
                break

    assert latest_a_tag is not None

    latest_href = latest_a_tag.get("href")
    assert latest_href is not None
    assert isinstance(latest_href, str)

    heading_span = None
    p_tag = None
    for h3 in soup.find_all("h3"):
        child_spans = h3.find_all("span", id=latest_href.removeprefix("#"))
        if len(child_spans) > 0:
            heading_span = child_spans[0]
            p_tag = h3.find_next_sibling("p")
            break

    assert heading_span is not None
    assert p_tag is not None

    date_str = heading_span.text.strip()
    display_text = p_tag.text.strip()
    is_cest = "CEST" in display_text
    if "CET" in display_text or "CEST" in display_text:
        europe_index = display_text.find(", Europe ") + len(", Europe ")
        end_index = display_text.find(",", europe_index)
        time_str = (
            display_text[europe_index:end_index]
            .removesuffix(" CET")
            .removesuffix(" CEST")
            .strip()
        )
    else:
        raise ParseException("Bulbapedia", "Could not find Europe time zone info")

    dt = datetime.strptime(f"{date_str} {time_str}", "%B %d, %Y %I%p")
    dt = dt - timedelta(hours=2 if is_cest else 1)
    dt = dt.replace(tzinfo=UTC)

    return dt


if __name__ == "__main__":
    asyncio.run(_scrape_bulbapedia())
