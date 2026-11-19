"""Build the deployable zerostart.org site from page.html.

page.html is the single source. Everything above the ``<!-- BODY -->`` marker
goes into <head>; everything below goes into <body>. Output lands in public/,
which is the folder to deploy to Cloudflare Pages.

Usage: python3 build.py
"""

from pathlib import Path

SITE_URL = "https://zerostart.org/"
SEO_TITLE = "ZeroStart | Websites and Local Search for Businesses Worldwide"
DESCRIPTION = (
    "ZeroStart builds websites, listings and local search presence for "
    "businesses anywhere in the world. See a working preview of your site first."
)
MARKER = "<!-- BODY -->"

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "public"


def _head_extras() -> str:
    """Return SEO tags for the real site's <head>."""
    return f"""<link rel="canonical" href="{SITE_URL}">
<meta property="og:type" content="website">
<meta property="og:url" content="{SITE_URL}">
<meta property="og:title" content="{SEO_TITLE}">
<meta property="og:description" content="{DESCRIPTION}">
<meta name="twitter:card" content="summary">
<script type="application/ld+json">
{{"@context":"https://schema.org","@type":"Organization","name":"ZeroStart",
"url":"{SITE_URL}","description":"{DESCRIPTION}","areaServed":"Worldwide"}}
</script>"""


def build_index(source: str) -> str:
    """Wrap page.html content in a full HTML document.

    Args:
        source: Text of page.html, containing the BODY marker.

    Returns:
        A complete HTML document string.

    Raises:
        ValueError: If the BODY marker is missing.
    """
    if MARKER not in source:
        raise ValueError(f"page.html is missing the {MARKER} marker")
    head, body = source.split(MARKER, 1)
    head = head.replace("<title>ZeroStart</title>", f"<title>{SEO_TITLE}</title>", 1)
    head = head.replace('<meta name="claude:viewport-fit-sides" content="cover">\n', "", 1)
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1, '
        'viewport-fit=cover">\n'
        f"{head.strip()}\n{_head_extras()}\n</head>\n<body>\n{body.strip()}\n"
        "</body>\n</html>\n"
    )


def main() -> None:
    """Write public/index.html, robots.txt and sitemap.xml."""
    OUT.mkdir(exist_ok=True)
    source = (ROOT / "page.html").read_text(encoding="utf-8")
    (OUT / "index.html").write_text(build_index(source), encoding="utf-8")
    (OUT / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}sitemap.xml\n", encoding="utf-8"
    )
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"  <url><loc>{SITE_URL}</loc></url>\n</urlset>\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
