# plexsubro

Build **Plex-compatible external subtitle sidecars** for an existing video
collection, without touching the video files. Point it at a folder of videos and
a folder of source subtitles; it writes one `<video>.<lang>.srt` next to each
video. Romanian (`ro`) is the default language, but any language code works.

The tool only *adds* sidecar subtitle files — it never renames, moves, re-encodes
or deletes the videos.

The repo also ships a second, independent tool set that builds a **Plex TV
layout** for a collection Plex currently ignores (episodes filed under a Movies
library, an absolute-numbered series, and so on). It follows the same rule: it
only *links* the originals into a TV-ready folder structure — it never renames,
moves, re-encodes or deletes them. See
[Making an existing collection show up as a TV show](#making-an-existing-collection-show-up-as-a-tv-show).

Two tiny helpers, `add_movie.py` and `add_tv.py`, cover the routine "link today's
download into the right library root" step. See
[Adding a new download to a library](#adding-a-new-download-to-a-library).

---

## What it does

1. Finds the video files in a folder.
2. Pairs each one with the best matching source subtitle (by episode code, by
   filename similarity, or by an explicit mapping).
3. Converts that subtitle to **UTF-8 SubRip (`.srt`)** with no BOM.
4. Saves it as `<video basename>.<lang>.srt` in the video's folder.

---

## Why the naming matters (Plex)

Plex only picks up an external subtitle when:

- it is **in the same folder** as the video,
- its **filename equals the video's basename**, and
- it ends with a **language suffix** — ISO‑639‑1 like `.ro`, or a language name
  like `.Romanian`.

So for `Some Show S01E01.mkv` the sidecar must be `Some Show S01E01.ro.srt`.

| Requirement | Value |
|---|---|
| Container | SubRip (`.srt`) |
| Encoding | UTF‑8 **without BOM** |
| Line endings | CRLF |
| Language suffix | `.ro`, `.en`, … (ISO‑639‑1) |

After adding the files, run **Scan Library Files**, then **Analyze** in Plex so
the subtitles are attached.

---

## Requirements

- **Python 3.8+** — standard library only, no packages to install.
- Optional, for the download/extract steps in the workflow below:
  - an archiver that can read `.zip` and `.rar`. On Windows, the built‑in
    `tar.exe` (bsdtar) reads both; on other systems `bsdtar`/`unrar` work.
  - `curl` (or any HTTP client) to fetch subtitle packs.
- For the TV-layout tool: linking video files needs the source and target on the
  **same filesystem** for hard links (the default); use `--link-mode symlink` or
  `--link-mode copy` across volumes. On Windows, a directory junction (used
  automatically for whole folders) needs no special privilege, but a file
  symlink does.

The Python scripts are portable (Windows, macOS, Linux).

---

## Install

```bash
git clone https://github.com/adrianiftode/plexsubro.git
cd plexsubro
```

---

## Repository layout

```
plexsubro/
├─ README.md
├─ LICENSE
└─ scripts/
   ├─ subkit.py             # subtitle library: parsers, conversion, matching
   ├─ build_sidecars.py     # pair videos + subs -> <video>.<lang>.srt
   ├─ verify.py             # check subtitle coverage and sidecar validity
   ├─ tvkit.py              # shared library: episode parsing, season map, links
   ├─ build_tv_layout.py    # link videos into <Show (Year)>/Season NN/ for Plex
   ├─ verify_tv_layout.py   # check a TV layout: gaps, duplicates, broken links
   ├─ add_movie.py          # link one downloaded movie into a Movies root
   └─ add_tv.py             # link one downloaded show folder into a TV root
```

---

## Usage

### 1. Build sidecars for a season

```bash
# dry run first: prints what would be written
python scripts/build_sidecars.py \
    --videos "../Some Show/Season 01" \
    --subs   "./subtitle-sources" \
    --lang ro

# when the plan looks right, write the files
python scripts/build_sidecars.py \
    --videos "../Some Show/Season 01" \
    --subs   "./subtitle-sources" \
    --lang ro --apply
```

### 2. Build sidecars for individual movies / one-offs

Use name matching instead of episode matching:

```bash
python scripts/build_sidecars.py \
    --videos "./movies" \
    --subs   "./subtitle-sources" \
    --mode name --apply
```

### 3. Force specific pairings (`--map`)

For specials, recaps, or oddly numbered files, provide a JSON map. It takes
precedence over automatic matching:

```json
{
  "Some Show S00E01.mkv": "specials/ova-01.srt",
  "movie-file-name.mkv":  "movie.ro.srt"
}
```

```bash
python scripts/build_sidecars.py --videos . --subs ./subtitle-sources --map pairs.json --apply
```

### 4. Verify

```bash
python scripts/verify.py --dir "../Some Show" --lang ro
```

Reports how many videos have a sidecar, lists any missing ones, checks that each
sidecar is valid UTF‑8 (no BOM) with SubRip structure, and flags orphan sidecars.

---

## Matching & options

| Option | Meaning |
|---|---|
| `--mode auto` | `episode` if any video has a `SxxEyy`/`1x01` token, else `name` (default) |
| `--mode episode` | Match strictly by episode token (seasons) |
| `--mode name` | Match by filename token overlap (movies, one-offs) |
| `--prefer REGEX` | When several source subs match, prefer the one matching the regex, e.g. `2160p`, `BluRay`, `WEB` |
| `--map FILE` | JSON overrides (see above) |
| `--microdvd-fps N` | Frame rate for MicroDVD `.sub` (default `23.976`) |
| `--recursive` | Search the `--videos` folder recursively |
| `--apply` | Actually write files (default is a dry run) |

---

## Format & encoding handling

Source subtitles come in many legacy shapes; all are normalised to UTF‑8 SRT.

| Input | Handling |
|---|---|
| SubRip `.srt` (UTF‑8 or CP1250, with/without BOM) | tolerant timecode-arrow regex, tag stripping, cue renumbering |
| ASS/SSA `.ass`/`.ssa` | `[Events]` `Dialogue:` lines; `{…}` override tags stripped; `\N`/`\n` → newline, `\h` → space |
| SubViewer 2.0 `.sub` | `hh:mm:ss.xx , hh:mm:ss.xx` → SRT; `[br]` → newline |
| MicroDVD `.sub` | `{start}{end}text` frames → timecodes at `--microdvd-fps`; `\|` → newline |
| Legacy encoding | UTF‑8 first, fall back to **CP1250** |

`subkit.decode()` accepts a custom encoding list if your sources need something
else.

---

## Typical end-to-end workflow

```bash
# 1. obtain a source subtitle pack for the collection, e.g. a .zip/.rar archive

# 2. extract it (Windows bsdtar reads .zip and .rar incl. RAR4)
mkdir -p ./subtitle-sources
tar -xf ./downloaded-pack.zip -C ./subtitle-sources

# 3. build sidecars (dry run, then apply)
python scripts/build_sidecars.py --videos "../Some Show/Season 01" --subs ./subtitle-sources --lang ro
python scripts/build_sidecars.py --videos "../Some Show/Season 01" --subs ./subtitle-sources --lang ro --apply

# 4. verify
python scripts/verify.py --dir "../Some Show" --lang ro

# 5. in Plex: Scan Library Files, then Analyze
```

---

## Making an existing collection show up as a TV show

Plex decides how to treat a file by **where it lives**, not by what the file is.
A file named like `... S01E01 ...` that sits inside a **Movies** library is
ignored by the movie scanner — movies have no `SxxEyy` concept — so it needs a
**TV** library instead. A TV library expects this shape:

```
<TV root>/
└─ Show Name (Year)/
   ├─ Season 01/
   │  └─ Show Name (Year) - S01E01.mkv
   └─ Season 00/                 # specials
```

Rebuilding a collection into that shape normally means moving and renaming the
files — which this repo never does. Instead, `build_tv_layout.py` creates a
**parallel layout of links** under a TV root and leaves every original exactly
where it is:

| Situation | What it does |
|---|---|
| Season folder is already `SxxEyy`-named | links the whole folder with a **directory junction** (Windows) / symlink |
| Files are absolute- or oddly-numbered | creates one **hard link per file**, renamed `Show (Year) - SxxEyy[-Eyy].ext`, sorted into seasons from a mapping |
| One file holds several episodes | names it as a range, e.g. `S01E26-E27` |
| Specials / OVAs | placed in `Season 00` |
| Sidecar subtitles exist | carried to the new names (e.g. `...S01E26-E27.ro.srt`) |
| A file is superseded | skipped with `--exclude REGEX` |

Hard links share the original data (no extra disk space, same volume required);
directory junctions/symlinks work across folders and volumes. **Nothing is ever
renamed, moved, re-encoded or deleted.**

### 1. Decide the season split first

Plex names episodes to match a metadata source. For a single-season show there
is nothing to decide. For an **absolute-numbered** series (common in anime) you
must pick the split Plex will match against — typically the show's TheMovieDB
**"Aired"** ordering (e.g. `52 / 52 / 54 / 62`), or an **"Absolute"** episode
group (all episodes in `S01E001`–`S01E220`, chosen per-show in Plex under
*Advanced → Episode Ordering*). Decide this **before** building, because the
`--seasons` mapping and Plex have to agree.

### 2. Dry run

```
python scripts/build_tv_layout.py \
    --target-root "/media/TV" \
    --show "Some Show (2002)" \
    --source "/incoming/Some Show" \
    --episode-regex 'Show_(\d{1,3}(?:[-_]\d{1,3})*)' \
    --seasons "1:1-52,2:53-104,3:105-158,4:159-220" \
    --carry-subs
```

`--episode-regex` must contain one capture group holding the episode token; the
token may be a run like `26-27`, which is kept as a multi-episode file. Review
the plan (each file, its season/episode, and anything skipped), then re-run the
same command with `--apply`.

Notes:

- `--seasons` is `SEASON:FIRST-LAST` pairs; the default is `1:1-9999` (one
  season). Use `--special PATH` (repeatable) for `Season 00` items.
- `--exclude REGEX` skips superseded/duplicate files (e.g. a lone `…_202_` when a
  `…_202-203-204_` file already covers it).
- `--emit-spec layout.json` writes the derived items to JSON so you can edit
  them (titles, specials) and feed them back with `--spec`.

### 3. Full control with a spec file

```json
{
  "show": "Some Show (2002)",
  "items": [
    { "source": "/incoming/ep01.mkv",    "season": 1, "episode": 1 },
    { "source": "/incoming/ep02_03.mkv", "season": 1, "episode": 2, "end_episode": 3 },
    { "source": "/incoming/ova.mkv",     "season": 0, "episode": 1, "title": "OVA" },
    { "source": "/incoming/Some Show S01", "season": 1, "folder": true }
  ]
}
```

```
python scripts/build_tv_layout.py --target-root "/media/TV" --spec layout.json          # dry run
python scripts/build_tv_layout.py --target-root "/media/TV" --spec layout.json --apply
```

### 4. Verify

```
python scripts/verify_tv_layout.py --show "/media/TV/Some Show (2002)"
```

Reports the files per season, numbering **gaps** (missing source episodes —
reported, not fatal), **duplicate** episode assignments, files that do not match
the name scheme, and **broken/dangling** links. Exit status is non-zero on
duplicates, unmatched files or broken links.

### 5. Point Plex at the TV root

In Plex: **Settings → Manage → Libraries → Add Library → TV Shows**, add the
**TV root** (not the Movies root), then **Scan Library Files**. If the show
matches but the episode numbers look wrong, set the per-show
**Advanced → Episode Ordering** to the same ordering you built with.

---

## Adding a new download to a library

Once your media is organised into a Movies root and a TV root, the day-to-day
task is "link today's download into the right root". Two small scripts do exactly
that — and like everything else here they **only add a link**, never touching,
moving or renaming the download:

| Script | Puts | Into |
|---|---|---|
| `add_movie.py` | a movie file, or a folder that holds one | a **Movies** root |
| `add_tv.py` | a whole show folder, as-is | a **TV** root |

Both take any paths (nothing is hard-coded) and are safe to re-run: an item that
is already linked is reported, not duplicated.

### Movies

```bash
# a folder download  -> a directory junction named after the folder
python scripts/add_movie.py --library "D:/Media/Movies" "D:/incoming/Some Movie (2020)"

# a single video file -> a hard link
python scripts/add_movie.py --library "D:/Media/Movies" "D:/incoming/Some.Movie.2020.mkv"

# first-time migration: link every child of a dump folder except the TV shows
python scripts/add_movie.py --library "D:/Media/Movies" --children "D:/incoming" \
    --exclude "Some Show|Another Show" --dry-run
```

- a **folder** source becomes a **directory junction**; a **file** source becomes
  a **hard link** (same volume, no extra space). Across volumes use
  `--link-mode symlink` or `--link-mode copy`.
- for a **file** source, add `--carry-subs` to also link its sibling subtitle
  sidecars (`Movie.mkv` + `Movie.ro.srt`) under the matching name. Sidecars that
  sit *inside* a folder come along with the junction automatically.
- `--name` changes the *link's* name only; `--exclude REGEX` skips names;
  `--children` treats each argument as a container of items to add.
- `--dry-run` previews; without it the links are created immediately.

### TV shows

```bash
python scripts/add_tv.py --library "D:/Media/TV" "D:/incoming/Some.Show.S01.1080p" \
    --name "Some Show (2020)"
```

`add_tv.py` links the **whole folder as-is**, so use it when the download already
follows Plex's `Show (Year)/Season NN/` shape (or Plex can match it). For
absolute-numbered or loosely named collections, use `build_tv_layout.py` above —
it works out the season/episode mapping and renames while it links.

Then in Plex, run **Scan Library Files** for the library you added to.

> Convention note: the two `build_*` tools are **dry-run first** and require
> `--apply`; the two `add_*` tools **act immediately** and take `--dry-run` to
> preview. None of them ever modify the source files.

---

## Using this repo with an AI assistant

The tooling is deliberately assistant-agnostic: plain Python, no dependencies,
and this README carries all the domain knowledge. Any coding assistant (ChatGPT,
Claude, Gemini, GitHub Copilot, Cursor, opencode, …) can run the workflow on a
new collection. Both workflows in this repo — subtitles and the TV layout — work
this way.

**How to brief it**

1. Tell it to read this `README.md` and the `scripts/` folder.
2. State the non-negotiable: **never modify, move or rename the video files**;
   only add `<video>.<lang>.srt` sidecars.
3. Ask it to run `build_sidecars.py` as a **dry run** and show you the plan
   before writing anything.

Most assistants auto-load a project context file, so you can paste the prompt
below (or a copy of this README) into:

| Assistant / tool | Context file it reads |
|---|---|
| opencode | `AGENTS.md` |
| Claude Code | `CLAUDE.md` |
| Cursor | `.cursorrules` or `.cursor/rules/*` |
| GitHub Copilot | `.github/copilot-instructions.md` |
| ChatGPT | Custom Instructions / a Project's "Instructions" |

**Copy/paste handoff prompt**

```text
You are helping me add external subtitles to a video collection so Plex can show
them, WITHOUT modifying any video file.

Repo: <PATH-TO-plexsubro>. Read README.md and the scripts/ folder first.

Hard rules:
- NEVER rename, move, delete or re-encode the video files.
- Only ADD sidecar files named exactly "<video basename>.<lang>.srt" next to each
  video.
- Sidecars must be SubRip .srt, UTF-8 WITHOUT BOM, CRLF line endings.
- Use only the scripts in scripts/ and the Python standard library. Do not
  install packages and do not invent tools.

Task:
1. Videos live in <VIDEO_FOLDER> (collection: <NAME>, language: <LANG>).
2. Obtain source subtitles for that collection (a .zip/.rar/.srt/.ass pack) and
   extract them with "tar -xf <archive> -C <outdir>" (bsdtar reads .zip and .rar).
3. Dry run:
     python scripts/build_sidecars.py --videos "<VIDEO_FOLDER>" --subs "<RAW_DIR>" --lang <LANG>
   Show me the plan. If sources are for several releases, add
   --prefer <regex> (e.g. 2160p, WEB). When the plan looks right, re-run with
   --apply.
4. Validate with "python scripts/verify.py --dir "<VIDEO_FOLDER>" --lang <LANG>"
   and report: items matched, anything unmatched, encoding/BOM issues, and
   confirm that no video file was modified.

If a suitable source subtitle cannot be found, say so explicitly instead of
fabricating subtitles.
```

### Driving the TV-layout workflow

The TV task has the same shape: inspect → propose a mapping → dry run → show the
plan → apply → verify. Keep the hard rules (never touch the originals; only add
links) explicit in the brief.

```text
You are helping me make an existing video collection appear in Plex as a TV show,
WITHOUT modifying, moving, renaming or re-encoding the originals.

Repo: <PATH-TO-plexsubro>. Read README.md and the scripts/ folder first.

Hard rules:
- NEVER rename, move, delete or re-encode the source videos.
- Only ADD a parallel layout of links under the TV root I give you.
- Per-file renames use hard links (same volume, no extra space); whole folders
  use a directory junction (Windows) / symlink. Use only the scripts in scripts/
  and the Python standard library.

Task:
1. Source collection: <SOURCE_FOLDER>. TV root: <TV_ROOT>. Show: <SHOW (YEAR)>.
2. List the filenames. Propose an --episode-regex that captures the episode
   token (supporting ranges like 26-27) and a --seasons split, and confirm the
   split against the ordering Plex will match (TheMovieDB "Aired", or an
   "Absolute" episode group selected in Plex).
3. Dry run:
     python scripts/build_tv_layout.py --target-root "<TV_ROOT>" \
       --show "<SHOW (YEAR)>" --source "<SOURCE_FOLDER>" \
       --episode-regex "<REGEX>" --seasons "<S:FIRST-LAST,...>" --carry-subs
   Show me the plan: seasons, counts, and anything skipped, duplicated or
   missing. Fix the regex/mapping or add --exclude for superseded files, then
   re-run with --apply.
4. Validate with:
     python scripts/verify_tv_layout.py --show "<TV_ROOT>/<SHOW (YEAR)>"
   and report gaps, duplicates and broken links, and confirm that no source file
   was modified.
5. Tell me to add a TV Shows library in Plex pointing at <TV_ROOT> and scan.

If the season split or the numbering cannot be determined, say so explicitly
instead of guessing.
```

An agent can also run the subtitle workflow (`build_sidecars.py`) against either
the originals or the linked layout — a sidecar simply has to match the video's
name in whichever folder Plex reads. For routine additions, `add_movie.py` /
`add_tv.py` link a single downloaded item into a library root with no mapping at
all: hand them one path and a `--library`.

---

## License / attribution

Scripts are provided under the MIT License (see `LICENSE`), use freely. This
repository contains only conversion tooling, not any subtitle text; any
subtitle content you process remains subject to the terms of its original
authors and source.
