AUTHOR = "Adrian Sampson"

# General configuration

extensions = ["sphinx.ext.autodoc", "sphinx.ext.extlinks"]

exclude_patterns = ["_build"]
source_suffix = {".rst": "restructuredtext"}
master_doc = "index"

project = "beets"
copyright = "2016, Adrian Sampson"

version = "2.2"
release = "2.2.0"

pygments_style = "sphinx"

# External links to the bug tracker and other sites.
extlinks = {
    "bug": ("https://github.com/beetbox/beets/issues/%s", "#%s"),
    "user": ("https://github.com/%s", "%s"),
    "pypi": ("https://pypi.org/project/%s/", "%s"),
    "stdlib": ("https://docs.python.org/3/library/%s.html", "%s"),
}

linkcheck_ignore = [
    r"https://github.com/beetbox/beets/issues/",
    r"https://github.com/[^/]+$",  # ignore user pages
    r".*localhost.*",
    r"https?://127\.0\.0\.1",
    r"https://www.musixmatch.com/",  # blocks requests
    r"https://genius.com/",  # blocks requests
]

# Options for HTML output
htmlhelp_basename = "beetsdoc"

# Options for LaTeX output
latex_documents = [
    ("index", "beets.tex", "beets Documentation", AUTHOR, "manual"),
]

# Options for manual page output
man_pages = [
    (
        "reference/cli",
        "beet",
        "music tagger and library organizer",
        [AUTHOR],
        1,
    ),
    (
        "reference/config",
        "beetsconfig",
        "beets configuration file",
        [AUTHOR],
        5,
    ),
]

# Options for pydata theme
html_theme = "pydata_sphinx_theme"
html_theme_options = {"collapse_navigation": True, "logo": {"text": "beets"}}
html_title = "beets"
html_logo = "_static/beets_logo_nobg.png"
html_static_path = ["_static"]
html_css_files = ["beets.css"]
