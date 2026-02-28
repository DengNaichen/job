"""HTML to text conversion utilities."""

import html as html_module
import re

from bs4 import BeautifulSoup


def html_to_text(html: str) -> str:
    """Convert HTML to plain text using BeautifulSoup.

    Args:
        html: HTML string (may contain escaped entities like &lt;)

    Returns:
        Clean plain text with preserved structure
    """
    if not html:
        return ""

    # First, unescape HTML entities (like &lt; -> <)
    text = html_module.unescape(html)

    # Parse with BeautifulSoup
    soup = BeautifulSoup(text, "html.parser")

    # Remove script and style elements
    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    # Get text with line breaks preserved
    # Add newlines for block elements
    for tag in soup.find_all(["p", "div", "br", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr"]):
        if tag.name == "br":
            tag.replace_with("\n")
        else:
            tag.append("\n")

    # Get text
    text = soup.get_text(separator=" ")

    # Decode HTML entities again (in case there were nested)
    text = html_module.unescape(text)

    # Normalize whitespace but preserve paragraph breaks
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()
