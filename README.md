# ♠ Kashe Royale — Royal Texas Hold'em

> Kashe Royale is the product name; **PokerStack** is the engine/package (`pokerstack/`) that powers it.

A complete, offline, multi-device **No-Limit Texas Hold'em** table with **virtual chips only**, built for
*Fundamentals of Data Structures* — topic: **Stack**.

Midnight-black felt, polished gold rails, 3D-style cards, side pots, uncalled-bet returns, a real hand
evaluator, and a live **Stack Visualizer** that animates every `push()` and `pop()` in the game.

```bash
python run.py
```

That is the whole setup. No `pip install`, no `npm install`, no build step, no database, no accounts.
Python **3.10+** standard library only. The terminal prints a local URL and a LAN URL, and a browser opens
automatically (pass `--no-browser` to skip, `--port 9000` to pick a port).

---

## 1. Quick start

| Goal | What to do |
| --- | --- |
| Play alone / demo the Stack | **Practice on this screen** (hot-seat, 2–6 seats, all cards visible, undo enabled) |
| Play with friends on Wi-Fi | **Create a table** → share the 5-letter room code or the invite link → each player opens the LAN URL on their own device |
| Play online with a friend | Both open the printed **Network** URL, second player joins with the code |
| Run the tests | `python -m unittest discover -s tests -v` |

Default table: 2 seats, 1 000 virtual chips, blinds 5 / 10, 30-second turn timer. The engine supports
2–10 players; the UI is designed and tested for 2–6 seats.

> If a phone cannot reach the LAN URL, allow Python through the computer firewall (private networks).

---

## 1b. Where to run it / where to host it

**On your own computer (instant):** `python run.py` → open the printed **Local** URL. Friends on the same
Wi-Fi open the **Network** URL and join with the room code. Nothing leaves your machine.

**Quick public link (no account, nothing deployed):** run the game, then tunnel to it with Cloudflare:

```bash
python run.py --no-browser                       # terminal 1: game server on :8000
cloudflared tunnel --url http://127.0.0.1:8000   # terminal 2: public https://<name>.trycloudflare.com
```

Anyone with the printed `trycloudflare.com` link can play while both commands stay open. The link is
throw-away: it dies when the tunnel or your computer stops.

**A permanent URL (free tier):** this is a plain Python process, so it needs a host that runs Python, not a
static site host. It honours the `$PORT` environment variable that these platforms inject, so the start
command is simply `python run.py --no-browser`. The repo already ships the config each one needs:

| Platform | Setup | Notes |
| --- | --- | --- |
| **Render** (free web service) | [render.yaml](render.yaml) is included — push the repo to GitHub, then Render → New → **Blueprint** → pick the repo. Or: New → Web Service → Build: *(empty)* → Start: `python run.py --no-browser` | Simplest; gives a `onrender.com` URL. Free instances sleep after ~15 min idle (first hit takes ~30 s). |
| **Railway** | [Procfile](Procfile) is included — New Project → Deploy from repo | `$PORT` is honoured automatically. |
| **Fly.io / Koyeb / Docker hosts** | [Dockerfile](Dockerfile) is included — `docker build -t kashe-royale . && docker run -p 8000:8000 kashe-royale` | Always-on, more setup. |
| **Any VPS or university server** | `nohup python run.py --no-browser --port 8000 > poker.log 2>&1 &` | Full control; keep the terminal/host running. |

Because tables live in memory, every visitor must reach the **same** running instance, and a restart wipes the
rooms (players just re-create a table). No database, no accounts, no secrets — which is exactly why it is
this easy to host.

---

## 2. Project structure

```
run.py                     one-command launcher (prints local + LAN URL)
pokerstack/
  stack.py                 hand-written Stack ADT  ← the graded data structure
  cards.py                 Card / Suit / Rank model
  deck.py                  52-card deck and burn pile, both Stacks
  evaluator.py             best 5 of 7, all hand classes, exact winning five
  betting.py               wager validation, min-raise and short all-in rules
  pots.py                  PotStack: main pot + side pots, odd-chip splitting
  game.py                  authoritative game engine (state machine)
  history.py               ActionStack (undo snapshots) and HandHistory stack
  rooms.py                 rooms, tokens, presence, seat management, ticker
  server.py                stdlib HTTP server + JSON API + static files
web/
  index.html               lobby, table, action dock, visualizer, modals
  css/theme.css            palette, typography, buttons, panels, ambient light
  css/table.css            oval table, gold rail, seats, chips, pot, layout
  css/cards.css            card faces, suits, backs, flip/deal animations
  css/ui.css               modals, toasts, forms, responsive rules
  js/app.js                application controller (polling, actions, buttons)
  js/api.js                API client + session/room-token storage
  js/render.js             table, seats, dock, modals, cheat sheet, history
  js/cards.js              card element builder and hero card fan
  js/stackviz.js           Stack Visualizer (deck / burn / action / pot / history)
  js/sound.js              WebAudio effects + the generated music bed (no audio files)
tests/
  test_stack.py            the ADT itself (LIFO, underflow, overflow, copies)
  test_deck.py             deck order, burn pile, duplicates, rigged deals
  test_evaluator.py        every hand class, wheel, no wrap-around, ties
  test_betting.py          minimum bet/raise, short all-in, stack limits
  test_pots.py             side-pot layering, folded money, odd chips
  test_game_flow.py        blinds/order, showdown, undo, timeouts, privacy, 3-way all-ins
  test_server.py           full HTTP flows (2 players + practice/undo)
```

