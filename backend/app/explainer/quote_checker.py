import re
import unicodedata

def normalize_text(text: str) -> str:
    """Normalizes text for robust character matching across PDF line breaks and unicode variants."""
    if not text:
        return ""
    # Normalize unicode (NFKC)
    t = unicodedata.normalize("NFKC", text)
    # Collapse multiple whitespace characters, tabs, newlines into single spaces
    t = re.sub(r"\s+", " ", t).strip()
    return t.lower()


def verify_quote(quote: str, document_text: str) -> bool:
    """Verifies that a quote cited by the model actually exists verbatim in the document."""
    if not quote or not document_text:
        return False
    norm_doc = normalize_text(document_text)
    norm_quote = normalize_text(quote)
    if not norm_quote:
        return False
    # If quote is very short (under 4 chars) it is not a meaningful quote
    if len(norm_quote) < 4:
        return False
    return norm_quote in norm_doc
