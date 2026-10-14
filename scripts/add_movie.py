# -*- coding: utf-8 -*-
"""Link a downloaded movie into a Plex **Movies** library root.

Plex reads a Movies library from one or more folders, and a movie may be either a
single video file or a folder that holds it. This tool adds such an item to a
library root **by link**, so the download folder stays the source of truth and
nothing is moved, renamed, re-encoded or deleted::

    <Movies root>/<Movie (Year)>/...        # folder source -> directory junction
    <Movies root>/<Movie (Year).mkv>        # single file   -> hard link

It is meant to be run once per download (or over a whole folder to migrate an
existing dump). Point it at your *Movies* root; for TV shows use ``add_tv.py``.

Examples
  # after a download lands in the torrent folder
  python add_movie.py --library "D:/Media/Movies" "D:/incoming/Some Movie (2020)"

  # preview only, and add every child of a folder (first-time migration)
  python add_movie.py --library "D:/Media/Movies" --children "D:/incoming" --dry-run

  # across volumes there is no hard-link option: symlink or copy instead
  python add_movie.py --library "E:/Movies" "D:/incoming/Some Movie (2020)" --link-mode copy
"""
import argparse
import os
import re
import sys

import tvkit

sys.stdout.reconfigure(encoding="utf-8")

MODES = ("auto", "hardlink", "symlink", "junction", "copy")


def iter_sources(paths, children):
    """Yield the items to add: each path, or each immediate child of each path."""
    for p in paths:
        if children:
            if not os.path.isdir(p):
                raise SystemExit("--children expects folders, not %r" % p)
            for name in sorted(os.listdir(p)):
                yield os.path.join(p, name)
        else:
            yield p


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("source", nargs="+", help="movie file or folder (repeatable)")
    ap.add_argument("--library", required=True, help="Movies library root")
    ap.add_argument("--name", default=None,
                    help="link name (default: the source's own name)")
    ap.add_argument("--children", action="store_true",
                    help="treat each source as a folder and add each of its children")
    ap.add_argument("--exclude", action="append", default=[],
                    help="regex of names to skip (repeatable)")
    ap.add_argument("--link-mode", choices=MODES, default="auto",
                    help="auto (default): folders -> junction, files -> hard link")
    ap.add_argument("--carry-subs", action="store_true",
                    help="also link a file source's sibling subtitle sidecars")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    args = ap.parse_args()

    items = [os.path.abspath(s) for s in iter_sources(args.source, args.children)]
    if args.name and len(items) != 1:
        sys.exit("--name only makes sense with a single item")
    excludes = [re.compile(x) for x in args.exclude]

    added = existing = skipped = 0
    for src in items:
        name = args.name or os.path.basename(src)
        dst = os.path.join(args.library, name)

        if any(x.search(name) for x in excludes):
            print("SKIP     %-52s (excluded)" % name)
            skipped += 1
        elif not os.path.lexists(src):
            print("MISSING  %s" % src)
            skipped += 1
        elif os.path.lexists(dst):
            print("EXISTS   %s" % name)
            existing += 1
        elif args.dry_run:
            print("PLAN     %-52s <- %s" % (name, src))
            added += 1
        else:
            is_dir = os.path.isdir(src)
            mode = tvkit.resolve_link_mode(args.link_mode, is_dir)
            tvkit.make_link(src, dst, mode=mode, is_dir=is_dir)
            print("%-8s %-52s <- %s" % (mode.upper(), name, src))
            if args.carry_subs and not is_dir:
                stem = os.path.splitext(dst)[0]
                for sub_path, tail in tvkit.sibling_subs(src):
                    tvkit.make_link(sub_path, stem + tail, mode=mode)
                    print("%-8s %s" % (mode.upper(), name + tail))
            added += 1

    print("\n%d added, %d already present, %d skipped  (library: %s)"
          % (added, existing, skipped, args.library))
    if args.dry_run and added:
        print("(dry run - re-run without --dry-run to create the links)")


if __name__ == "__main__":
    main()