---

## 3. The Stack (compulsory requirement)

`pokerstack/stack.py` implements the ADT from scratch — no `collections.deque`, and game logic never
touches a bare Python list:

| Operation | Complexity | Notes |
| --- | --- | --- |
| `push(x)` | O(1) | raises `StackOverflowError` when `max_size` is reached |
| `pop()` | O(1) | raises `StackUnderflowError` when empty |
| `peek()` | O(1) | raises `StackUnderflowError` when empty |
| `is_empty()` / `size()` / `clear()` | O(1) | |
| `to_list_top_first()` | O(n) | returns a copy, so outside code cannot mutate the stack |

### Where the Stack does real work

| Place | How |
| --- | --- |
| **Deck** | The shuffled 52 cards are pushed onto a `Stack`. Dealing is `pop()`. `peek()` is used by demo mode only. |
| **Burn pile** | Before flop, turn and river: `pop()` from the deck, `push()` onto the burn Stack. |
| **Undo / action history** | Every action, blind, deal and street transition is `push()`ed with a full state snapshot. Undo is `pop()` + restore. |
| **Hand history** | Completed hands are `push()`ed, shown newest-first. |
| **Side pots** | Pot layers are a `Stack` of `PotLayer` objects, resolved **top-down** at showdown. |
| **Pending streets** | River, turn, flop are pushed in reverse so `pop()` yields the next street. |

The server sends a `viz` block with deck size, burn size, action-stack top, pot layers and a feed of
`push()` / `pop()` events. The UI's **Stack** panel animates each one, shows the size, highlights the top
element and prints the operation (e.g. `pop() → K♠`). In normal play, hidden card faces are never sent —
only counts and card backs.

---

## 4. Rules implemented (specification-faithful)

* **Deck & shuffle** — 52 unique cards, shuffled with `random.SystemRandom` (OS CSPRNG). A card can never
  appear twice; tests assert this over thousands of deals.
* **Blinds & button** — button moves every hand; SB/BB posted correctly; **heads-up**: the dealer is the
  small blind and acts first pre-flop, and the big blind acts first after the flop.
* **Streets** — pre-flop, flop, turn, river, with a burn card before each of the last three.
* **Actions** — fold, check, bet, call, raise, all-in. Every action is validated server-side with a clear
  error message. Out-of-turn actions are rejected.
* **Minimum raise** — a raise must be at least the size of the previous bet/raise; short all-ins are
  allowed but **do not reopen the betting** (players who already acted may only call or fold).
* **Chip accounting** — total chips are asserted constant after every hand; the table also reports the
  invariant to the UI.
* **Showdown** — best five of seven, royal flush down to high card, kickers, wheel (A-2-3-4-5), no
  wrap-around straights. The exact five winning cards are returned for highlighting. Suits never break
  ties.
* **Pots** — main pot plus as many side pots as there are distinct all-in levels; folded players' chips
  stay in the pot but they can never win it; a player can only win layers they covered; uncalled excess
  is returned to the bettor; split pots are supported.
* **Odd chip rule** — when a pot does not divide evenly, the extra chips go one at a time to the tied
  winners in clockwise order **starting with the first seat left of the dealer button**. Applied
  identically to every pot and every hand.
* **Timeouts / disconnects** — with a turn timer, the acting player auto-checks when possible, otherwise
  auto-folds. Without a timer, a player who stops polling is marked disconnected after ~5 s and auto-acted
  for within ~2 s, so a hand can never freeze. Reconnecting resumes the same seat.
* **Fair play** — each state response is built for one viewer: you receive only your own hole cards.
  Opponents' cards are sent as `{"hidden": true}` until a showdown that actually reveals them. Practice
  mode is the single exception and is clearly labelled.

### Table settings (host, between hands)

Table name, min/max players, starting chips, small/big blind, betting format (No-Limit), optional turn
timer, late joining, spectators, private/open table, and **Demo mode** (undo + deck peek). Changes are
rejected while a hand is running.

---

## 5. Using the table

* **Action dock** — Fold, Check, Call, Raise/Bet with a slider + number box, quick bets (Min, ½ Pot, ¾ Pot,
  Pot, All-in) and a dedicated **All-in** button. Unavailable actions are disabled with the reason shown.
  Keyboard: `F` fold, `C` check/call, `R` raise.
* **Header** — room code (click to copy), **Stack** visualizer, **Ranks** cheat sheet, **History**, **Rules**,
  **Settings**, sound toggle, music toggle, **Leave**.
* **Sound & music** — everything is synthesised in the browser with the Web Audio API, so there are no audio
  files and the game still works offline. `♪` mutes every effect, `♫` starts/stops a soft generated
  jazz-lounge music bed (a I-vi-ii-V pad loop). Both choices are remembered between visits.
