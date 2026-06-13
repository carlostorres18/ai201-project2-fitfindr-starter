# FitFindr

A 3-layer AI agent that takes a natural language clothing query, searches a mock secondhand listings dataset, and returns a matching item, an outfit suggestion paired with the user's wardrobe, and a shareable fit card caption — all powered by Groq.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # add your GROQ_API_KEY (free at console.groq.com)
```

## Running the app

```bash
python app.py          # Gradio UI at http://localhost:7860
python agent.py        # CLI test of both happy and no-results paths
python tools.py        # smoke test of all three tools
```

## Running tests

```bash
pytest                          # all 17 tests
pytest tests/test_tools.py -v   # verbose, one line per test
pytest -k "failure_mode"        # only failure-mode tests
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

**Purpose:** Find listings that match the user's query without calling an LLM.

| Parameter | Type | Meaning |
|---|---|---|
| `description` | `str` | Keywords from the user's query (e.g. `"vintage graphic tee"`) |
| `size` | `str \| None` | Size to filter by; case-insensitive substring match against the listing's `size` field (`"M"` matches `"S/M"`); `None` skips filter |
| `max_price` | `float \| None` | Upper price ceiling in dollars, inclusive; `None` skips filter |

**Output:** `list[dict]` — listing dicts sorted by keyword-match score descending, zero-score items removed. Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str or None), `platform`. Returns `[]` if nothing passes all filters or every survivor scores zero.

---

### `suggest_outfit(new_item, wardrobe)`

**Purpose:** Use the Groq LLM to pair the new thrifted item with pieces from the user's wardrobe, or give general styling advice if the wardrobe is empty.

| Parameter | Type | Meaning |
|---|---|---|
| `new_item` | `dict` | A listing dict (the top result from `search_listings`) |
| `wardrobe` | `dict` | A wardrobe dict with an `"items"` key; each item has `name`, `category`, `colors`, `style_tags`, optional `notes`; may be empty |

**Output:** `str` — 1–2 complete outfit descriptions naming specific wardrobe pieces, or general styling guidance when wardrobe is empty. Always non-empty (falls back to a hardcoded message if the LLM returns blank).

---

### `create_fit_card(outfit, new_item)`

**Purpose:** Use the Groq LLM at high temperature to generate a 2–4 sentence Instagram/TikTok caption for the thrifted outfit.

| Parameter | Type | Meaning |
|---|---|---|
| `outfit` | `str` | The outfit suggestion string from `suggest_outfit` |
| `new_item` | `dict` | The listing dict; used to pull `title`, `price`, and `platform` into the caption |

**Output:** `str` — a second-person caption that mentions the item name, price, and platform once each and captures the outfit vibe in specific terms (e.g. "soft grunge", "y2k nostalgia"). Returns a descriptive error message string — not an empty string and not an exception — if `outfit` is empty or whitespace-only.

---

## Planning Loop

The loop always runs the same fixed sequence of 7 steps. It is not dynamic — it does not decide which tool to call based on intermediate results. The only branching is a single early-exit guard after the search step.

```
Step 1  _new_session()              initialize session dict
Step 2  LLM (temp=0.0)             parse query → {description, size, max_price}
Step 3  search_listings()          search dataset with parsed params
        ↓ if empty list:
        set session["error"], return immediately — steps 4–7 skipped
Step 4  search_results[0]          select top item, no LLM
Step 5  suggest_outfit()           pair item with wardrobe
Step 6  create_fit_card()          generate caption
Step 7  return session
```

I chose to parse the query with the LLM (step 2) rather than using regex because natural language queries vary too much in structure — "vintage graphic tee under $30" and "I'm looking for something y2k, size small, nothing over $25" have the same three parameters but no consistent pattern to extract them with string splitting. The parse prompt uses `temperature=0.0` so results are deterministic; a `re.search` strips code fences if the model wraps the JSON in a markdown block.

---

## State Management

`run_agent()` initializes one session dict at the top of the call and mutates it in-place through each step. Nothing is passed as a function return value to the next step — each step reads from and writes to the shared dict.

```python
session = {
    "query":             str,    # never modified after init
    "parsed":            dict,   # written step 2, read step 3
    "search_results":    list,   # written step 3, read steps 3-guard and 4
    "selected_item":     dict,   # written step 4, read steps 5 and 6
    "wardrobe":          dict,   # set at init from argument, never modified
    "outfit_suggestion": str,    # written step 5, read step 6
    "fit_card":          str,    # written step 6
    "error":             str,    # set only on early exit; None on success
}
```

`app.py` checks `session["error"]` first. On error it returns the message in panel 1 and empty strings for panels 2 and 3. On success it formats `session["selected_item"]` into a readable listing block and passes `session["outfit_suggestion"]` and `session["fit_card"]` directly to their panels.

---

## Error Handling

