"""Visualize source elements in the original filing HTML."""

import tempfile
import webbrowser
from typing import List


def highlight_html(html: str, element_ids: List[str]) -> str:
    """
    Return a copy of the annotated HTML with the specified elements
    highlighted and auto-scrolled to.

    Args:
        html: Annotated HTML from ``Parser.html()`` (contains
              ``data-sec2md-block`` attributes on source DOM nodes).
        element_ids: Element IDs to highlight (e.g. from ``chunk.element_ids``).

    Returns:
        Modified HTML string with highlight CSS and scroll JS injected.
    """
    if not element_ids:
        return html

    direct = ",\n".join(
        f'[data-sec2md-block="{eid}"]' for eid in element_ids
    )
    descendants = ",\n".join(
        f'[data-sec2md-block="{eid}"] *' for eid in element_ids
    )

    style_block = (
        '<style id="sec2md-highlight">\n'
        f"{direct},\n{descendants} {{\n"
        "  background-color: #FFFF00 !important;\n"
        "}\n"
        "</style>\n"
    )

    first_id = element_ids[0]
    script_block = (
        '<script id="sec2md-scroll">\n'
        "document.addEventListener('DOMContentLoaded', function() {\n"
        f'  var el = document.querySelector(\'[data-sec2md-block="{first_id}"]\');\n'
        "  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });\n"
        "});\n"
        "</script>\n"
    )

    # Inject style — prefer </head>, fallback to after <body>, else prepend
    lower = html.lower()
    head_end = lower.find("</head>")
    if head_end != -1:
        html = html[:head_end] + style_block + html[head_end:]
    else:
        body_start = lower.find("<body")
        if body_start != -1:
            end = html.index(">", body_start) + 1
            html = html[:end] + style_block + html[end:]
        else:
            html = style_block + html

    # Inject script before </body> or append
    lower = html.lower()
    body_end = lower.find("</body>")
    if body_end != -1:
        html = html[:body_end] + script_block + html[body_end:]
    else:
        html += script_block

    return html


def open_highlighted(html: str, element_ids: List[str]) -> str:
    """
    Write highlighted HTML to a temporary file and open it in the browser.

    Args:
        html: Annotated HTML from ``Parser.html()``.
        element_ids: Element IDs to highlight.

    Returns:
        Path to the temporary HTML file.
    """
    highlighted = highlight_html(html, element_ids)

    tmp = tempfile.NamedTemporaryFile(
        "w", suffix=".html", prefix="sec2md_", delete=False, encoding="utf-8"
    )
    tmp.write(highlighted)
    tmp.close()

    webbrowser.open(f"file://{tmp.name}")
    return tmp.name