* **Between hands** — Start game, Next hand, Sit out, Rebuy (only when below a big blind), Undo (demo),
  Peek deck (demo), Copy invite.
* **Practice mode** — one screen controls every seat, all cards visible, undo rewinds the exact state.
  Perfect for a 5-minute class demo of the Stack.

---

## 6. HTTP API (server-authoritative)

All game state lives on the server; the browser only sends actions and renders what it receives.
Short polling of `GET /api/state` (~1 s, plus immediately after every action) keeps phones and laptops in
sync without WebSockets or third-party packages.

| Method & path | Purpose |
| --- | --- |
| `POST /api/create` | create a table (returns room code + private token) |
| `POST /api/join` | join by code (seat or spectator) |
| `POST /api/practice` | create a hot-seat table |
| `POST /api/start` / `POST /api/next` | deal the first / next hand |
| `POST /api/act` | `fold`, `check`, `call`, `bet`, `raise`, `allin` |
| `POST /api/sit` / `POST /api/rebuy` / `POST /api/leave` | between-hand seat management |
| `POST /api/settings` | host-only settings patch |
| `POST /api/undo` / `POST /api/peek` | demo mode only |
| `GET /api/state?code=…` | per-viewer state (token in `X-Table-Token`) |
| `GET /api/tables` / `GET /api/health` | lobby listing / health |

A table token is required for state and actions, which is what prevents a player from acting on another
seat. Hidden cards never appear in a payload before a legitimate reveal.

---

## 7. Tests

```bash
python -m unittest discover -s tests -v
```

67 tests, all passing. Highlights:

* Stack LIFO order, underflow/overflow, defensive copies, top-first iteration.
* Deck dealing order (`pop`), burn pile growth, no duplicates over many deals, rigged deals for scenarios.
* Every hand class, wheel straight, `Q-K-A-2-3` rejected, kicker tie-breaks, board-plays ties.
* Minimum bet/raise, short all-in allowance, short all-in not reopening raising, stack limits.
* Side-pot layering (3 different all-in levels), folded money, odd-chip distribution, split pots.
* Full game flow: blinds/button/action order, showdown reveal + privacy before it, illegal actions, undo
  restoring exact state, timeouts, disconnects, settings-between-hands, uncalled excess return, folded
  player cannot win, and a randomized thousands-of-hands soak test that asserts chip conservation.

---

## 8. Design notes

* **Palette** — background `#05060a` with a deep navy glow, gold `#d4af37` / `#f5d97a` / `#8a6d1f` rails and
  accents, ivory `#f8f1e3` text. Serif display faces fall back to Georgia/Times when Cinzel/Playfair are not
  installed, so the page never depends on a font CDN.
* **Cards** — built entirely in CSS/JS: ivory face, inner gold hairline, large corner indices, serif pip
  glyphs, layered shadows and a subtle 3D tilt with a sheen on deal. Card backs use a gold-guilloche pattern.
  No images, no external assets, works offline.
* **Table** — oval felt with radial vignette and CSS noise, thick gold rail, inner gold line, seat plates
  with initial avatar, chip stack, dealer button, SB/BB badges, the current bet in front of each seat, and a
  glowing ring + countdown bar for the player to act. The pot renders as growing gold chip stacks with side
  pot layers.
* **No external requests** — the app is fully self-contained (CSP forbids anything off-origin).

---

## 9. Decisions & deviations

* **No WebSockets.** The brief allowed SSE or polling. Short polling with `Cache-Control: no-store` is the
  simplest thing that is robust across browsers, phones and LAN sleep/wake, and it keeps the project
  dependency-free. Polling pauses when the tab is hidden.
* **Practice mode = Demo mode.** Undo and deck peek would be unfair online, so they are available only in
  hot-seat practice, or on a table where the host explicitly enabled Demo mode (clearly shown in the UI).
* **Rebuy threshold.** Rebuy adds the starting stack only when a player holds less than a big blind, keeping
  chip totals meaningful while letting a busted seat keep playing.
* **Odd chip rule** is documented in section 4 and implemented once, in `pots.split_pot`.
* **Seat cap in the UI.** The engine supports 2–10 players; the lobby and settings expose 2–6 because that is
  what the oval layout was designed and tested for.
* **No accounts, no persistence.** Rooms live in memory and disappear when the server stops. That is
  intentional for an offline university demo.
* **Virtual chips only.** There is no deposit, purchase, prize or real-money mechanic anywhere in the code.

---

## 10. Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Address already in use` | The launcher automatically tries the next port; check the printed URL |
| Phone can't connect | Use the printed **Network** URL, same Wi-Fi, allow Python through the firewall |
| "Cannot reach the table server" | `run.py` was stopped — start it again; the table state is in memory |
| Undo button missing | Undo only exists in practice mode or a Demo-mode table (host only) |
| A hand seems paused | A connected player is thinking (or the turn timer is off). A disconnected player is auto-acted for within a few seconds. |
