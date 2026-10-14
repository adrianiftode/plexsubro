# -*- coding: utf-8 -*-
"""Validate that video files have Plex-friendly subtitle sidecars.

For every video under --dir it checks that "<video>.<lang>.srt" exists and that
the sidecar is valid UTF-8 (no BOM) with SubRip structure.

Example
  python verify.py --dir "../Some Show" --lang ro
"""
import argparse
import os
import re
import sys

import subkit

sys.stdout.reconfigure(encoding="utf-8")

TC_LINE = re.compile(
    r"^\s*\d{1,2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{1,2}:\d{2}:\d{2},\d{3}\s*$"
)


def validate(path):
    """Return (ok, problems) for a single SRT sidecar."""
    problems = []
    b = open(path, "rb").read()
    if b[:3] == b"\xef\xbb\xbf":
        problems.append("has UTF-8 BOM")
    try:
        text = b.decode("utf-8")
    except UnicodeDecodeError:
        problems.append("not valid UTF-8")
        return False, problems
    lines = text.replace("\r\n", "\n").split("\n")
    if len(lines) < 3 or not lines[0].strip().isdigit() or not TC_LINE.match(lines[1]):
        problems.append("bad SRT header")
    return (not problems), problems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", required=True, help="folder to scan (recursive)")
    ap.add_argument("--lang", default="ro", help="subtitle language suffix (default: ro)")
    ap.add_argument("--video-ext", default=",".join(subkit.VIDEO_EXT),
                    help="comma-separated video extensions")
    args = ap.parse_args()

    ext = tuple(e if e.startswith(".") else "." + e
                for e in (x.strip().lower() for x in args.video_ext.split(",")) if e)
    suffix = f".{args.lang}.srt"

    videos, sidecars = [], []
    for root, _dirs, files in os.walk(args.dir):
        for f in files:
            low = f.lower()
            if low.endswith(ext):
                videos.append(os.path.join(root, f))
            elif low.endswith(suffix):
                sidecars.append(os.path.join(root, f))

    missing, bad = [], []
    video_sidecars = set()
    for v in videos:
        sc = os.path.join(os.path.dirname(v), os.path.splitext(os.path.basename(v))[0] + suffix)
        video_sidecars.add(os.path.normcase(sc))
        if not os.path.isfile(sc):
            missing.append(v)

    for sc in sidecars:
        ok, problems = validate(sc)
        if not ok:
            bad.append((sc, problems))

    orphans = [s for s in sidecars if os.path.normcase(s) not in video_sidecars]

    print(f"root            : {os.path.abspath(args.dir)}")
    print(f"videos          : {len(videos)}")
    print(f"sidecars (.{args.lang}.srt): {len(sidecars)}")
    print(f"videos w/o sub  : {len(missing)}")
    print(f"sidecars w/ issue: {len(bad)}")
    print(f"orphan sidecars : {len(orphans)}")

    for v in missing:
        print(f"  NO SUB   {os.path.relpath(v, args.dir)}")
    for sc, problems in bad:
        print(f"  BAD      {os.path.relpath(sc, args.dir)}  [{'; '.join(problems)}]")
    for s in orphans:
        print(f"  ORPHAN   {os.path.relpath(s, args.dir)}")

    ok = not (missing or bad)
    print("\nRESULT:", "OK" if ok else "ISSUES FOUND")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
