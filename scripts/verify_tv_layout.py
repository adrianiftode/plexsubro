# -*- coding: utf-8 -*-
"""Validate a TV layout built by build_tv_layout.py.

Scans ``<show>/Season NN/`` and checks the naming, numbering and link health::

    <Show (Year)>/Season NN/<Show (Year)> - SxxEyy[-Eyy][ - title].<ext>

Reports, per season: files found, numbering **gaps**, **duplicate** episode
assignments, files that do not match the expected name, and **broken/dangling**
links (a link whose target is gone). Exit status is non-zero when issues remain.

Example
  python verify_tv_layout.py --show "/media/TV/Some Show (2002)"
"""
import argparse
import os
import re
import sys

import tvkit

sys.stdout.reconfigure(encoding="utf-8")

NAME_RE = re.compile(
    r"^.+? - S(\d{2,3})E(\d{2,3})((?:-E\d{2,3})*)(?: - .+)?(\.[^.]+)$", re.IGNORECASE
)


def parse_name(name):
    """Return (season, [episodes]) for a layout filename, or None."""
    m = NAME_RE.match(name)
    if not m:
        return None
    season = int(m.group(1))
    episodes = [int(m.group(2))]
    for part in re.findall(r"-E(\d{2,3})", m.group(3)):
        episodes.append(int(part))
    return season, episodes


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--show", required=True, help="show folder, e.g. '/media/TV/Some Show (2002)'")
    ap.add_argument("--sub-ext", default=",".join(tvkit.SUB_EXT),
                    help="comma-separated subtitle extensions to ignore as media")
    args = ap.parse_args()

    sub_ext = tuple(x if x.startswith(".") else "." + x
                    for x in (e.strip().lower() for e in args.sub_ext.split(",")) if x)

    if not os.path.isdir(args.show):
        sys.exit("not a folder: %s" % args.show)

    seasons = {}          # season -> {episode: relpath}
    unmatched = []        # files that are not episodes and not sidecars
    sidecars = 0

    for root, dirs, files in os.walk(args.show):
        # Only descend into "Season NN" folders (and the show root).
        dirs[:] = [d for d in dirs if re.match(r"^Season \d+$", d, re.I)]
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), args.show)
            if f.lower().endswith(sub_ext):
                sidecars += 1
                continue
            if not f.lower().endswith(tvkit.VIDEO_EXT):
                unmatched.append(rel)
                continue
            parsed = parse_name(f)
            if not parsed:
                unmatched.append(rel)
                continue
            season, episodes = parsed
            bucket = seasons.setdefault(season, {})
            for e in episodes:
                bucket.setdefault(e, []).append(rel)

    # broken links
    broken = []
    for root, _dirs, files in os.walk(args.show):
        for f in files:
            full = os.path.join(root, f)
            if os.path.lexists(full) and not os.path.exists(full):
                broken.append(os.path.relpath(full, args.show))

    total = sum(len(b) for b in seasons.values())
    season_list = ", ".join(str(s) for s in sorted(seasons)) or "-"
    print("root            : %s" % os.path.abspath(args.show))
    print("seasons         : %s" % season_list)
    print("episode files   : %d" % total)
    print("sidecars        : %d" % sidecars)
    print("broken links    : %d" % len(broken))
    print("unmatched files : %d" % len(unmatched))

    issues = bool(broken or unmatched)
    for season in sorted(seasons):
        bucket = seasons[season]
        present = sorted(bucket)
        dups = {e: sorted(set(rs)) for e, rs in bucket.items() if len(set(rs)) > 1}
        gaps = sorted(set(range(1, present[-1] + 1)) - set(present)) if present else []
        print("\nSeason %02d: %d episode(s), span 1-%d" %
              (season, len(present), present[-1] if present else 0))
        if dups:
            issues = True
            for e, rs in sorted(dups.items()):
                print("  DUPLICATE Ep%02d: %s" % (e, ", ".join(rs)))
        if gaps:
            print("  gaps: %s" % ", ".join("Ep%02d" % g for g in gaps))

    for rel in broken:
        print("  BROKEN   %s" % rel)
    for rel in unmatched:
        print("  UNMATCHED %s" % rel)

    print("\nRESULT:", "OK" if not issues else "ISSUES FOUND")
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
