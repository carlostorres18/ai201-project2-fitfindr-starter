# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Loads all listings from `data/listings.json`, filters them by size and price ceiling, scores each remaining item by counting how many words from `description` appear in the listing's title, description, and style_tags, then returns the survivors sorted best-match first with zero-score items removed.

**Input parameters:**
- `description` (str): free-text keywords extracted from the user's query (e.g. `"vintage graphic tee"`)
- `size` (str | None): clothing size to filter by, case-insensitive substring match against the listing's `size` field (e.g. `"M"` matches `"S/M"`); `None` skips the size filter
- `max_price` (float | None): upper price ceiling in dollars, inclusive; `None` skips the price filter

**What it returns:**
A list of listing dicts sorted by keyword-match score descending. Each dict has: `id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str), `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Returns an empty list if nothing passes all filters or every surviving item scores zero.

**What happens if it fails or returns nothing:**
If the returned list is empty, set `session["error"]` to a user-facing message (e.g. `"No listings matched your search. Try different keywords, a higher price, or leave size blank."`) and return the session immediately without calling any further tools.

---

### Tool 2: suggest_outfit

**What it does:**
Calls the Groq LLM to pair `new_item` with pieces from the user's wardrobe, producing 1–2 complete outfit descriptions. If the wardrobe is empty it asks the LLM for general styling advice for the item instead of attempting to match wardrobe pieces.

**Input parameters:**
- `new_item` (dict): a single listing dict as returned by `search_listings` — the agent passes `session["selected_item"]`, which is `session["search_results"][0]`
- `wardrobe` (dict): the user's wardrobe with an `"items"` key containing a list of wardrobe item dicts; each item has `id`, `name`, `category`, `colors`, `style_tags`, and optional `notes`; an empty wardrobe has `"items": []`

**What it returns:**
A non-empty string describing 1–2 outfits. When the wardrobe has items, each outfit names specific wardrobe pieces by their `name` field paired with the new item. When the wardrobe is empty, the string gives general styling suggestions based on the item's category, colors, and style_tags without referencing any specific pieces.

**What happens if it fails or returns nothing:**
If the LLM returns an empty or whitespace-only string, store a fallback message in `session["outfit_suggestion"]` (e.g. `"Style this item your way — it pairs well with both casual and dressed-up looks."`) and continue to `create_fit_card` rather than treating it as a hard error.

---

### Tool 3: create_fit_card

**What it does:**
Calls the Groq LLM at a higher temperature (≥ 0.9) to generate a 2–4 sentence Instagram/TikTok-style caption that mentions the item's name, price, and platform once each and captures the outfit's vibe in specific terms (e.g. "soft grunge" or "quiet luxury" rather than "stylish").

**Input parameters:**
- `outfit` (str): the outfit suggestion string from `suggest_outfit` — must be non-empty; if it is empty or whitespace only, skip the LLM call entirely
- `new_item` (dict): the same listing dict passed to `suggest_outfit`, used to pull `title`, `price`, and `platform` into the caption

**What it returns:**
A 2–4 sentence string written in second-person present tense (e.g. "You're giving…", "Pair it with…") that reads like an influencer caption, not a product description.

**What happens if it fails or returns nothing:**
If `outfit` is empty/whitespace, set `session["fit_card"]` to `""` and return without calling the LLM. If the LLM returns an empty string, set `session["fit_card"]` to `""` and continue — the UI in `app.py` should handle an empty fit card gracefully by hiding that output panel rather than showing a blank box.

---

### Additional Tools (if any)

<!-- Copy the block above for any tools beyond the required three -->

---

## Planning Loop

**How does your agent decide which tool to call next?**
The loop always runs the same sequence — it is not dynamic — but it short-circuits on failure at two points:

