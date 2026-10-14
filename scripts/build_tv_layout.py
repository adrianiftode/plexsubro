# -*- coding: utf-8 -*-
"""Build a Plex-friendly TV layout by linking existing video files.

Plex only treats a file as an episode when it sits in a **TV** library under
``<Show (Year)>/Season NN/`` and (ideally) is named ``Show (Year) - SxxEyy.ext``.
Rather than moving or renaming a collection, this tool creates a **parallel
layout of links** in a separate TV root and leaves the originals untouched.

For each item it derives (season, episode[s]) and creates::

    <target-root>/<Show (Year)>/Season NN/<Show (Year)> - SxxEyy[-Eyy].<ext>

Sibling sidecar subtitles (``<video>.<lang>.srt``) are carried to the new name.

Two ways to describe the collection
  --spec FILE     explicit JSON list of items (full control: titles, specials,
                  whole-folder links). See README.
  --source DIR    auto-derive items from filenames using --episode-regex and
                  --seasons; add --specials PATHS and --exclude REGEX to trim.

Link types (--link-mode)
  hardlink   default; same data, same volume, no extra space. Best for per-file
             renames; Plex sees a normal file.
  symlink    file/dir symlink (cross-volume; needs privilege on Windows).
  junction   Windows directory junction (auto-used for whole folders).
  copy       real copies (cross-volume, no links).

Examples
  # dry run: absolute-numbered collection split across four seasons
  python build_tv_layout.py --target-root "/media/TV" --show "Some Show (2002)" \\
      --source "/incoming/Some Show" \\
      --episode-regex 'Show_(\\d{1,3}(?:[-_]\\d{1,3})*)' \\
      --seasons "1:1-52,2:53-104,3:105-158,4:159-220" --carry-subs

  # apply a hand-written spec
  python build_tv_layout.py --target-root "/media/TV" --spec layout.json --apply
"""
import argparse
import json
import os
import re
import sys

import tvkit

sys.stdout.reconfigure(encoding="utf-8")


def load_spec(path):
    with open(path, encoding="utf-8") as f:
        spec = json.load(f)
    if not spec.get("show"):
        raise SystemExit("spec is missing a 'show' name")
    items = []
    for raw in spec.get("items", []):
        item = {
            "source": raw["source"],
            "season": int(raw.get("season", 1)),
            "title": raw.get("title"),
            "folder": bool(raw.get("folder")),
        }
        if not item["folder"]:
            if raw.get("episodes"):
                item["episodes"] = [int(e) for e in raw["episodes"]]
            else:
                first = int(raw["episode"])
                last = int(raw.get("end_episode", first))
                item["episodes"] = list(range(first, last + 1))
        items.append(item)
    return spec["show"], items


def derive_items(args):
    """Auto-derive items from --source folders using --episode-regex/--seasons."""
    ranges = tvkit.parse_seasons(args.seasons)
    excludes = [re.compile(x) for x in (args.exclude or [])]

    videos = []
    for src in args.source:
        if os.path.isfile(src):
            videos.append(src)
        else:
            videos.extend(tvkit.list_files(src, tvkit.VIDEO_EXT))

    items, skipped = [], []
    for v in videos:
        base = os.path.basename(v)
        if any(x.search(base) for x in excludes):
            skipped.append((base, "excluded"))
            continue
        eps = tvkit.extract_episodes(base, args.episode_regex)
        if not eps:
            skipped.append((base, "no episode token matched"))
            continue
        season = tvkit.season_for(eps[0], ranges)
        if season is None:
            skipped.append((base, "episode %d outside every season range" % eps[0]))
            continue
        items.append({"source": v, "season": season, "episodes": eps,
                      "title": None, "folder": False})

    for i, path in enumerate(args.specials or [], 1):
        items.append({"source": path, "season": 0, "episodes": [i],
                      "title": None, "folder": False})
    return items, skipped


def dest_path(show_dir, show, item):
    season_dir = os.path.join(show_dir, tvkit.season_dir(item["season"]))
    if item["folder"]:
        return season_dir
    ext = os.path.splitext(item["source"])[1]
    name = tvkit.target_name(show, item["season"], item["episodes"], item["title"], ext)
    return os.path.join(season_dir, name)


