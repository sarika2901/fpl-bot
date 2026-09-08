# FPL Bot 🏆

A Discord bot that gives Fantasy Premier League managers live squad summaries, transfer suggestions, and captain picks — powered by a trained ML scoring model and the official FPL API.

Built as a learning project (my first real Python project), going from raw API calls to a trained regression model to a deployed multi-user Discord bot.

---

## Features

- **`/register`** — link your FPL team ID to your Discord account once, no need to re-enter it every time.
- **`/team`** — live squad summary: optimal starting XI (auto-picked across every valid formation), bench, points, and injury/availability flags.
- **`/transfers`** — ML-scored transfer suggestions, aware of:
  - **Free transfers banked** (respects FPL's 1-per-week, max-2-banked rule)
  - **-4 point hits** — only suggested when the projected score gain clears a worthwhile threshold
  - **Active chips** (Wildcard / Free Hit make transfers free that week)
  - **Unused Wildcard nudges** — flags when a Wildcard might be more efficient than several small hits
  - Injured/doubtful players, prioritized as transfer-out candidates
- **`/captain`** — captain **and vice-captain** suggestions, scored by the ML model and adjusted for upcoming fixture difficulty.
- **Gameweek-deadline aware** — suggestions automatically target the next actionable gameweek once the current one locks, with a clear notice when squad data might be stale (a public-API limitation, not a bug).

## How it works

1. **Data** — pulled live from the official [Fantasy Premier League API](https://fantasy.premierleague.com/api/bootstrap-static/) (player stats, prices, fixtures, manager picks/history).
2. **Scoring** — a Linear Regression model trained on historical rolling player performance (form, points-per-cost, fixture difficulty, etc.) predicts each player's expected score for the upcoming gameweek. This beat a Random Forest baseline (MAE ≈ 2.03 points) during model selection.
3. **Recommendation engine** — combines model scores with live FPL rules (transfer costs, chip status, budget, availability) to produce advice, not just raw predictions.
4. **Discord layer** — slash commands (`discord.py`) let any server member register their own team and query it independently.

## Tech stack

- Python
- `discord.py` — bot framework / slash commands
- `pandas` — data wrangling
- `scikit-learn` — model training
- `requests` — FPL API calls
- `python-dotenv` — environment config

## Project structure

```
fpl-bot/
├── api/
│   └── data_fetcher.py       # FPL API calls (players, fixtures, manager info/picks/history)
├── analysis/
│   ├── team_analyzer.py      # squad building, starting XI logic, free transfer/chip tracking
│   └── transfer_engine.py    # transfer + captain/vice-captain suggestion logic
├── bot/
│   ├── discord_bot.py        # Discord slash commands
│   └── user_registry.py      # maps Discord users to their FPL team IDs
├── scoring.py                 # loads the trained model, builds live feature vectors
├── data/
│   └── processed/
│       └── training_data.csv # historical rolling-average training data
├── config/
│   └── my_squad.json         # mock squad for offline/pre-season testing
└── requirements.txt
```

## Setup

1. Clone the repo and create a virtual environment:
   ```bash
   git clone https://github.com/sarika2901/fpl-bot.git
   cd fpl-bot
   python -m venv venv
   venv\Scripts\activate      # Windows
   source venv/bin/activate   # macOS/Linux
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file in the project root:
   ```
   DISCORD_BOT_TOKEN=your_discord_bot_token_here
   ```
4. Run the bot:
   ```bash
   python bot/discord_bot.py
   ```
5. In Discord, register your team and try it out:
   ```
   /register team_id:<your FPL team ID>
   /team
   /transfers
   /captain
   ```
   (Find your team ID in your FPL team URL: `fantasy.premierleague.com/entry/<team_id>/event/...`)

## Status

Core features are built and working locally: squad summaries, ML-scored transfer suggestions, chip-aware transfer economy, and captain/vice-captain picks. Currently in a fine-tuning + hardening pass (error handling, data persistence, deployment config) ahead of hosting on Railway for 24/7 availability.

## Known limitations

- The public FPL API only exposes a manager's squad **as it was locked at the last gameweek deadline** — transfers made after that deadline but before the next one aren't visible until the new gameweek locks. The bot flags this explicitly rather than showing stale data silently.
- Selling price is approximated from current market price rather than each player's exact purchase-price-based sell value (the FPL API doesn't expose true sell value without an authenticated session).

## License

Personal/educational project (No License)