1. **Parse** — call the LLM with the raw `query` to extract `{description, size, max_price}` as a JSON object; store in `session["parsed"]`.
2. **Search** — call `search_listings(description, size, max_price)` with the parsed fields; store result in `session["search_results"]`.
3. **Guard: empty results** — if `session["search_results"]` is an empty list, set `session["error"]` and `return session` immediately. Steps 4–7 are skipped entirely.
4. **Select** — set `session["selected_item"] = session["search_results"][0]` (highest-scoring item, no LLM needed).
5. **Outfit** — call `suggest_outfit(session["selected_item"], session["wardrobe"])`; store result in `session["outfit_suggestion"]`.
6. **Fit card** — call `create_fit_card(session["outfit_suggestion"], session["selected_item"])`; store result in `session["fit_card"]`.
7. **Done** — return `session`. The loop knows it is done because there are no more steps; it does not poll or loop back.

---

## State Management

**How does information from one tool get passed to the next?**
`run_agent()` creates one session dict at the start of the call via `_new_session(query, wardrobe)` and mutates it in-place through the 7 steps. Nothing is returned from a step except the value written into the dict; each subsequent step reads from that dict rather than receiving a return value directly.

Concrete hand-offs:
- `session["parsed"]` is written in step 1 and destructured into `description`, `size`, `max_price` before the step 2 call.
- `session["search_results"]` is written in step 2, checked for emptiness in step 3, and indexed at `[0]` in step 4.
- `session["selected_item"]` is written in step 4 and passed as `new_item` to both `suggest_outfit` (step 5) and `create_fit_card` (step 6).
- `session["outfit_suggestion"]` is written in step 5 and passed as `outfit` to `create_fit_card` (step 6).
- `session["wardrobe"]` is set at initialization from the argument passed by `app.py` and never modified.
- `session["error"]` is set only on early exit; `app.py` checks for it first and displays the error message instead of the three output panels.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Set `session["error"]` to a user-facing message and return `session` immediately; skip all remaining steps |
| suggest_outfit | Wardrobe is empty (`items: []`) | Pass the wardrobe as-is; the tool detects the empty list and asks the LLM for general styling advice instead — not an error, execution continues |
| create_fit_card | `outfit` is an empty or whitespace-only string | Skip the LLM call; set `session["fit_card"] = ""`; `app.py` hides the fit card panel rather than showing a blank |

---

## Architecture

```
app.py
  handle_query(user_query, wardrobe_choice)
  │  selects wardrobe dict (example or empty)
  └─► run_agent(query, wardrobe)                         agent.py
        │
        ├─[step 1] LLM parse query
        │           → session["parsed"] = {description, size, max_price}
        │
        ├─[step 2] search_listings(description, size, max_price)
        │           → session["search_results"] = [listing, ...]
        │
        ├─[step 3] if search_results is empty:
        │           → session["error"] = "No listings matched…"
        │           → return session  ──────────────────────────────► app.py shows error
        │
        ├─[step 4] selected_item = search_results[0]
        │           → session["selected_item"]
        │
        ├─[step 5] suggest_outfit(selected_item, wardrobe)
        │           │  if wardrobe["items"] == []:
        │           │      LLM → general styling advice
        │           │  else:
        │           │      LLM → outfits using wardrobe pieces
        │           → session["outfit_suggestion"] = str
        │
        ├─[step 6] create_fit_card(outfit_suggestion, selected_item)
        │           │  if outfit_suggestion is empty:
        │           │      skip LLM → session["fit_card"] = ""
        │           │  else:
        │           │      LLM (temp ≥ 0.9) → caption
        │           → session["fit_card"] = str
        │
        └─[step 7] return session
                        │
                        ▼
                   app.py reads:
                     session["selected_item"]    → "🛍️ Top listing found"
                     session["outfit_suggestion"] → "👗 Outfit idea"
                     session["fit_card"]          → "✨ Your fit card"
```

---

## AI Tool Plan

<!-- For each part of the implementation below, describe:
     - Which AI tool you plan to use (Claude, Copilot, ChatGPT, etc.)
     - What you'll give it as input (which sections of this planning.md, your agent diagram)
     - What you expect it to produce
     - How you'll verify the output matches your spec before moving on

     "I'll use AI to help me code" is not a plan.
     "I'll give Claude my Tool 1 spec (inputs, return value, failure mode) and ask it to implement
     search_listings() using load_listings() from the data loader — then test it against 3 queries
     before trusting it" is a plan. -->

