# plexsubro

Build **Plex-compatible external subtitle sidecars** for an existing video
collection, without touching the video files. Point it at a folder of videos and
a folder of source subtitles; it writes one `<video>.<lang>.srt` next to each
video. Romanian (`ro`) is the default language, but any language code works.

The tool only *adds* sidecar subtitle files — it never renames, moves, re-encodes
or deletes the videos.

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
   ├─ subkit.py           # shared library: parsers, conversion, matching
   ├─ build_sidecars.py   # pair videos + subs -> <video>.<lang>.srt
   └─ verify.py           # check coverage and sidecar validity
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

## Using this repo with an AI assistant

The tooling is deliberately assistant-agnostic: plain Python, no dependencies,
and this README carries all the domain knowledge. Any coding assistant (ChatGPT,
Claude, Gemini, GitHub Copilot, Cursor, opencode, …) can run the workflow on a
new collection.

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

---

## License / attribution

Scripts are provided under the MIT License (see `LICENSE`), use freely. This
repository contains only conversion tooling, not any subtitle text; any
subtitle content you process remains subject to the terms of its original
authors and source.
