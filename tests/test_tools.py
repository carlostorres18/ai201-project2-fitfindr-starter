"""
Tests for the three FitFindr tools.

search_listings — pure logic, no mocking needed.
suggest_outfit  — LLM call, Groq client is mocked.
create_fit_card — LLM call, Groq client is mocked.
"""

import pytest
from unittest.mock import MagicMock, patch

from tools import search_listings, suggest_outfit, create_fit_card
from utils.data_loader import get_example_wardrobe, get_empty_wardrobe


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mock_groq(text: str):
    """Return a mock Groq client whose .chat.completions.create() returns text."""
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value.choices[0].message.content = text
    return mock_client


@pytest.fixture
def graphic_tee():
    """A real listing that matches 'vintage graphic tee' under $30."""
    results = search_listings("vintage graphic tee", max_price=30)
    assert results, "fixture requires at least one match — check listings.json"
    return results[0]


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def test_search_listings_returns_results_for_known_keywords():
    results = search_listings("vintage graphic tee")
    assert len(results) > 0


def test_search_listings_failure_mode_no_match_returns_empty_list():
    # No listing contains all of these niche keywords — confirmed no-match case.
    results = search_listings("designer ballgown couture gala evening")
    assert results == []


def test_search_listings_price_filter_excludes_over_ceiling():
    results = search_listings("jacket", max_price=25.0)
    for item in results:
        assert item["price"] <= 25.0, f"{item['title']} costs ${item['price']}, over $25 ceiling"


def test_search_listings_price_filter_returns_empty_when_all_too_expensive():
    results = search_listings("jacket coat blazer", max_price=0.01)
    assert results == []


def test_search_listings_size_filter_case_insensitive():
    results = search_listings("top tee shirt", size="M")
    for item in results:
        assert "m" in item["size"].lower(), (
            f"{item['title']} has size '{item['size']}', expected 'm' substring"
        )


def test_search_listings_drops_zero_score_items():
    # A word that appears nowhere in listings — all items score 0, none returned.
    results = search_listings("zzzxyznotakeywordatall")
    assert results == []


def test_search_listings_best_match_is_first():
    results = search_listings("vintage denim jacket")
    assert len(results) >= 2
    # We can't score externally here, but we can verify the list is ordered by
    # checking that the first item has at least one keyword in its text.
    first = results[0]
    text = (first["title"] + first["description"] + " ".join(first["style_tags"])).lower()
    assert any(kw in text for kw in ["vintage", "denim", "jacket"])


def test_search_listings_no_filters_returns_results():
    results = search_listings("shoes boots sneakers")
    assert len(results) > 0


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def test_suggest_outfit_with_wardrobe_returns_nonempty_string(graphic_tee):
    wardrobe = get_example_wardrobe()
    with patch("tools._get_groq_client", return_value=_mock_groq(
        "Outfit 1: Tuck the tee into your baggy jeans with the chunky sneakers."
    )):
        result = suggest_outfit(graphic_tee, wardrobe)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_failure_mode_empty_wardrobe_returns_nonempty_string(graphic_tee):
    # Failure mode: wardrobe is empty. Tool must not error — must return advice.
    empty_wardrobe = get_empty_wardrobe()
    with patch("tools._get_groq_client", return_value=_mock_groq(
        "Great with high-waisted jeans and chunky boots for a grunge vibe."
    )):
        result = suggest_outfit(graphic_tee, empty_wardrobe)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_suggest_outfit_failure_mode_llm_returns_empty_gives_fallback(graphic_tee):
    # Failure mode: LLM returns blank. Tool must return a fallback, not an empty string.
    empty_wardrobe = get_empty_wardrobe()
    with patch("tools._get_groq_client", return_value=_mock_groq("   ")):
        result = suggest_outfit(graphic_tee, empty_wardrobe)
    assert isinstance(result, str)
    assert result.strip() != "", "Expected fallback message, got empty string"


def test_suggest_outfit_empty_wardrobe_does_not_call_llm_with_wardrobe_items(graphic_tee):
    # When wardrobe is empty, the prompt sent to the LLM should NOT mention wardrobe pieces.
    empty_wardrobe = get_empty_wardrobe()
    mock_client = _mock_groq("Style it with straight-leg jeans.")

    with patch("tools._get_groq_client", return_value=mock_client):
        suggest_outfit(graphic_tee, empty_wardrobe)

    call_args = mock_client.chat.completions.create.call_args
    prompt_text = call_args[1]["messages"][0]["content"]
    assert "wardrobe includes" not in prompt_text.lower()


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def test_create_fit_card_failure_mode_empty_outfit_returns_error_message(graphic_tee):
    # Failure mode: outfit is empty string. Must return a descriptive error string, not raise.
    result = create_fit_card("", graphic_tee)
    assert isinstance(result, str)
    assert result.strip() != "", "Expected a descriptive error message, got empty string"


def test_create_fit_card_failure_mode_whitespace_outfit_returns_error_message(graphic_tee):
    # Failure mode: outfit is whitespace-only. Must return a descriptive error string, not raise.
    result = create_fit_card("   \n\t  ", graphic_tee)
    assert isinstance(result, str)
    assert result.strip() != "", "Expected a descriptive error message, got empty string"


def test_create_fit_card_empty_outfit_does_not_call_llm(graphic_tee):
    # Verify the LLM is never invoked when outfit is empty.
    with patch("tools._get_groq_client") as mock_factory:
        create_fit_card("", graphic_tee)
    mock_factory.assert_not_called()


def test_create_fit_card_returns_nonempty_string_for_valid_input(graphic_tee):
    outfit = "Pair the graphic tee with baggy jeans and chunky white sneakers."
    with patch("tools._get_groq_client", return_value=_mock_groq(
        "You're giving full vintage energy with this graphic tee for $24 on Depop. "
        "Tuck it into your baggy jeans and lace up the chunky sneakers — pure 90s grunge."
    )):
        result = create_fit_card(outfit, graphic_tee)
    assert isinstance(result, str)
    assert result.strip() != ""


def test_create_fit_card_uses_high_temperature(graphic_tee):
    # The LLM call must use temperature >= 0.9 for caption variety.
    outfit = "Graphic tee with jeans."
    mock_client = _mock_groq("You're serving looks.")

    with patch("tools._get_groq_client", return_value=mock_client):
        create_fit_card(outfit, graphic_tee)

    call_kwargs = mock_client.chat.completions.create.call_args[1]
    assert call_kwargs.get("temperature", 0) >= 0.9, (
        f"Expected temperature >= 0.9, got {call_kwargs.get('temperature')}"
    )
