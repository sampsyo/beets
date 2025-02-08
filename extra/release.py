#!/usr/bin/env python3

"""A utility script for automating the beets release process."""

from __future__ import annotations

import re
import subprocess
from contextlib import redirect_stdout
from datetime import datetime, timezone
from functools import partial
from io import StringIO
from pathlib import Path
from typing import Callable, NamedTuple

import click
import tomli
from packaging.version import Version, parse
from sphinx.ext import intersphinx
from typing_extensions import TypeAlias

BASE = Path(__file__).parent.parent.absolute()
PYPROJECT = BASE / "pyproject.toml"
CHANGELOG = BASE / "docs" / "changelog.rst"
DOCS = "https://beets.readthedocs.io/en/stable"

VERSION_HEADER = r"\d+\.\d+\.\d+ \([^)]+\)"
RST_LATEST_CHANGES = re.compile(
    rf"{VERSION_HEADER}\n--+\s+(.+?)\n\n+{VERSION_HEADER}", re.DOTALL
)

Replacement: TypeAlias = "tuple[str, str | Callable[[re.Match[str]], str]]"


class Ref(NamedTuple):
    """A reference to documentation with ID, path, and optional title."""

    id: str
    path: str | None
    title: str | None

    @classmethod
    def from_line(cls, line: str) -> Ref:
        """Create Ref from a Sphinx objects.inv line.

        Each line has the following structure:
        <id>    [optional title : ] <relative-url-path>

        See the output of
            python -m sphinx.ext.intersphinx docs/_build/html/objects.inv
        """
        if len(line_parts := line.split(" ", 1)) == 1:
            return cls(line, None, None)

        id, path_with_name = line_parts
        parts = [p.strip() for p in path_with_name.split(":", 1)]

        if len(parts) == 1:
            path, name = parts[0], None
        else:
            name, path = parts

        return cls(id, path, name)

    @property
    def url(self) -> str:
        """Full documentation URL."""
        return f"{DOCS}/{self.path}"

    @property
    def name(self) -> str:
        """Display name (title if available, otherwise ID)."""
        return self.title or self.id


def get_refs() -> dict[str, Ref]:
    """Parse Sphinx objects.inv and return dict of documentation references."""
    objects_filepath = Path("docs/_build/html/objects.inv")
    if not objects_filepath.exists():
        raise ValueError("Documentation does not exist. Run 'poe docs' first.")

    captured_output = StringIO()

    with redirect_stdout(captured_output):
        intersphinx.inspect_main([str(objects_filepath)])

    lines = captured_output.getvalue().replace("\t", "    ").splitlines()
    return {
        r.id: r
        for ln in lines
        if ln.startswith("    ") and (r := Ref.from_line(ln.strip()))
    }


def create_rst_replacements() -> list[Replacement]:
    """Generate list of pattern replacements for RST changelog."""
    refs = get_refs()

    def make_ref_link(ref_id: str, name: str | None = None) -> str:
        ref = refs[ref_id]
        return rf"`{name or ref.name} <{ref.url}>`_"

    commands = "|".join(r.split("-")[0] for r in refs if r.endswith("-cmd"))
    plugins = "|".join(
        r.split("/")[-1] for r in refs if r.startswith("plugins/")
    )
    return [
        # Fix nested bullet points indent: use 2 spaces consistently
        (r"(?<=\n) {3,4}(?=\*)", "  "),
        # Fix nested text indent: use 4 spaces consistently
        (r"(?<=\n) {5,6}(?=[\w:`])", "    "),
        # Replace Sphinx :ref: and :doc: directives by documentation URLs
        #   :ref:`/plugins/autobpm` -> [AutoBPM Plugin](DOCS/plugins/autobpm.html)
        (
            r":(?:ref|doc):`+(?:([^`<]+)<)?/?([\w./_-]+)>?`+",
            lambda m: make_ref_link(m[2], m[1]),
        ),
        # Convert command references to documentation URLs
        #   `beet move` or `move` command -> [import](DOCS/reference/cli.html#import)
        (
            rf"`+beet ({commands})`+|`+({commands})`+(?= command)",
            lambda m: make_ref_link(f"{m[1] or m[2]}-cmd"),
        ),
        # Convert plugin references to documentation URLs
        #   `fetchart` plugin -> [fetchart](DOCS/plugins/fetchart.html)
        (rf"`+({plugins})`+", lambda m: make_ref_link(f"plugins/{m[1]}")),
        # Add additional backticks around existing backticked text to ensure it
        # is rendered as inline code in Markdown
        (r"(?<=[\s])(`[^`]+`)(?!_)", r"`\1`"),
        # Convert bug references to GitHub issue links
        (r":bug:`(\d+)`", r":bug: (#\1)"),
        # Convert user references to GitHub @mentions
        (r":user:`(\w+)`", r"\@\1"),
    ]


