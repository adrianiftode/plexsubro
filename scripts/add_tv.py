# -*- coding: utf-8 -*-
"""Link a downloaded TV show folder into a Plex **TV** library root.

A TV library expects ``<Show (Year)>/Season NN/<Show (Year)> - SxxEyy.ext``. When
a download is *already* laid out that way (or Plex can match it as-is), all that
is missing is for it to live under the TV root. This tool adds the whole show
folder **by link** (a directory junction on Windows), leaving the download
untouched::

    <TV root>/<Show (Year)>/     # -> junction to the downloaded show folder

Use ``--name "<Show (Year)>"`` when the release folder is not named the way Plex
expects. If a show is *not* already structured (absolute-numbered anime, loose
episodes, combined files), use ``build_tv_layout.py`` instead — it derives the
season/episode mapping and renames as it links.

Examples
  # link a downloaded, already-structured season folder
  python add_tv.py --library "D:/Media/TV" "D:/incoming/Some.Show.S01.1080p" \\
      --name "Some Show (2020)"

  # preview
  python add_tv.py --library "D:/Media/TV" "D:/incoming/Some.Show.S01.1080p" --dry-run
"""
import argparse
import os
import re
import sys

import tvkit

sys.stdout.reconfigure(encoding="utf-8")

MODES = ("auto", "symlink", "junction", "copy")


def iter_sources(paths, children):
    """Yield the show folders to add: each path, or each immediate child."""
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
    ap.add_argument("source", nargs="+", help="downloaded show folder (repeatable)")
    ap.add_argument("--library", required=True, help="TV library root")
    ap.add_argument("--name", default=None,
                    help='show folder name, e.g. "Some Show (2020)" (default: source name)')
    ap.add_argument("--children", action="store_true",
                    help="treat each source as a folder and add each of its children")
    ap.add_argument("--exclude", action="append", default=[],
                    help="regex of names to skip (repeatable)")
    ap.add_argument("--link-mode", choices=MODES, default="auto",
                    help="auto (default): junction on Windows, symlink elsewhere")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, change nothing")
    args = ap.parse_args()

    items = [os.path.abspath(s) for s in iter_sources(args.source, args.children)]
    if args.name and len(items) != 1:
        sys.exit("--name only makes sense with a single show")
    excludes = [re.compile(x) for x in args.exclude]

    added = existing = skipped = 0
    for src in items:
        name = args.name or os.path.basename(src)
        dst = os.path.join(args.library, name)

        if any(x.search(name) for x in excludes):
            print("SKIP     %-52s (excluded)" % name)
            skipped += 1
        elif not os.path.isdir(src):
            print("BAD      %-52s (not a folder - use build_tv_layout.py)" % src)
            skipped += 1
        elif os.path.lexists(dst):
            print("EXISTS   %s" % name)
            existing += 1
        elif args.dry_run:
            print("PLAN     %-52s <- %s" % (name, src))
            added += 1
        else:
            mode = tvkit.resolve_link_mode(args.link_mode, True)
            tvkit.make_link(src, dst, mode=mode, is_dir=True)
            print("%-8s %-52s <- %s" % (mode.upper(), name, src))
            added += 1

    print("\n%d added, %d already present, %d skipped  (library: %s)"
          % (added, existing, skipped, args.library))
    if args.dry_run and added:
        print("(dry run - re-run without --dry-run to create the links)")


if __name__ == "__main__":
    main()
