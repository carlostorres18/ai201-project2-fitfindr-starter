"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()

    if max_price is not None:
        listings = [l for l in listings if l["price"] <= max_price]

    if size is not None:
        listings = [l for l in listings if size.lower() in l["size"].lower()]

    keywords = set(description.lower().split())

    def _score(listing):
        text = " ".join([
            listing["title"],
            listing["description"],
            " ".join(listing["style_tags"]),
        ]).lower()
        return sum(1 for kw in keywords if kw in text)

    scored = [(_score(l), l) for l in listings]
    scored = [(s, l) for s, l in scored if s > 0]
    scored.sort(key=lambda x: x[0], reverse=True)

    return [l for _, l in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    client = _get_groq_client()

    item_summary = (
        f"Name: {new_item['title']}\n"
        f"Description: {new_item['description']}\n"
        f"Style tags: {', '.join(new_item['style_tags'])}\n"
        f"Colors: {', '.join(new_item['colors'])}\n"
        f"Category: {new_item['category']}"
    )

    if not wardrobe.get("items"):
        prompt = (
            "You are a personal stylist. A user is considering buying this secondhand item:\n"
            f"{item_summary}\n\n"
            "They have an empty wardrobe. Give them 1–2 specific outfit ideas, including "
            "what types of pieces would pair well and what overall vibe to go for. "
            "Be concrete — name garment types, colors, and footwear."
        )
    else:
        wardrobe_lines = "\n".join(
            f"- {item['name']} ({item['category']}, "
            f"colors: {', '.join(item['colors'])}, "
            f"tags: {', '.join(item['style_tags'])})"
            for item in wardrobe["items"]
        )
        prompt = (
            "You are a personal stylist. A user is considering buying this secondhand item:\n"
            f"{item_summary}\n\n"
            "Their current wardrobe includes:\n"
            f"{wardrobe_lines}\n\n"
            "Suggest 1–2 complete outfits that pair the new item with specific named pieces "
            "from their wardrobe. Call out each wardrobe piece by name."
        )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
    )
    result = response.choices[0].message.content.strip()

    if not result:
        return "Style this item your way — it pairs well with both casual and dressed-up looks."

    return result


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string
        — does NOT raise an exception.

    The caption should:
    - Feel casual and authentic (like a real OOTD post, not a product description)
    - Mention the item name, price, and platform naturally (once each)
    - Capture the outfit vibe in specific terms
    - Sound different each time for different inputs (use higher LLM temperature)
    """
    if not outfit or not outfit.strip():
        return "No outfit suggestion was provided, so a fit card could not be generated."

    client = _get_groq_client()

    prompt = (
        f"Write a 2–4 sentence Instagram/TikTok caption for this thrifted outfit.\n\n"
        f"New item: {new_item['title']} — ${new_item['price']} on {new_item['platform']}\n"
        f"Style tags: {', '.join(new_item['style_tags'])}\n\n"
        f"Outfit description:\n{outfit}\n\n"
        "Rules:\n"
        "- Write in second-person present tense (\"You're giving…\", \"Pair it with…\")\n"
        f"- Mention the item name ({new_item['title']}), price (${new_item['price']}), "
        f"and platform ({new_item['platform']}) each exactly once\n"
        "- Capture the vibe in specific terms (e.g. \"soft grunge\", \"quiet luxury\", \"y2k nostalgia\")\n"
        "- Sound like an influencer caption, not a product description\n"
        "- 2–4 sentences only, no hashtags"
    )

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.9,
    )
    return response.choices[0].message.content.strip()


# ── Manual smoke test ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Tool 1: search_listings ===")
    results = search_listings("vintage graphic tee", max_price=30)
    print(f"Found {len(results)} results")
    if results:
        top = results[0]
        print(f"Top match: {top['title']} — ${top['price']} — {top['platform']}")

    print("\n=== Tool 1: no-match case ===")
    no_results = search_listings("designer ballgown couture gala")
    print(f"Results: {no_results}")  # should be []

    if results:
        print("\n=== Tool 2: suggest_outfit (example wardrobe) ===")
        suggestion = suggest_outfit(results[0], get_example_wardrobe())
        print(suggestion)

        print("\n=== Tool 2: suggest_outfit (empty wardrobe) ===")
        suggestion_empty = suggest_outfit(results[0], get_empty_wardrobe())
        print(suggestion_empty)

        print("\n=== Tool 3: create_fit_card ===")
        card = create_fit_card(suggestion, results[0])
        print(card)

        print("\n=== Tool 3: empty outfit guard ===")
        card_empty = create_fit_card("", results[0])
        print(f"Empty outfit result: '{card_empty}'")  # should be ""
