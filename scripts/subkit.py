# -*- coding: utf-8 -*-
"""Shared helpers for converting subtitle files to Plex-friendly UTF-8 SRT.

Parsing supports SubRip (.srt), ASS/SSA (.ass/.ssa), SubViewer 2.0 (.sub) and
MicroDVD (.sub, frame based). Decoding tries UTF-8 and falls back to CP1250
(common for legacy Central/Eastern-European subtitles).
"""
import os
import re

VIDEO_EXT = (".mkv", ".mp4", ".avi", ".mov", ".m4v", ".ts", ".webm", ".mpg", ".mpeg")
SUB_EXT = (".srt", ".ass", ".ssa", ".sub")

EP_RE = re.compile(r"[Ss](\d{1,2})[\s._-]*[Ee](\d{1,3})")
ALT_RE = re.compile(r"\b(\d{1,2})x(\d{1,3})\b")

SRT_TC = re.compile(
    r"\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}\s*[^\d]{1,10}?\s*\d{1,2}:\d{2}:\d{2}[.,]\d{1,3}"
)

FALLBACK_ENCODINGS = ("utf-8", "cp1250")


# --------------------------------------------------------------------------- #
# decoding
# --------------------------------------------------------------------------- #
def decode(path, encodings=FALLBACK_ENCODINGS):
    """Read a subtitle file, honour a UTF-8 BOM, and try each encoding in turn."""
    b = open(path, "rb").read()
    if b[:3] == b"\xef\xbb\xbf":
        b = b[3:]
    last = None
    for enc in encodings:
        try:
            return b.decode(enc)
        except UnicodeDecodeError as ex:
            last = ex
    raise last


def normalize_tc(tc):
    """'00:01:25.00' / '00:01:25,000' -> '00:01:25,000'."""
    tc = tc.strip().replace(".", ",")
    m = re.match(r"(\d{1,2}):(\d{2}):(\d{2})[,](\d{1,3})", tc)
    if not m:
        return None
    h, mm, ss, frac = m.groups()
    return f"{int(h):02d}:{mm}:{ss},{(frac + '00')[:3]}"


def clean_body(body):
    body = re.sub(r"\{[^}]*\}", "", body)      # override / MicroDVD tags
    body = re.sub(r"<[^>]+>", "", body)        # html-ish tags
    body = body.replace("\u00a0", " ").strip("\n")
    return body


# --------------------------------------------------------------------------- #
# parsers -> list of (start, end, [text lines])
# --------------------------------------------------------------------------- #
def parse_srt(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    # tolerant of odd arrows: -->, .. >, ->, =>, etc.
    tcpat = re.compile(
        r"^\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*[^\d]{1,10}?(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*$"
    )
    cues, i = [], 0
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        if lines[i].strip().isdigit():
            i += 1
            if i >= len(lines):
                break
        m = tcpat.match(lines[i])
        if not m:
            i += 1
            continue
        start, end = normalize_tc(m.group(1)), normalize_tc(m.group(2))
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() != "":
            buf.append(lines[i].rstrip())
            i += 1
        body = clean_body("\n".join(buf))
        if start and end and body.strip():
            cues.append((start, end, [ln.rstrip() for ln in body.split("\n")]))
    return cues


def ass_tc(tc):
    m = re.match(r"(\d{1,2}):(\d{2}):(\d{2})[.,](\d{1,3})", tc.strip())
    if not m:
        return None
    h, mm, ss, frac = m.groups()
    return f"{int(h):02d}:{mm}:{ss},{(frac + '00')[:3]}"


def parse_ass(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    cues, in_events = [], False
    for line in text.split("\n"):
        if line.strip().startswith("["):
            in_events = line.strip().lower() == "[events]"
            continue
        if not in_events or not line.startswith("Dialogue:"):
            continue
        parts = line.split(",", 9)          # Text is the last field
        if len(parts) < 10:
            continue
        start, end = ass_tc(parts[1]), ass_tc(parts[2])
        body = re.sub(r"\{[^}]*\}", "", parts[9])
        body = body.replace("\\N", "\n").replace("\\n", "\n").replace("\\h", " ")
        body = clean_body(body)
        if start and end and body.strip():
            cues.append((start, end, [ln.rstrip() for ln in body.split("\n")]))
    return cues


def parse_subviewer(text):
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    tcpat = re.compile(
        r"^(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*,\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{1,3})\s*$"
    )
    cues, i = [], 0
    while i < len(lines):
        m = tcpat.match(lines[i].strip())
        if not m:
            i += 1
            continue
        start, end = normalize_tc(m.group(1)), normalize_tc(m.group(2))
        i += 1
        buf = []
        while i < len(lines) and lines[i].strip() != "":
            buf.append(lines[i].rstrip())
            i += 1
        body = clean_body("\n".join(buf).replace("[br]", "\n"))
        if start and end and body.strip():
            cues.append((start, end, [ln.rstrip() for ln in body.split("\n")]))
    return cues


def frame_tc(frame, fps):
    t = max(frame, 0) / fps
    h = int(t // 3600)
    mm = int((t % 3600) // 60)
    ss = t % 60
    return f"{h:02d}:{mm:02d}:{int(ss):02d},{int(round((ss - int(ss)) * 1000)):03d}"


def parse_microdvd(text, fps):
    cues = []
    for m in re.finditer(r"\{(\d+)\}\{(\d+)\}([^\r\n]*)", text):
        start = frame_tc(int(m.group(1)), fps)
        end = frame_tc(int(m.group(2)), fps)
        body = clean_body(m.group(3).replace("|", "\n"))
        if body.strip():
            cues.append((start, end, [ln.rstrip() for ln in body.split("\n")]))
    return cues


def load_cues(path, microdvd_fps=23.976):
    """Auto-detect the format of *path* and return parsed cues."""
    ext = os.path.splitext(path)[1].lower()
    text = decode(path)
    if ext in (".ass", ".ssa"):
        return parse_ass(text)
    if ext == ".sub":
        if text.lstrip().startswith("[INFORMATION]"):
            return parse_subviewer(text)
        if re.match(r"\s*\{\d+\}\{\d+\}", text):
            return parse_microdvd(text, microdvd_fps)
        return parse_subviewer(text)
    if SRT_TC.search(text):
        return parse_srt(text)
    return parse_subviewer(text)


def to_srt(cues):
    out = []
    for n, (s, e, txt) in enumerate(cues, 1):
        out.append(str(n))
        out.append(f"{s} --> {e}")
        out.extend(txt)
        out.append("")
    return "\r\n".join(out) + "\r\n"


# --------------------------------------------------------------------------- #
# matching helpers
# --------------------------------------------------------------------------- #
def episode_key(name):
    m = EP_RE.search(name) or ALT_RE.search(name)
    if not m:
        return None
    return "S%02dE%02d" % (int(m.group(1)), int(m.group(2)))


def tokens(name):
    return set(t for t in re.split(r"[^A-Za-z0-9]+", name.lower()) if t)


def score(candidate, video_name):
    return len(tokens(os.path.basename(candidate)) & tokens(video_name))


def pick(candidates, video_name, prefer=None):
    """Choose the best candidate by release-name token overlap (and --prefer)."""
    pool = candidates
    if prefer:
        pref = [c for c in pool if re.search(prefer, c, re.I)]
        if pref:
            pool = pref
    return max(pool, key=lambda c: (score(c, video_name), -len(c)))


def list_files(folder, exts):
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in files:
            if f.lower().endswith(exts):
                out.append(os.path.join(root, f))
    return out
