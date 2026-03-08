"""
Cost Parser — extracts structured cost info from freeform text.

Converts strings like "Free", "$5", "$10/child", "No charge" into
(cost_text, cost_cents) tuples for database storage.
"""
import re
import logging

log = logging.getLogger("cost_parser")

# Patterns that mean "free"
FREE_PATTERNS = re.compile(
    r"^(free|no\s+charge|no\s+cost|complimentary|gratis|\$0(\.00)?|0\.00)$",
    re.IGNORECASE,
)

# Extract a dollar amount: $5, $5.00, $10/child, $25 per person
RE_DOLLAR = re.compile(r"\$(\d+(?:\.\d{1,2})?)")

# "varies", "sliding scale", "donation" — cost exists but isn't fixed
VARIES_PATTERNS = re.compile(
    r"(varies|sliding\s+scale|donation|pay\s+what|suggested)",
    re.IGNORECASE,
)


def parse_cost(text: str) -> tuple:
    """
    Parse a cost string into (cost_text, cost_cents).

    Returns:
        (cost_text, cost_cents) where:
        - cost_text: cleaned display string ("Free", "$5", "$10/child")
        - cost_cents: integer cents (0=free, 500=$5.00, None=unknown/varies)
    """
    if not text or not text.strip():
        return None, None

    text = text.strip()

    # Check for "free"
    if FREE_PATTERNS.match(text):
        return "Free", 0

    # Check for dollar amount
    dollar_match = RE_DOLLAR.search(text)
    if dollar_match:
        amount = float(dollar_match.group(1))
        cents = int(round(amount * 100))
        if cents == 0:
            return "Free", 0
        return text, cents

    # Check for "varies" / "donation" type
    if VARIES_PATTERNS.search(text):
        return text, None

    # If the text is just "Free" with extra words around it
    if re.search(r"\bfree\b", text, re.IGNORECASE):
        return "Free", 0

    # Unrecognized — return text as-is, cents unknown
    return text, None


def cost_from_tags(tags: str) -> tuple:
    """
    Extract cost info from Gemini-assigned tags.

    If the tagger included "Free" as a tag, we can infer cost_cents=0.
    """
    if not tags:
        return None, None

    tag_list = [t.strip() for t in tags.split(",")]
    if "Free" in tag_list:
        return "Free", 0

    return None, None
