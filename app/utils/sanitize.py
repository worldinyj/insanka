import bleach

# Define allowed tags and attributes for sanitization (Supports Quill.js)
ALLOWED_TAGS = [
    "a", "abbr", "acronym", "b", "blockquote", "code", "em", "i", "li", "ol",
    "strong", "ul", "p", "br", "span", "div", "h1", "h2", "h3", "h4", "h5", "h6",
    "img", "u", "s", "pre"
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target"],
    "abbr": ["title"],
    "acronym": ["title"],
    "img": ["src", "alt", "width", "height", "class"],
    "span": ["class", "style"],
    "div": ["class", "style"],
}

ALLOWED_STYLES = [
    "color", "background-color", "text-align"
]

def sanitize_html(html_content: str) -> str:
    """
    Sanitize HTML content using bleach to prevent XSS.
    """
    if not html_content:
        return ""
    
    return bleach.clean(
        html_content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        styles=ALLOWED_STYLES,
        strip=True
    )
