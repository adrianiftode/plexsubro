# -*- coding: utf-8 -*-
"""Shared helpers for building a Plex-friendly TV layout out of a collection.

Plex decides whether a file is an *episode* by where it lives, not by what it is
named: files named like ``... S01E01 ...`` are ignored inside a **Movies**
library and belong in a **TV** library laid out as::

    <TV root>/<Show (Year)>/Season NN/<Show (Year)> - SxxEyy.<ext>

Rebuilding a collection into that shape normally means moving and renaming the
originals. This kit never does that: it derives the season/episode for each file
from a regular expression plus a season-range mapping and then **links** (hard
link, symlink, junction) or copies the originals into the TV root. Sources are
only ever read.

Nothing here hard-codes a path, a show name or a numbering scheme -- everything
is supplied by the caller (CLI flags or a JSON spec).
"""
import os
import re
import shutil
import subprocess
import sys

VIDEO_EXT = (".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm", ".mpg", ".mpeg")
SUB_EXT = (".srt", ".ass", ".ssa", ".vtt")

# 'S:FIRST-LAST' pairs, e.g. "1:1-52,2:53-104".
SEASON_RANGE_RE = re.compile(r"^\s*(\d{1,3})\s*:\s*(\d{1,3})\s*-\s*(\d{1,3})\s*$")


# --------------------------------------------------------------------------- #
# season mapping
# --------------------------------------------------------------------------- #
def parse_seasons(spec):
    """Parse "1:1-52,2:53-104" into ``[(season, first, last), ...]``."""
    ranges = []
    for part in (spec or "").split(","):
        part = part.strip()
        if not part:
            continue
        m = SEASON_RANGE_RE.match(part)
        if not m:
            raise ValueError(
                "bad season range %r (expected 'SEASON:FIRST-LAST', e.g. '1:1-52')" % part
            )
        ranges.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    if not ranges:
        raise ValueError("empty season spec")
    return ranges


def season_for(episode, ranges):
    """Return the season that owns *episode*, or None if no range covers it."""
    for season, first, last in ranges:
        if first <= episode <= last:
            return season
    return None


def parse_episode_token(token):
    """'01' / '26-27' / '166_167' / '202-203-204' -> [1] / [26, 27] / ..."""
    return [int(n) for n in re.split(r"[-_]", token) if n.isdigit()]


def extract_episodes(name, pattern):
    """Return the episode numbers captured by *pattern* in *name*.

    *pattern* must have a capture group holding the episode token, which may be a
    run such as ``26-27``. Only the first match is used, so trailing hashes in a
    release name are ignored. Returns ``[]`` when nothing matches.
    """
    m = re.search(pattern, name)
    if not m:
        return []
    return parse_episode_token(m.group(1))


# --------------------------------------------------------------------------- #
# naming
# --------------------------------------------------------------------------- #
def episode_tag(season, episodes):
    """[26, 27] in season 1 -> 'S01E26-E27'."""
    tag = "S%02dE%02d" % (season, episodes[0])
    for e in episodes[1:]:
        tag += "-E%02d" % e
    return tag


def target_name(show, season, episodes, title, ext):
    """Build the Plex filename, e.g. 'Some Show (2002) - S01E26-E27 - Title.mkv'."""
    name = "%s - %s" % (show, episode_tag(season, episodes))
    if title:
        name += " - %s" % title
    return name + ext


def season_dir(season):
    return "Season %02d" % season


# --------------------------------------------------------------------------- #
# filesystem helpers
# --------------------------------------------------------------------------- #
def list_files(folder, exts):
    """Recursively list files under *folder* whose name ends with one of *exts*."""
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(tuple(exts)):
                out.append(os.path.join(root, f))
    return sorted(out)


def sibling_subs(video, sub_ext=SUB_EXT):
    """Return ``(path, tail)`` for sidecars that share the video's stem.

    ``ep01.mkv`` with ``ep01.ro.srt`` -> ``(".../ep01.ro.srt", ".ro.srt")``.
    *tail* is what gets re-applied to the video's new name.
    """
    stem = os.path.splitext(video)[0]
    folder, base = os.path.split(stem)
    out = []
    try:
        names = os.listdir(folder or ".")
    except OSError:
        return out
    for f in names:
        if not f.startswith(base + "."):
            continue
        tail = f[len(base):]
        if tail.lower().endswith(tuple(sub_ext)):
            out.append((os.path.join(folder, f), tail))
    return sorted(out)


def resolve_link_mode(mode, is_dir):
    """Turn ``auto`` into a concrete mode: folders -> junction/symlink, files -> hardlink."""
    if mode != "auto":
        return mode
    if is_dir:
        return "junction" if sys.platform == "win32" else "symlink"
    return "hardlink"


def make_link(src, dst, mode="hardlink", is_dir=False):
    """Create *dst* pointing at *src*. Returns one of linked/junction/copied/exists.

    ``mode`` is one of ``hardlink`` (default, no extra space, same volume),
    ``symlink`` (cross-volume, needs privilege on Windows), ``junction``
    (Windows directories) or ``copy``. Directory sources can only be linked,
    not hard-linked/copied: ``hardlink``/``copy`` silently fall back to a
    junction/symlink for them.
    """
    if os.path.lexists(dst):
        return "exists"

    parent = os.path.dirname(dst)
    if parent:
        os.makedirs(parent, exist_ok=True)

    if is_dir:
        if mode in ("hardlink", "copy"):
            mode = "junction" if sys.platform == "win32" else "symlink"
        if mode == "junction":
            return _junction(src, dst)
        os.symlink(os.path.abspath(src), dst, target_is_directory=True)
        return "linked"

    if mode == "hardlink":
        os.link(src, dst)
    elif mode == "symlink":
        os.symlink(os.path.abspath(src), dst)
    elif mode == "copy":
        shutil.copy2(src, dst)
    elif mode == "junction":
        raise ValueError("a junction is only valid for directories")
    else:
        raise ValueError("unknown link mode %r" % mode)
    return "linked"


def _junction(src, dst):
    """Create a Windows directory junction (falling back to a symlink elsewhere)."""
    src, dst = os.path.abspath(src), os.path.abspath(dst)
    if sys.platform != "win32":
        os.symlink(src, dst, target_is_directory=True)
        return "linked"
    try:
        import _winapi
        _winapi.CreateJunction(src, dst)
        return "junction"
    except Exception:
        subprocess.run(
            ["cmd", "/c", "mklink", "/J", dst, src],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        return "junction"