### `search_listings` — no results

If the filtered, scored list is empty, `run_agent()` sets:
```python
session["error"] = "No listings matched your search. Try different keywords, a higher price, or leave size blank."
```
and returns immediately. `suggest_outfit` and `create_fit_card` are never called — confirmed with `mock.assert_not_called()` in testing.

**Concrete example from testing:** the query `"designer ballgown size XXS under $5"` — the price ceiling ($5) eliminates all 41 listings before scoring, so the list is empty and the error message appears in panel 1 with panels 2 and 3 blank.

---

### `suggest_outfit` — empty wardrobe

When `wardrobe["items"]` is an empty list, the tool sends a different prompt to the LLM: instead of asking it to pair the item with named wardrobe pieces, it asks for general styling advice (garment types, colors, footwear) based on the item's category, colors, and style tags. Execution continues normally — this is not treated as an error.

If the LLM returns an empty or whitespace-only string for any reason, the tool returns a hardcoded fallback: `"Style this item your way — it pairs well with both casual and dressed-up looks."`

**Concrete example from testing:** calling `suggest_outfit` with `get_empty_wardrobe()` (which has `"items": []`) returns a non-empty styling suggestion every time. The prompt sent to the LLM never includes the phrase "wardrobe includes" — verified by inspecting `mock_client.chat.completions.create.call_args` in the test suite.

---

### `create_fit_card` — empty outfit string

If `outfit` is an empty or whitespace-only string, the tool skips the LLM call entirely and returns:
```
"No outfit suggestion was provided, so a fit card could not be generated."
```
The Groq client is never initialized in this path — confirmed by `mock_factory.assert_not_called()` in the test.

**Concrete example from testing:**
```python
>>> from tools import search_listings, create_fit_card
>>> results = search_listings('vintage graphic tee', size=None, max_price=50)
>>> create_fit_card('', results[0])
'No outfit suggestion was provided, so a fit card could not be generated.'
```

---

## Spec Reflection

**What matched:** The 7-step loop and session dict structure from `planning.md` mapped directly to code with almost no changes. The state management section made it easy to see which keys needed to be written before each step read them, which caught one ordering mistake early (I had step 4 reading `search_results` before confirming it was non-empty).

**What I changed:** `planning.md` said `create_fit_card` should set `session["fit_card"] = ""` on empty input and let `app.py` hide the panel. During testing I noticed that an empty string in a Gradio `Textbox` looks broken rather than intentionally absent, so I changed the tool to return a descriptive error message string instead. The tests were updated to assert `result.strip() != ""` rather than `result == ""`.

**What the spec missed:** The dataset only had 4 shoe listings and none were combat boots, but "black combat boots size 8" was included as a UI example query. The spec described error handling for no-results but didn't flag that the example queries needed to be validated against the dataset. I added `lst_041` (Black Combat Boots — Lace-Up, US 8, $45, Depop) to `listings.json` to fix this. In a real project, the data spec and the UI examples would need to be kept in sync.

---

## AI Usage

### Instance 1 — Implementing `search_listings`

**What I gave Claude:** The Tool 1 section of `planning.md` (what it does, exact parameters with types, return value field list, failure mode), the `search_listings` docstring already in `tools.py`, and the first listing from `data/listings.json` as a format example.

**What it produced:** A working implementation that loaded listings, filtered by price and size, scored by keyword overlap, and sorted descending. The structure matched the spec exactly.

**What I changed:** Claude's initial scoring function used `word in listing["title"].lower()` — it only checked the title, not `description` or `style_tags`. The spec said to score against all three fields. I told Claude to fix this and it updated `_score()` to join `title`, `description`, and `style_tags` into a single string before counting keyword matches. I verified the fix by running `search_listings("grunge")` and confirming items tagged `["grunge"]` but with neutral titles still appeared in results.

### Instance 2 — Implementing the planning loop in `run_agent()`

**What I gave Claude:** The Planning Loop section from `planning.md` (the 7 numbered steps with explicit branching), the State Management section (the exact key-to-step mapping table), the `_new_session()` dict already in `agent.py`, and the existing tool signatures from `tools.py`.

**What it produced:** A complete `run_agent()` implementation that followed the 7 steps, initialized the session, parsed the query with the LLM, called the three tools in order, and returned early with `session["error"]` on empty search results.

**What I changed:** Claude used `json.loads(raw)` directly on the LLM's parse response, which threw a `JSONDecodeError` when the model added a markdown code fence around the JSON. I added `re.search(r"\{.*\}", raw, re.DOTALL)` to extract the JSON object before parsing, with a fallback that uses the raw query as the description if no JSON is found at all. I also added `temperature=0.0` to the parse call — Claude defaulted to `0.7`, but deterministic parsing is important here since a randomly rephrased description would produce inconsistent search results for the same user query.
