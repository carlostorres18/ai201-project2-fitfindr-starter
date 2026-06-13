# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env  # then add your GROQ_API_KEY
```

## Running the App

```bash
python app.py        # launches Gradio UI at http://localhost:7860
python agent.py      # CLI test of the agent loop
python tools.py      # manual test of individual tools
python utils/data_loader.py  # verify data loads correctly
```

## Running Tests

```bash
pytest               # run all tests
pytest -k "test_name"  # run a single test
```

## Architecture

FitFindr is a 3-layer AI agent that recommends secondhand clothing. Data flows strictly top-down — nothing goes backwards:

```
User query
  → app.py (Gradio UI)  →  handle_query()
  → agent.py            →  run_agent()
  → tools.py            →  search_listings() → suggest_outfit() → create_fit_card()
```

### State: `agent.py`

`run_agent()` manages a single session dict created by `_new_session()`. The dict accumulates outputs across the 7-step planning loop:

| Key | Set by |
|---|---|
| `parsed` | step 2 — LLM parses query into `{description, size, max_price}` |
| `search_results` | step 3 — `search_listings()` |
| `selected_item` | step 5 — top result from search |
| `outfit_suggestion` | step 6 — `suggest_outfit()` |
| `fit_card` | step 7 — `create_fit_card()` |
| `error` | any step — early-exit signal; check in `app.py` |

### Tools: `tools.py`

Three standalone tools; each takes plain Python values, calls Groq, and returns plain Python values. All use `_get_groq_client()` for LLM access.

- **`search_listings(description, size, max_price)`** — pure logic, no LLM. Filters `data/listings.json` by price/size, ranks by keyword overlap with description, drops zero-score items.
- **`suggest_outfit(new_item, wardrobe)`** — LLM call. Must handle empty wardrobe (general styling advice, not an error).
- **`create_fit_card(outfit, new_item)`** — LLM call. Generates an Instagram/TikTok caption; use higher temperature for variety.

### Data

- `data/listings.json` — 40 mock secondhand listings with fields: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`
- `data/wardrobe_schema.json` — wardrobe format definition plus `example_wardrobe` (10 items) and `empty_wardrobe` (empty template)
- `utils/data_loader.py` — `load_listings()`, `get_example_wardrobe()`, `get_empty_wardrobe()`

### LLM

Uses Groq (not OpenAI). Client is initialized via `GROQ_API_KEY` env var. See `_get_groq_client()` in `tools.py`.

## What Is Already Implemented

The infrastructure is complete; only the business logic is stubbed:

- Gradio UI layout and wiring (`app.py`) — `handle_query()` is a stub
- Agent session structure and entry point (`agent.py`) — the 7-step loop body is a stub
- Tool signatures and docstrings (`tools.py`) — all three bodies are stubs
- Data loading utilities — fully implemented and tested
- Groq client initialization — implemented