def emit_spec(path, show, items):
    payload = {
        "show": show,
        "items": [
            {"source": it["source"], "season": it["season"],
             "episodes": it["episodes"], "title": it["title"]}
            if not it["folder"] else
            {"source": it["source"], "season": it["season"], "folder": True}
            for it in items
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print("wrote spec: %s (%d items)" % (path, len(items)))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--target-root", required=True, help="TV library root")
    ap.add_argument("--spec", default=None, help="JSON layout spec (instead of --source)")
    ap.add_argument("--show", default=None, help="show folder name, e.g. 'Some Show (2002)'")
    ap.add_argument("--source", action="append", default=[],
                    help="folder/file with episodes (repeatable)")
    ap.add_argument("--episode-regex", default=None,
                    help="regex whose group(1) holds the episode token")
    ap.add_argument("--seasons", default="1:1-9999",
                    help="season split 'S:FIRST-LAST,...' (default '1:1-9999')")
    ap.add_argument("--special", dest="specials", action="append", default=[],
                    help="file to place in Season 00 (repeatable)")
    ap.add_argument("--exclude", action="append", default=[],
                    help="regex of filenames to skip (repeatable)")
    ap.add_argument("--carry-subs", action="store_true",
                    help="also link sibling subtitle sidecars under the new name")
    ap.add_argument("--sub-ext", default=",".join(tvkit.SUB_EXT),
                    help="comma-separated subtitle extensions to carry")
    ap.add_argument("--link-mode", choices=("hardlink", "symlink", "junction", "copy"),
                    default="hardlink")
    ap.add_argument("--emit-spec", default=None,
                    help="write the derived items to this JSON file")
    ap.add_argument("--apply", action="store_true", help="create links (default: dry run)")
    args = ap.parse_args()

    if args.spec:
        show, items = load_spec(args.spec)
        skipped = []
    elif args.source:
        if not args.show:
            sys.exit("--show is required when using --source")
        if not args.episode_regex:
            sys.exit("--episode-regex is required when using --source")
        show, items = args.show, None
        items, skipped = derive_items(args)
    else:
        sys.exit("provide --spec, or --source with --show/--episode-regex")

    if args.emit_spec:
        emit_spec(args.emit_spec, show, items)

    show_dir = os.path.join(args.target_root, show)
    sub_ext = tuple(x if x.startswith(".") else "." + x
                    for x in (e.strip().lower() for e in args.sub_ext.split(",")) if x)

    made = existing = 0
    for item in items:
        src = item["source"]
        if not os.path.lexists(src):
            print("MISSING  %s" % src)
            continue
        dst = dest_path(show_dir, show, item)
        rel = os.path.relpath(dst, args.target_root)

        if not args.apply:
            kind = "folder" if item["folder"] else tvkit.episode_tag(item["season"], item["episodes"])
            print("PLAN     %-40s <- %s  [%s]" % (rel, os.path.basename(src), kind))
            made += 1
            continue

        result = tvkit.make_link(src, dst, mode=args.link_mode, is_dir=item["folder"])
        if result == "exists":
            existing += 1
            print("EXISTS   %s" % rel)
        else:
            made += 1
            print("%-8s %s <- %s" % (result.upper(), rel, os.path.basename(src)))

        if args.carry_subs and not item["folder"]:
            stem = os.path.splitext(dst)[0]
            for sub_path, tail in tvkit.sibling_subs(src, sub_ext):
                tvkit.make_link(sub_path, stem + tail, mode=args.link_mode)

    for name, why in skipped:
        print("SKIP     %-40s (%s)" % (name, why))

    verb = "created" if args.apply else "planned"
    print("\nshow=%s  %d item(s) %s, %d already present, %d skipped."
          % (show, made, verb, existing, len(skipped)))
    if not args.apply and made:
        print("(dry run - re-run with --apply to create the links)")


if __name__ == "__main__":
    main()