**Milestone 3 — Individual tool implementations:**
For each tool I'll give Claude the Tool spec from this file (what it does, exact parameters, return value, failure mode) plus the relevant docstring from `tools.py` and the data shape from `data/listings.json` or `data/wardrobe_schema.json`. I'll ask it to implement only that one function, using `load_listings()` / `_get_groq_client()` already in the file. Verification: run `python tools.py` and manually check that `search_listings("vintage graphic tee", None, 30)` returns at least one item with `price ≤ 30`, that `suggest_outfit` returns a non-empty string for both the example and empty wardrobe, and that `create_fit_card` returns a string containing the item's title.

**Milestone 4 — Planning loop and state management:**
I'll give Claude the Planning Loop and State Management sections from this file plus the `_new_session()` dict structure from `agent.py`. I'll ask it to implement the body of `run_agent()` following the 7 numbered steps exactly, with the early-return guard after step 3. Verification: run `python agent.py` with the two CLI test queries — one should produce a full session dict with all five keys populated, and the no-match query ("designer ballgown") should return a session with only an `error` key set.

---

## A Complete Interaction (Step by Step)

FitFindr takes a plain-English query, uses the LLM to extract a structured description, size, and price ceiling, then calls `search_listings()` to find matching items — if nothing is found, it stops early and tells the user. When results exist, it picks the top match and calls `suggest_outfit()` with the user's wardrobe (falling back to general styling advice if the wardrobe is empty), then passes that suggestion into `create_fit_card()` to produce a shareable caption — if the outfit string is missing or empty, it skips the fit card and returns what it has.

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse query:**
The agent calls the LLM with the raw query. The LLM returns `{"description": "vintage graphic tee", "size": null, "max_price": 30.0}`. This is stored in `session["parsed"]`. Size is null because the user didn't specify one.

**Step 2 — Search listings:**
The agent calls `search_listings("vintage graphic tee", None, 30.0)`. The tool loads all 40 listings, drops items with `price > 30`, then scores each remaining item by counting how many of the words `{"vintage", "graphic", "tee"}` appear in its title + description + style_tags. Items with score 0 are removed. The result is a list sorted best-match first — e.g. `lst_006` ("Graphic Tee - 2003 Tour Bootleg", $24, style_tags: ["vintage", "grunge", "graphic"]) scores 3 and lands at index 0. Stored in `session["search_results"]`.

**Step 3 — Guard:**
`session["search_results"]` is not empty, so the agent continues without setting an error.

**Step 4 — Select item:**
`session["selected_item"] = session["search_results"][0]` — the Graphic Tee listing dict.

**Step 5 — Suggest outfit:**
The agent calls `suggest_outfit(selected_item, wardrobe)`. The wardrobe is the example wardrobe (10 items). The LLM sees the tee's style_tags (`vintage`, `grunge`, `graphic`) and wardrobe items including `w_001` (baggy straight-leg jeans), `w_008` (black combat boots), and `w_006` (vintage black denim jacket), and returns something like: "Outfit 1: Tuck the graphic tee into your baggy straight-leg jeans and lace up the black combat boots for a lived-in grunge look. Outfit 2: Layer the vintage denim jacket over the tee, pair with the dark-wash jeans and chunky white sneakers for a more relaxed 90s vibe." Stored in `session["outfit_suggestion"]`.

**Step 6 — Create fit card:**
The agent calls `create_fit_card(outfit_suggestion, selected_item)`. The LLM at temperature 0.9 generates a caption that names the tee, its $24 price, and Depop. For example: "You're giving full 2003 tour energy and we are here for it. Snag this vintage graphic tee for $24 on Depop before someone else does. Style it grunge with combat boots or keep it laid-back with baggy jeans and chunky sneakers — either way it's giving." Stored in `session["fit_card"]`.

**Step 7 — Return:**
The agent returns the complete session dict to `app.py`.

**Final output to user:**
- **🛍️ Top listing found:** "Graphic Tee - 2003 Tour Bootleg — $24 — Depop — Size M — Condition: good"
- **👗 Outfit idea:** the two-outfit string from step 5
- **✨ Your fit card:** the caption from step 6
