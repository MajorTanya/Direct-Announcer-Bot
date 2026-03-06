<!-- START doctoc generated TOC please keep comment here to allow auto update -->
<!-- DON'T EDIT THIS SECTION, INSTEAD RE-RUN doctoc TO UPDATE -->
**Table of Contents**

- [Setup](#setup)
- [Subscribing to an event](#subscribing-to-an-event)
- [Unsubscribing from an event](#unsubscribing-from-an-event)
- [Disclaimer](#disclaimer)

<!-- END doctoc generated TOC please keep comment here to allow auto update -->

# Direct Announcer Bot

Tired of missing Nintendo's super short notice Directs and Pokémon Presents events and
then getting spoiled to hell and back on social media? Me too.

That's why I made this little Discord bot. It scours the internet[^1] for these events
and then conveniently pings a role of your choice five minutes before[^2] the next one
is due to start with a link to the respective YouTube channel that will host the event.

Currently, the bot is _not_ able to link the Direct/Presents video directly because
they're usually not available early on when the bot discovers the new event.

To compensate, _the bot will link to the respective YouTube channel's specific Videos
tab_, where the presentation should be the first video, or at the very least a video
very high up in the list (e.g. the Pokémon YouTube Channel often schedules a lot of live
streams regarding regional tournaments, etc.).

[^1]: Specifically,
[Bulbapedia](https://bulbapedia.bulbagarden.net/wiki/Pok%C3%A9mon_Presents) for Pokémon
Presents events
and [Sunappu's Nintendo Direct countdown](https://nintendodirect.sunappu.net/en) for
Nintendo Direct events.

[^2]: Exact timing is subject to change, but it will always be _before_ the actual
event starts.

## Setup

1. [Invite the bot to your server](https://discord.com/oauth2/authorize?client_id=1476649795014627380)
2. Allow the `Manage Roles` permission
    - required because the bot needs to assign/remove the ping roles to/from users via
      the `/subscribe`/`/unsubscribe` commands
3. Configure the bot with the `configure` commands (Slash Commands)
    1. `/configure channel` -- which channel the bot should ping users in
4. Set up the notifications you wish to enable:

    - Nintendo Directs
      This includes all types of Direct, including movie directs, Partner Showcases,
      etc.
        1. `/configure directs` -- whether to enable pings for Nintendo Directs
        2. `/configure directs-ping` -- which role to ping for Nintendo Directs

    - Pokémon Presents
        1. `/configure pokemon` -- whether to enable pings for Pokémon Presents
        2. `/configure pokemon-ping` -- which role to ping for Pokémon Presents

5. Done! Now let your users use the `/subscribe` & `/unsubscribe` commands as shown
   below.

## Subscribing to an event

This is very simple, just use the `/subscribe` subcommand for the event you'd like to be
pinged for:

**Nintendo Directs**:

- `/subscribe directs`

**Pokémon Presents**:

- `/subscribe pokemon`

## Unsubscribing from an event

No longer wish to be pinged for an event? Simply use the specific `/unsubscribe`
subcommand like this:

**Nintendo Directs**:

- `/unsubscribe directs`

**Pokémon Presents**:

- `/unsubscribe pokemon`

## Disclaimer

This project is not affiliated with or endorsed by either Nintendo or The Pokémon
Company.