MD_REPLACEMENTS: list[Replacement] = [
    (r"<span[^>]+>([^<]+)</span>", r"_\1"),  # remove a couple of wild span refs
    (r"^(\w[^\n]{,80}):(?=\n\n[^ ])", r"### \1"),  # format section headers
    (r"^(\w[^\n]{81,}):(?=\n\n[^ ])", r"**\1**"),  # and bolden too long ones
    (r"### [^\n]+\n+(?=### )", ""),  # remove empty sections
]
order_bullet_points = partial(
    re.compile("(\n- .*?(?=\n(?! *- )|$))", flags=re.DOTALL).sub,
    lambda m: "\n- ".join(sorted(m.group().split("\n- "))),
)


def update_docs_config(text: str, new: Version) -> str:
    new_major_minor = f"{new.major}.{new.minor}"
    text = re.sub(r"(?<=version = )[^\n]+", f'"{new_major_minor}"', text)
    return re.sub(r"(?<=release = )[^\n]+", f'"{new}"', text)


def update_changelog(text: str, new: Version) -> str:
    new_header = f"{new} ({datetime.now(timezone.utc).date():%B %d, %Y})"
    return re.sub(
        # do not match if the new version is already present
        r"\nUnreleased\n--+\n",
        rf"""
Unreleased
----------

New features:

Bug fixes:

For packagers:

Other changes:

{new_header}
{'-' * len(new_header)}
""",
        text,
    )


UpdateVersionCallable = Callable[[str, Version], str]
FILENAME_AND_UPDATE_TEXT: list[tuple[Path, UpdateVersionCallable]] = [
    (
        PYPROJECT,
        lambda text, new: re.sub(r"(?<=\nversion = )[^\n]+", f'"{new}"', text),
    ),
    (
        BASE / "beets" / "__init__.py",
        lambda text, new: re.sub(
            r"(?<=__version__ = )[^\n]+", f'"{new}"', text
        ),
    ),
    (CHANGELOG, update_changelog),
    (BASE / "docs" / "conf.py", update_docs_config),
]


def validate_new_version(
    ctx: click.Context, param: click.Argument, value: Version
) -> Version:
    """Validate the version is newer than the current one."""
    with PYPROJECT.open("rb") as f:
        current = parse(tomli.load(f)["tool"]["poetry"]["version"])

    if not value > current:
        msg = f"version must be newer than {current}"
        raise click.BadParameter(msg)

    return value


def bump_version(new: Version) -> None:
    """Update the version number in specified files."""
    for path, perform_update in FILENAME_AND_UPDATE_TEXT:
        with path.open("r+") as f:
            contents = f.read()
            f.seek(0)
            f.write(perform_update(contents, new))
            f.truncate()


def rst2md(text: str) -> str:
    """Use Pandoc to convert text from ReST to Markdown."""
    return (
        subprocess.check_output(
            ["pandoc", "--from=rst", "--to=gfm+hard_line_breaks"],
            input=text.encode(),
        )
        .decode()
        .strip()
    )


def get_changelog_contents() -> str | None:
    if m := RST_LATEST_CHANGES.search(CHANGELOG.read_text()):
        return m.group(1)

    return None


def changelog_as_markdown(rst: str) -> str:
    """Get the latest changelog entry as hacked up Markdown."""
    for pattern, repl in create_rst_replacements():
        rst = re.sub(pattern, repl, rst, flags=re.M | re.DOTALL)

    md = rst2md(rst)

    for pattern, repl in MD_REPLACEMENTS:
        md = re.sub(pattern, repl, md, flags=re.M | re.DOTALL)

    # order bullet points in each of the lists alphabetically to
    # improve readability
    return order_bullet_points(md)


@click.group()
def cli():
    pass


@cli.command()
@click.argument("version", type=Version, callback=validate_new_version)
def bump(version: Version) -> None:
    """Bump the version in project files."""
    bump_version(version)


@cli.command()
def changelog():
    """Get the most recent version's changelog as Markdown."""
    if changelog := get_changelog_contents():
        try:
            print(changelog_as_markdown(changelog))
        except ValueError as e:
            raise click.exceptions.UsageError(str(e))


if __name__ == "__main__":
    cli()
