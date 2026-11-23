"""The landing site: Jinja templates served by Flask while you work, built to self-contained static pages to publish.

    uv run --project site flask --app site/app.py run --debug   # http://127.0.0.1:5000
    uv run --project site python site/app.py build              # writes site/dist/

Every page extends `templates/base.html`, so the header, nav, and footer are written once. A build inlines each page's
CSS and JavaScript from `static/`, so every file in `dist/` stands alone. The version comes from the repo's
`pyproject.toml`; the pages also ask PyPI for the latest release when they load.
"""

import json
import shutil
import sys
import tomllib
from pathlib import Path

from flask import Flask, abort, render_template
from markupsafe import Markup

HERE = Path(__file__).parent
DIST = HERE / "dist"

#: Pages, by output file name.
PAGES = ["index.html", "what-is-a-fact.html"]
#: The header nav, on every page. A link starting with "#" is a section of the home page.
NAV = [
    ("#overview", "Overview"),
    ("#pipeline", "Pipeline"),
    ("#access-paths", "Access Paths"),
    ("#lifecycle", "Lifecycle"),
    ("#benchmarks", "Evaluation"),
    ("#papers", "Papers"),
    ("what-is-a-fact.html", "What is a fact?"),
]
FOOTER = [
    ("https://github.com/Endgame-Labs/factoid", "GitHub Repository"),
    ("https://pypi.org/project/factoid/", "PyPI Package"),
    ("https://github.com/Endgame-Labs/factoid/blob/main/CHANGELOG.md", "Changelog"),
    ("https://github.com/Endgame-Labs/factoid/blob/main/SPEC.md", "SPEC.md"),
    ("https://github.com/Endgame-Labs/factoid/blob/main/LICENSE", "MIT License"),
    ("https://arxiv.org/abs/2608.20845", "arXiv:2608.20845"),
    ("https://arxiv.org/abs/2609.29661", "arXiv:2609.29661"),
]

app = Flask(__name__, static_folder=None)


def version() -> str:
    return tomllib.loads((HERE.parent / "pyproject.toml").read_text())["project"]["version"]


def asset(name: str) -> Markup:
    """A file from `static/`, inlined into the page."""
    return Markup((HERE / "static" / name).read_text())


def render(page: str) -> str:
    def link(href: str) -> str:
        # On the home page a section link stays in the page; elsewhere it goes to the home page's section.
        if href.startswith("#"):
            return href if page == "index.html" else "index.html" + href
        return href

    return render_template(page, page=page, nav=NAV, footer=FOOTER, link=link, asset=asset, version=version(),
                           demo=json.loads((HERE / "data" / "demo.json").read_text()))


@app.route("/")
@app.route("/<page>")
def serve(page: str = "index.html") -> str:
    if page not in PAGES:
        abort(404)
    return render(page)


def build() -> None:
    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir()
    with app.app_context():
        for page in PAGES:
            (DIST / page).write_text(render(page))
            print(f"wrote {(DIST / page).relative_to(HERE.parent)}")


if __name__ == "__main__":
    if sys.argv[1:] == ["build"]:
        build()
    else:
        sys.exit(__doc__)
