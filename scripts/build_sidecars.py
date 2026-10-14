# -*- coding: utf-8 -*-
"""Write Plex external subtitle sidecars next to video files.

Pairs each video with a source subtitle, converts it to UTF-8 SRT (no BOM) and
saves it as "<video basename>.<lang>.srt" in the video's own folder. Video files
are never modified, renamed or moved.

Source formats: SubRip (.srt), ASS/SSA (.ass/.ssa), SubViewer 2.0 (.sub),
MicroDVD (.sub, frame based).

Matching modes
  episode  match by S01E02 / 1x02 token                  (TV seasons)
  name     match by filename token similarity            (movies / one-offs)
  auto     episode when any video has an episode token, else name  (default)

A JSON --map can force specific pairs (handy for specials or oddly numbered
files); it takes precedence over automatic matching.

Examples
  # TV season
  python build_sidecars.py --videos "../Some Show/Season 01" --subs "./subs" --lang ro --apply

  # a folder of movies (name matching)
  python build_sidecars.py --videos "./movies" --subs "./subs" --mode name --apply

  # explicit overrides
  python build_sidecars.py --videos . --subs ./subs --map pairs.json --apply
"""
import argparse
import glob
import json
import os
import sys

import subkit

sys.stdout.reconfigure(encoding="utf-8")


def read_videos(path, recursive):
    if os.path.isfile(path):
        return [path]
    if recursive:
        return sorted(subkit.list_files(path, subkit.VIDEO_EXT))
    out = []
    for f in sorted(os.listdir(path)):
        full = os.path.join(path, f)
        if os.path.isfile(full) and f.lower().endswith(subkit.VIDEO_EXT):
            out.append(full)
    return out


def load_map(path, subs, subs_dir):
    if not path:
        return {}
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    map_dir = os.path.dirname(os.path.abspath(path))
    resolved = {}
    for k, v in raw.items():
        cand = v if os.path.isabs(v) else os.path.join(subs_dir, v)
        if not os.path.isfile(cand):
            cand = os.path.join(map_dir, v)
        if not os.path.isfile(cand):
            hits = [s for s in subs if os.path.basename(s) == os.path.basename(v)]
            cand = hits[0] if hits else None
        resolved[k] = cand
    return resolved


def choose(video, mode, subs, by_ep, prefer):
    base = os.path.basename(video)
    if mode == "episode":
        cands = by_ep.get(subkit.episode_key(base), [])
        return subkit.pick(cands, base, prefer) if cands else None
    # name mode
    if not subs:
        return None
    best = subkit.pick(subs, base, prefer)
    return best if subkit.score(best, base) > 0 else None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--videos", required=True, help="video file or folder")
    ap.add_argument("--subs", required=True, help="folder of source subtitles (recursive)")
    ap.add_argument("--lang", default="ro", help="language suffix (default: ro)")
    ap.add_argument("--mode", choices=("auto", "episode", "name"), default="auto")
    ap.add_argument("--prefer", default=None,
                    help="regex preferring some candidates, e.g. '1080p' or 'BluRay'")
    ap.add_argument("--map", dest="map_file", default=None,
                    help="JSON {video name or SxxEyy: subtitle file} overrides")
    ap.add_argument("--microdvd-fps", type=float, default=23.976)
    ap.add_argument("--recursive", action="store_true", help="search --videos recursively")
    ap.add_argument("--apply", action="store_true", help="write files (default: dry run)")
    args = ap.parse_args()

    videos = read_videos(args.videos, args.recursive)
    if not videos:
        sys.exit("No video files found.")
    subs = subkit.list_files(args.subs, subkit.SUB_EXT)
    overrides = load_map(args.map_file, subs, args.subs)

    mode = args.mode
    if mode == "auto":
        mode = "episode" if any(subkit.episode_key(os.path.basename(v)) for v in videos) else "name"

    by_ep = {}
    for s in subs:
        k = subkit.episode_key(os.path.basename(s))
        if k:
            by_ep.setdefault(k, []).append(s)

    written = unmatched = 0
    for v in videos:
        base = os.path.basename(v)
        src = overrides.get(base) or overrides.get(subkit.episode_key(base))
        if not src:
            src = choose(v, mode, subs, by_ep, args.prefer)
        if not src or not os.path.isfile(src):
            unmatched += 1
            print(f"NO SUB   {base}")
            continue
        try:
            cues = subkit.load_cues(src, args.microdvd_fps)
        except Exception as ex:
            unmatched += 1
            print(f"ERROR    {base}: {ex}")
            continue
        if not cues:
            unmatched += 1
            print(f"EMPTY    {base} <- {os.path.basename(src)}")
            continue
        out = os.path.join(os.path.dirname(v), os.path.splitext(base)[0] + f".{args.lang}.srt")
        data = subkit.to_srt(cues).encode("utf-8")
        if args.apply:
            with open(out, "wb") as f:
                f.write(data)
        written += 1
        print(f"{'WROTE ' if args.apply else 'PLAN  '} {os.path.basename(out)} "
              f"({len(cues)} cues) <- {os.path.basename(src)}")

    print(f"\nmode={mode}  {written} subtitle(s) {'written' if args.apply else 'planned'}, "
          f"{unmatched} unmatched.")
    if not args.apply and written:
        print("(dry run - re-run with --apply to write files)")


if __name__ == "__main__":
    main()
