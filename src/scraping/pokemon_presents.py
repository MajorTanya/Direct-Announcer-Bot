import asyncio
from datetime import UTC, date, datetime, timedelta

import aiohttp
from bs4 import BeautifulSoup, Tag

from src.database import EventDB
from src.events import Events
from src.scraping.scraper_exceptions import ParseException, ScrapeException


async def get_upcoming_pokemon_presents() -> list[datetime]:
    call_time = datetime.now(tz=UTC)

    stored_events = EventDB.get_events(Events.POKEMON)
    if stored_events is not None:
        upcoming: list[datetime] = []
        for event_dt in stored_events:
            if call_time < event_dt:
                upcoming.append(event_dt)
            else:
                EventDB.delete_event(Events.POKEMON, event_dt)

        return upcoming

    scraped_upcoming = await _scrape_bulbapedia()

    if len(scraped_upcoming) == 0:
        EventDB.delete_all_events(Events.POKEMON)

    for dt in scraped_upcoming:
        EventDB.store_event(Events.POKEMON, dt)

    return scraped_upcoming


async def _scrape_bulbapedia() -> list[datetime]:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            "https://bulbapedia.bulbagarden.net/wiki/Pok%C3%A9mon_Presents",
        ) as res:
            body = await res.read()
            if res.status != 200:
                raise ScrapeException("Bulbapedia", res.status, body)

    soup = BeautifulSoup(body, "html.parser")

    toc = soup.find(id="bvTOC")
    assert toc is not None

    # needed to find the latest event
    # can't be truly const since the bot _could_ run across year boundaries
    now = datetime.now(tz=UTC)
    current_year = now.year

    upcoming_presents: list[datetime] = []
    upcoming_elements: list[Tag] = []
    for li in reversed(toc.find_all("li")):
        a_tags = li.find_all("a")
        for a in a_tags:
            # events are grouped by year and then by date - assume the latest link with
            # a ", [year]" fragment (e.g. "February 27, 2026") is the latest Presents
            if a.string is not None and f", {current_year}" in a.string:
                try:
                    a_date = date.strptime(a.text, "%B %d, %Y")
                except ValueError:
                    continue
                else:
                    if a_date < now.date():
                        break
                    if a not in upcoming_elements:
                        upcoming_elements.append(a)

    for a in upcoming_elements:
        latest_href = a.get("href")
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

        if ":" in time_str:
            time_pat = "%I:%M"
        else:
            time_pat = "%I"
        dt = datetime.strptime(f"{date_str} {time_str}", f"%B %d, %Y {time_pat}%p")
        dt = dt - timedelta(hours=2 if is_cest else 1)
        dt = dt.replace(tzinfo=UTC)

        if now >= dt:
            break

        upcoming_presents.append(dt)

    return upcoming_presents


if __name__ == "__main__":
    asyncio.run(_scrape_bulbapedia())
