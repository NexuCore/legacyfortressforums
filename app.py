from flask import Flask, request, redirect, url_for, render_template_string, session, jsonify, send_from_directory
from datetime import datetime
from werkzeug.utils import secure_filename
import os, mimetypes, re

app = Flask(__name__)
app.secret_key = "change-this-secret"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024

posts = []
users = {}
user_profiles = {}   # username -> {"avatar": filename_or_None}
next_id = [0]

from markupsafe import Markup, escape

def markup_content(text):
    """Convert text with #hashtags into safe HTML with clickable links."""
    if not text:
        return Markup("")
    parts = []
    for word in text.split(" "):
        # Try to match a hashtag at the start of the word
        m = re.match(r'^(#)([A-Za-z0-9_]+)(.*)', word)
        if m:
            tag = m.group(2).lower()
            rest = escape(m.group(3))
            parts.append(
                Markup('<a class="hashtag" href="/hashtag/{tag}">#{tag}</a>{rest}').format(
                    tag=tag, rest=rest
                )
            )
        else:
            parts.append(escape(word))
    return Markup(" ".join(str(p) for p in parts))

app.jinja_env.globals['markup_content'] = markup_content

def extract_hashtags(text):
    """Return sorted lowercase list of hashtags found in text."""
    if not text:
        return []
    return list({t.lower() for t in re.findall(r'#([A-Za-z0-9_]+)', text)})

def new_id():
    next_id[0] += 1
    return next_id[0]

def find_comment(comments, target_id):
    for c in comments:
        if c["id"] == target_id:
            return c
        found = find_comment(c.get("replies", []), target_id)
        if found:
            return found
    return None

def find_post(post_id):
    return next((p for p in posts if p["id"] == post_id), None)

def make_votable():
    return {"likes": 0, "dislikes": 0, "votes": {}}

def save_file(file):
    if not file or file.filename == "":
        return None
    filename = secure_filename(file.filename)
    uid = str(new_id()) + "_" + filename
    file.save(os.path.join(UPLOAD_FOLDER, uid))
    mime = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return {"filename": uid, "original": filename, "mime": mime}

def file_category(mime):
    if not mime: return "other"
    if mime.startswith("image/"): return "image"
    if mime.startswith("video/"): return "video"
    if mime.startswith("audio/"): return "audio"
    return "other"

def apply_vote(obj, username, val):
    current = obj["votes"].get(username, 0)
    obj["votes"][username] = 0 if current == val else val
    obj["likes"]    = sum(1 for v in obj["votes"].values() if v ==  1)
    obj["dislikes"] = sum(1 for v in obj["votes"].values() if v == -1)
    return {"likes": obj["likes"], "dislikes": obj["dislikes"], "user_vote": obj["votes"].get(username, 0)}

# ── shared CSS ────────────────────────────────────────────────────────────────
BASE_STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323&display=swap" rel="stylesheet">
<style>
:root {
  --dirt:      #7a5230;
  --dirt-dark: #4a2f14;
  --stone:     #6a6a6a;
  --stone-dark:#3a3a3a;
  --grass:     #5d9e2f;
  --grass-top: #7ec850;
  --gold:      #f0c020;
  --torch:     #ff8c00;
  --lce-bg:    #0e0e1a;
  --lce-panel: #0d0d1a;
  --lce-blue:  #4488ff;
  --red:       #cc2200;
  --red-light: #ff4422;
  --pixel:     'Press Start 2P', monospace;
  --vt:        'VT323', monospace;
}
* { box-sizing: border-box; margin: 0; padding: 0; image-rendering: pixelated; }

body {
  font-family: var(--vt);
  background: var(--lce-bg);
  color: #ccc;
  min-height: 100vh;
  overflow-x: hidden;
}
/* grid background */
body::before {
  content: '';
  position: fixed; inset: 0; z-index: -2;
  background-color: #090912;
  background-image:
    repeating-linear-gradient(0deg,  rgba(0,0,0,0.18) 0px, rgba(0,0,0,0.18) 1px, transparent 1px, transparent 16px),
    repeating-linear-gradient(90deg, rgba(0,0,0,0.12) 0px, rgba(0,0,0,0.12) 1px, transparent 1px, transparent 16px);
  background-size: 16px 16px;
}
/* stars */
body::after {
  content: '';
  position: fixed; inset: 0; z-index: -1; pointer-events: none;
  background-image:
    radial-gradient(1px 1px at 8%  12%, rgba(255,255,255,0.55) 0%, transparent 100%),
    radial-gradient(1px 1px at 22% 38%, rgba(255,255,255,0.35) 0%, transparent 100%),
    radial-gradient(1px 1px at 57% 9%,  rgba(255,255,255,0.45) 0%, transparent 100%),
    radial-gradient(1px 1px at 78% 28%, rgba(255,255,255,0.28) 0%, transparent 100%),
    radial-gradient(1px 1px at 43% 68%, rgba(255,255,255,0.38) 0%, transparent 100%),
    radial-gradient(1px 1px at 88% 77%, rgba(255,255,255,0.25) 0%, transparent 100%),
    radial-gradient(1px 1px at 33% 85%, rgba(255,255,255,0.30) 0%, transparent 100%),
    radial-gradient(1px 1px at 65% 55%, rgba(255,255,255,0.22) 0%, transparent 100%);
}

/* ── HERO ── */
.hero {
  position: relative; width: 100%; min-height: 90px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  overflow: hidden; border-bottom: 4px solid #000;
}
.hero-bg {
  position: absolute; inset: 0;
  background: linear-gradient(135deg, #1a2a0a 0%, #0a1a20 50%, #1a0a2a 100%);
}
.hero-overlay {
  position: absolute; inset: 0;
  background: linear-gradient(to bottom, rgba(0,0,0,0.1) 0%, rgba(10,10,30,0.7) 100%);
}
.hero-grass {
  position: absolute; bottom: 0; left: 0; right: 0; height: 10px;
  background: linear-gradient(to bottom, var(--grass-top) 0%, var(--grass) 50%, var(--dirt) 100%);
  border-top: 2px solid #000;
}
.hero-title {
  position: relative; z-index: 2;
  font-family: var(--pixel);
  font-size: clamp(10px, 2.5vw, 16px);
  color: var(--gold);
  text-shadow: 3px 3px 0 #000, -1px -1px 0 rgba(0,0,0,0.8);
  letter-spacing: 2px;
  padding: 18px 20px 22px;
  animation: logobob 3s ease-in-out infinite;
}
@keyframes logobob { 0%,100%{transform:translateY(0)} 50%{transform:translateY(-4px)} }

/* ── TOP NAV BAR ── */
.top {
  background: #000;
  border-bottom: 3px solid var(--grass);
  padding: 0 16px;
  display: flex; align-items: center; justify-content: space-between;
  flex-wrap: wrap; gap: 0;
  min-height: 44px;
}
.top h1 { display: none; } /* title is in hero */
.top-brand {
  font-family: var(--pixel); font-size: 9px; letter-spacing: 1px;
  color: var(--gold); text-decoration: none;
  padding: 12px 0;
}
.auth-bar {
  font-family: var(--vt); font-size: 18px; letter-spacing: 1px;
  display: flex; align-items: center; gap: 12px;
  padding: 8px 0;
}
.auth-bar a { color: #aaa; text-decoration: none; transition: color 0.1s; }
.auth-bar a:hover { color: #fff; }
.auth-bar .nav-username {
  color: var(--gold); font-weight: bold;
  border: 2px solid rgba(240,192,32,0.3);
  padding: 2px 10px;
  background: rgba(240,192,32,0.06);
}
.auth-bar .nav-username:hover { background: rgba(240,192,32,0.12); }
.nav-server-btn {
  font-family: var(--pixel); font-size: 7px; letter-spacing: 1px;
  color: var(--grass-top); text-decoration: none; text-transform: uppercase;
  padding: 7px 14px; margin-left: 10px;
  background: linear-gradient(to bottom, #2a4a10, #1a3008);
  border: 2px solid #000;
  box-shadow: inset 1px 1px 0 rgba(255,255,255,0.15), inset -1px -1px 0 rgba(0,0,0,0.4), 2px 2px 0 #000;
  transition: all 0.08s; display: inline-block; position: relative;
}
.nav-server-btn:hover {
  background: linear-gradient(to bottom, #3a6018, #254010);
  color: #aaff44;
  box-shadow: inset 1px 1px 0 rgba(255,255,255,0.2), 2px 2px 0 #000, 0 0 10px rgba(126,200,80,0.3);
}
.nav-server-btn:active { transform: translate(2px,2px); box-shadow: none; }
.auth-bar .nav-sep { color: #333; }

/* ── DIRT DIVIDER ── */
hr {
  height: 10px; border: none;
  background: repeating-linear-gradient(90deg,
    var(--dirt) 0px, var(--dirt) 16px,
    var(--dirt-dark) 16px, var(--dirt-dark) 32px);
  border-top: 2px solid #000;
  border-bottom: 2px solid #000;
  margin: 20px 0;
}

/* ── MAIN WRAPPER ── */
.main-wrap { max-width: 720px; margin: 0 auto; padding: 20px 16px; }

/* ── LCE PANEL ── */
.lce-panel {
  background: rgba(0,0,0,0.72);
  border: 3px solid #000;
  box-shadow:
    inset 1px 1px 0 rgba(255,255,255,0.10),
    inset -1px -1px 0 rgba(0,0,0,0.55),
    3px 3px 0 #000;
  position: relative; overflow: hidden; margin-bottom: 16px;
}
.lce-panel::before {
  content: '';
  position: absolute; inset: 0; pointer-events: none;
  background-image: repeating-linear-gradient(0deg,
    rgba(255,255,255,0.018) 0px, rgba(255,255,255,0.018) 1px,
    transparent 1px, transparent 8px);
}
.panel-title {
  background: linear-gradient(to bottom, #2a2a4a, #1a1a30);
  border-bottom: 3px solid var(--lce-blue);
  padding: 8px 14px;
  display: flex; align-items: center; gap: 10px;
  font-family: var(--vt); font-size: 20px; letter-spacing: 3px;
  color: #fff; text-transform: uppercase; text-shadow: 1px 1px 0 #000;
}
.panel-body { padding: 14px 16px; }

/* ── PIXEL BUTTON ── */
.px-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 9px 16px; cursor: pointer;
  font-family: var(--pixel); font-size: 8px; letter-spacing: 1px;
  text-transform: uppercase; border: none; outline: none;
  position: relative;
  transition: background 0.08s;
  text-shadow: 1px 1px 0 rgba(0,0,0,0.8);
  box-shadow: inset 2px 2px 0 rgba(255,255,255,0.18), inset -2px -2px 0 rgba(0,0,0,0.4), 3px 3px 0 #000;
  white-space: nowrap;
}
.px-btn:active:not(:disabled) { transform: translate(2px,2px); box-shadow: 1px 1px 0 #000 !important; }
.px-btn:disabled { opacity: 0.35; cursor: not-allowed; }

.px-btn-green {
  background: linear-gradient(to bottom, #4a7a1e, #2d5a0e); color: #aaff44;
}
.px-btn-green:hover:not(:disabled) { background: linear-gradient(to bottom, #5a9a28, #3d7018); }

.px-btn-stone {
  background: linear-gradient(to bottom, #555, #3a3a3a); color: #ddd;
}
.px-btn-stone:hover:not(:disabled) { background: linear-gradient(to bottom, #666, #484848); }

.px-btn-gold {
  background: linear-gradient(to bottom, #5a4800, #3a2e00); color: var(--gold);
}
.px-btn-gold:hover:not(:disabled) { background: linear-gradient(to bottom, #6a5600, #4a3a00); }

.px-btn-red {
  background: linear-gradient(to bottom, #5a1a0a, #3a0a00); color: #ff8866;
}
.px-btn-red:hover:not(:disabled) { background: linear-gradient(to bottom, #7a2a18, #4a1008); }

.px-btn-blue {
  background: linear-gradient(to bottom, #0a1a3a, #05101e); color: var(--lce-blue);
}
.px-btn-blue:hover:not(:disabled) { background: linear-gradient(to bottom, #0d2050, #081530); }

/* ── POST CARD ── */
.post-card {
  background: rgba(0,0,0,0.65);
  border: 3px solid #000;
  box-shadow: inset 1px 1px 0 rgba(255,255,255,0.08), inset -1px -1px 0 rgba(0,0,0,0.5), 3px 3px 0 #000;
  padding: 14px 16px; margin-bottom: 14px;
  transition: border-color 0.15s;
  position: relative;
}
.post-card::before {
  content: ''; position: absolute; inset: 0; pointer-events: none;
  background-image: repeating-linear-gradient(0deg,
    rgba(255,255,255,0.012) 0px, rgba(255,255,255,0.012) 1px, transparent 1px, transparent 8px);
}
.post-card:hover { border-color: #444; box-shadow: inset 1px 1px 0 rgba(255,255,255,0.10), 3px 3px 0 #000; }
.post-title-link { text-decoration: none; color: #ddd; display: block; }

/* ── META LINE ── */
.meta {
  font-family: var(--vt); font-size: 16px; color: #666;
  margin-bottom: 8px; display: flex; align-items: center; gap: 0; flex-wrap: wrap;
}
.meta a.author-link {
  color: var(--gold); text-decoration: none; letter-spacing: 1px;
  text-shadow: 1px 1px 0 #000;
}
.meta a.author-link:hover { color: #fff; text-decoration: underline; }
.meta-sep { color: #333; margin: 0 6px; }
.meta-time { color: #444; font-size: 14px; }

p { margin: 6px 0; font-family: var(--vt); font-size: 17px; color: #bbb; line-height: 1.6; }

/* ── MEDIA ── */
.post-media img   { max-width: 100%; max-height: 280px; width: auto; margin-top: 10px; display: block;
  border: 3px solid #000; box-shadow: 3px 3px 0 #000; }
.post-media video { max-width: 100%; max-height: 280px; margin-top: 10px; display: block;
  border: 3px solid #000; box-shadow: 3px 3px 0 #000; }
.post-media audio { width: 100%; margin-top: 10px; }
.reply-media img  { max-width: 100%; max-height: 160px; width: auto; margin-top: 6px; display: block;
  border: 2px solid #000; box-shadow: 2px 2px 0 #000; }
.reply-media video{ max-width: 100%; max-height: 160px; margin-top: 6px; display: block;
  border: 2px solid #000; box-shadow: 2px 2px 0 #000; }
.reply-media audio{ width: 100%; margin-top: 6px; }

.file-download {
  display: inline-flex; align-items: center; gap: 8px; margin-top: 10px;
  padding: 6px 14px; text-decoration: none; font-family: var(--vt); font-size: 15px;
  color: var(--lce-blue);
  background: rgba(68,136,255,0.06); border: 2px solid #1a2a4a;
  box-shadow: 2px 2px 0 #000;
}
.file-download:hover { background: rgba(68,136,255,0.14); border-color: var(--lce-blue); }
.file-download svg { width: 14px; height: 14px; fill: currentColor; }

/* ── FORM ROW ── */
.form-row { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
textarea {
  width: 100%; padding: 10px 12px;
  font-family: var(--vt); font-size: 17px; color: #ccc;
  background: #050510; border: 3px solid #000;
  box-shadow: inset 2px 2px 0 rgba(0,0,0,0.5), inset 1px 1px 0 rgba(255,255,255,0.05);
  resize: vertical; outline: none;
}
textarea:focus { border-color: var(--lce-blue); box-shadow: inset 2px 2px 0 rgba(0,0,0,0.5), 0 0 0 1px var(--lce-blue); }
textarea::placeholder { color: #333; }

.file-label {
  display: inline-flex; align-items: center; gap: 6px; cursor: pointer;
  font-family: var(--pixel); font-size: 7px; letter-spacing: 1px; color: #888;
  background: #0a0a18; border: 2px solid #1a1a3a; padding: 0 12px; height: 36px;
  white-space: nowrap; box-shadow: 2px 2px 0 #000;
}
.file-label:hover { color: #ccc; border-color: #2a2a5a; }
.file-label svg { width: 13px; height: 13px; fill: none; stroke: currentColor; stroke-width: 2;
    stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.chosen-file { font-family: var(--vt); font-size: 14px; color: #445; max-width: 160px;
    overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.form-row button[type=submit] { height: 36px; padding: 0 18px; }

/* ── VOTE BAR ── */
.vote-bar { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.vote-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px; cursor: pointer; min-height: 32px;
  font-family: var(--vt); font-size: 16px;
  background: rgba(0,0,0,0.5); border: 2px solid #2a2a2a;
  color: #666; transition: all 0.1s;
  box-shadow: 2px 2px 0 #000;
}
.vote-btn:hover { background: rgba(255,255,255,0.05); border-color: #444; color: #aaa; }
.vote-btn.liked   { border-color: var(--grass); color: var(--grass-top); background: rgba(93,158,47,0.12);
  box-shadow: 2px 2px 0 #000, 0 0 8px rgba(126,200,80,0.25); }
.vote-btn.disliked{ border-color: var(--red); color: var(--red-light); background: rgba(204,34,0,0.1);
  box-shadow: 2px 2px 0 #000, 0 0 8px rgba(255,68,34,0.2); }
.vote-btn svg { width: 13px; height: 13px; fill: currentColor; }

.reply-toggle {
  display: inline-flex; align-items: center; gap: 5px; cursor: pointer;
  padding: 5px 10px; min-height: 32px;
  font-family: var(--vt); font-size: 16px; color: #555;
  background: transparent; border: 2px solid transparent;
  box-shadow: none;
}
.reply-toggle:hover { color: var(--lce-blue); border-color: #1a2a4a; background: rgba(68,136,255,0.07); box-shadow: 2px 2px 0 #000; }
.reply-toggle svg { width: 13px; height: 13px; fill: currentColor; }
.reply-count { font-family: var(--vt); font-size: 16px; color: #445; text-decoration: none;
    display: inline-flex; align-items: center; gap: 5px; padding: 5px 6px; }
.reply-count:hover { color: #aaa; }

/* ── COMMENT / THREAD ── */
.reply-form { display: none; margin-top: 10px; }
.comment {
  margin-top: 12px; padding-left: 14px;
  border-left: 3px solid #1a1a2e;
  background: rgba(68,136,255,0.02);
}
.comment:hover { border-left-color: #2a2a5a; }
.guest-note { font-family: var(--vt); font-size: 16px; color: #445; letter-spacing: 1px; }
.back-link { font-family: var(--vt); font-size: 17px; color: #446; text-decoration: none;
    display: inline-block; margin-bottom: 14px; letter-spacing: 1px; }
.back-link:hover { color: var(--lce-blue); }
.section-title {
  font-family: var(--vt); font-size: 20px; letter-spacing: 3px; color: #aaa;
  text-transform: uppercase; margin: 18px 0 10px;
  padding-bottom: 6px; border-bottom: 2px solid #1a1a2e;
}

/* ── PROFILE ── */
.profile-header { display: flex; align-items: center; gap: 16px; margin-bottom: 18px; }
.profile-avatar {
  width: 64px; height: 64px; flex-shrink: 0;
  border: 3px solid #000; box-shadow: 3px 3px 0 #000;
  background: linear-gradient(135deg, #1a2a4a, #0d1520);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--pixel); font-size: 22px; color: var(--gold);
  image-rendering: pixelated;
}
.profile-name { font-family: var(--pixel); font-size: 13px; color: var(--gold);
    text-shadow: 2px 2px 0 #000; letter-spacing: 2px; margin-bottom: 8px; }
.profile-stats { display: flex; gap: 20px; font-family: var(--vt); font-size: 17px; color: #555; }
.profile-stats span strong { color: #aaa; }
.profile-post-card {
  background: rgba(0,0,0,0.55); border: 3px solid #000;
  box-shadow: inset 1px 1px 0 rgba(255,255,255,0.06), 3px 3px 0 #000;
  padding: 12px 14px; margin-bottom: 12px; transition: border-color 0.15s;
}
.profile-post-card:hover { border-color: #333; }

/* ── MINI AVATAR ── */
.mini-avatar {
  width: 22px; height: 22px; object-fit: cover; vertical-align: middle; margin-right: 5px;
  border: 2px solid #000; box-shadow: 1px 1px 0 #000; flex-shrink: 0;
}
.mini-avatar-placeholder {
  width: 22px; height: 22px; flex-shrink: 0; vertical-align: middle; margin-right: 5px;
  display: inline-flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1a2a4a, #0d1520);
  border: 2px solid #000; box-shadow: 1px 1px 0 #000;
  font-family: var(--pixel); font-size: 8px; color: var(--gold);
}

/* ── LOGIN / REGISTER ── */
.auth-box {
  max-width: 400px; margin: 60px auto; padding: 24px;
  background: rgba(0,0,0,0.72); border: 3px solid #000;
  box-shadow: inset 1px 1px 0 rgba(255,255,255,0.08), 4px 4px 0 #000;
}
.auth-box h1 {
  font-family: var(--pixel); font-size: 13px; color: var(--gold);
  text-shadow: 2px 2px 0 #000; letter-spacing: 2px; margin-bottom: 18px;
}
.auth-input {
  width: 100%; padding: 10px 12px; margin-bottom: 10px;
  font-family: var(--vt); font-size: 18px; color: #ccc;
  background: #050510; border: 3px solid #000;
  box-shadow: inset 2px 2px 0 rgba(0,0,0,0.5); outline: none;
}
.auth-input:focus { border-color: var(--lce-blue); }
.auth-input::placeholder { color: #333; }
.auth-error { font-family: var(--vt); font-size: 16px; color: var(--red-light);
    border: 2px solid rgba(204,34,0,0.3); background: rgba(204,34,0,0.07);
    padding: 6px 10px; margin-bottom: 12px; letter-spacing: 1px; }
.auth-links { font-family: var(--vt); font-size: 17px; color: #446; margin-top: 14px; line-height: 2; }
.auth-links a { color: var(--lce-blue); text-decoration: none; }
.auth-links a:hover { color: #fff; }

/* ── NO POSTS ── */
.no-posts { font-family: var(--vt); font-size: 18px; color: #333;
    letter-spacing: 2px; padding: 30px 0; text-align: center; }

/* ── HASHTAGS ── */
.hashtag {
  display: inline-block; font-family: var(--vt); font-size: 15px;
  color: var(--lce-blue); text-decoration: none; letter-spacing: 1px;
  padding: 1px 6px; margin: 0 1px;
  background: rgba(68,136,255,0.08); border: 1px solid rgba(68,136,255,0.25);
  box-shadow: 1px 1px 0 #000; transition: all 0.1s;
}
.hashtag:hover { background: rgba(68,136,255,0.18); border-color: var(--lce-blue); color: #fff; }

.hashtag-pill {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--vt); font-size: 16px;
  color: var(--lce-blue); text-decoration: none;
  padding: 4px 12px; margin: 3px 4px 3px 0;
  background: rgba(68,136,255,0.07); border: 2px solid #1a2a4a;
  box-shadow: 2px 2px 0 #000; transition: all 0.1s;
}
.hashtag-pill:hover { background: rgba(68,136,255,0.16); border-color: var(--lce-blue); color: #fff; }
.hashtag-pill .pill-count {
  font-family: var(--pixel); font-size: 7px; color: #446;
  background: #050510; padding: 2px 5px; border: 1px solid #1a1a3a;
}

.hashtag-page-title {
  font-family: var(--pixel); font-size: clamp(10px, 2vw, 14px);
  color: var(--lce-blue); text-shadow: 2px 2px 0 #000, 0 0 12px rgba(68,136,255,0.4);
  letter-spacing: 2px; margin-bottom: 4px;
}
.hashtag-page-sub {
  font-family: var(--vt); font-size: 18px; color: #446; letter-spacing: 2px;
}
.tags-cloud { display: flex; flex-wrap: wrap; gap: 0; padding: 6px 0 2px; }

/* ── RESPONSIVE ── */
@media (max-width: 540px) {
  .hero-title { font-size: 9px; }
  .post-card { padding: 10px 12px; }
  .comment { padding-left: 8px; }
  .panel-title { font-size: 16px; }
  .auth-bar { font-size: 15px; }
}
</style>
"""

CLIP_SVG = '<svg viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66L9.41 17.41a2 2 0 0 1-2.83-2.83l8.49-8.48"/></svg>'
UP_SVG   = '<svg viewBox="0 0 24 24"><path d="M12 4l8 8H4z"/></svg>'
DOWN_SVG = '<svg viewBox="0 0 24 24"><path d="M12 20l-8-8h16z"/></svg>'
REPLY_SVG= '<svg viewBox="0 0 24 24"><path d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z"/></svg>'
DL_SVG   = '<svg viewBox="0 0 24 24"><path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/></svg>'

# ── hashtag macro ─────────────────────────────────────────────────────────────
HASHTAG_MACRO = """
{% macro hashtag_chips(tags) %}
  {% if tags %}
    <div style="display:flex;flex-wrap:wrap;gap:0;margin-top:8px;">
      {% for tag in tags %}
        <a class="hashtag" href="/hashtag/{{ tag }}">#{{ tag }}</a>
      {% endfor %}
    </div>
  {% endif %}
{% endmacro %}
"""

# ── avatar macro ─────────────────────────────────────────────────────────────
AVATAR_MACRO = """
{% macro mini_avatar(uname) %}
  {% set av = get_avatar_url(uname) %}
  {% if av %}
    <img class="mini-avatar" src="{{ av }}" alt="{{ uname }}">
  {% else %}
    <span class="mini-avatar-placeholder">{{ uname[0].upper() }}</span>
  {% endif %}
{% endmacro %}
"""

# ── attachment renderer ───────────────────────────────────────────────────────
ATTACH_MACRO = """
{% macro render_attachment(att, size_class) %}
{% if att %}
  {% set cat = file_category(att.mime) %}
  <div class="{{ size_class }}">
  {% if cat == 'image' %}
    <img src="/uploads/{{ att.filename }}" alt="{{ att.original }}">
  {% elif cat == 'video' %}
    <video controls><source src="/uploads/{{ att.filename }}" type="{{ att.mime }}"></video>
  {% elif cat == 'audio' %}
    <audio controls><source src="/uploads/{{ att.filename }}" type="{{ att.mime }}"></audio>
  {% else %}
    <a class="file-download" href="/uploads/{{ att.filename }}" download="{{ att.original }}">
      """ + DL_SVG + """ {{ att.original }}
    </a>
  {% endif %}
  </div>
{% endif %}
{% endmacro %}
"""

# ── comment macro (used on thread page) ──────────────────────────────────────
COMMENT_MACRO = HASHTAG_MACRO + AVATAR_MACRO + ATTACH_MACRO + """
{% macro render_comment(comment, username) %}
<div class="comment" id="comment-{{ comment.id }}">
  <div class="meta" style="display:flex;align-items:center;gap:0">{{ mini_avatar(comment.author) }}<a class="author-link" href="/profile/{{ comment.author }}">{{ comment.author }}</a>&nbsp;&mdash; {{ comment.time }}</div>
  {% if comment.content %}<p>{{ markup_content(comment.content) }}</p>{% endif %}
  {{ hashtag_chips(comment.hashtags) }}
  {{ render_attachment(comment.attachment, 'reply-media') }}

  <div class="vote-bar">
    {% set uv = comment.votes.get(username, 0) if username else 0 %}
    <button class="vote-btn {% if uv==1 %}liked{% endif %}"
      {% if username %}onclick="voteComment({{ comment.id }}, 1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + UP_SVG + """ <span>{{ comment.likes }}</span>
    </button>
    <button class="vote-btn {% if uv==-1 %}disliked{% endif %}"
      {% if username %}onclick="voteComment({{ comment.id }}, -1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + DOWN_SVG + """ <span>{{ comment.dislikes }}</span>
    </button>
    {% if username %}
    <button class="reply-toggle" onclick="toggleForm('rf-{{ comment.id }}')">
      """ + REPLY_SVG + """ Reply
    </button>
    {% endif %}
  </div>

  {% if username %}
  <div class="reply-form" id="rf-{{ comment.id }}">
    <form method="POST" action="/reply/{{ comment.post_id }}/{{ comment.id }}" enctype="multipart/form-data">
      <textarea name="content" placeholder="Write a reply... (Ctrl+V to paste image)"></textarea>
      <div class="form-row">
        <label class="file-label">""" + CLIP_SVG + """Attach file
          <input type="file" name="attachment" style="display:none" onchange="showFilename(this)">
        </label>
        <span class="chosen-file"></span>
        <button type="submit" class="px-btn px-btn-stone">&#9658; Reply</button>
      </div>
    </form>
  </div>
  {% endif %}

  {% if comment.replies %}
  {% for child in comment.replies %}{{ render_comment(child, username) }}{% endfor %}
  {% endif %}
</div>
{% endmacro %}
"""

# ── shared JS ─────────────────────────────────────────────────────────────────
BASE_JS = """
<script>
function toggleForm(id) {
  var el = document.getElementById(id);
  el.style.display = el.style.display === 'block' ? 'none' : 'block';
}
function showFilename(input) {
  var span = input.closest('.form-row').querySelector('.chosen-file');
  span.textContent = input.files[0] ? input.files[0].name : '';
}
function setupPaste(textarea) {
  textarea.addEventListener('paste', function(e) {
    var items = (e.clipboardData || e.originalEvent.clipboardData).items;
    for (var i = 0; i < items.length; i++) {
      if (items[i].kind === 'file') {
        var file = items[i].getAsFile();
        var form = textarea.closest('form');
        var fileInput = form.querySelector('input[type="file"]');
        var dt = new DataTransfer();
        dt.items.add(file);
        fileInput.files = dt.files;
        var span = form.querySelector('.chosen-file');
        if (span) span.textContent = '📋 ' + (file.name || 'pasted-file');
        e.preventDefault();
        break;
      }
    }
  });
}
document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('textarea').forEach(setupPaste);
});
function applyVote(bar, data) {
  var btns = bar.querySelectorAll('.vote-btn');
  btns[0].classList.toggle('liked',    data.user_vote ===  1);
  btns[1].classList.toggle('disliked', data.user_vote === -1);
  btns[0].querySelector('span').textContent = data.likes;
  btns[1].querySelector('span').textContent = data.dislikes;
}
function votePost(postId, val, btn) {
  fetch('/vote/post/' + postId + '?v=' + val, {method:'POST'})
    .then(r=>r.json()).then(data=>{ if(!data.error) applyVote(btn.closest('.vote-bar'), data); });
}
function voteComment(commentId, val, btn) {
  fetch('/vote/comment/' + commentId + '?v=' + val, {method:'POST'})
    .then(r=>r.json()).then(data=>{ if(!data.error) applyVote(btn.closest('.vote-bar'), data); });
}
</script>
"""

# ── nav bar ───────────────────────────────────────────────────────────────────
NAV = """
<div class="hero">
  <div class="hero-bg"></div>
  <div class="hero-overlay"></div>
  <div class="hero-title">&#9670; Legacy Fortress Forum &#9670;</div>
  <div class="hero-grass"></div>
</div>
<div class="top">
  <div style="display:flex;align-items:center;gap:0;">
    <a class="top-brand" href="/">&#9658; Forum</a>
    <a href="http://26.187.165.224:8080/" target="_blank" class="nav-server-btn">&#9670; LCE Server</a>
  </div>
  <span class="auth-bar">
    {% if username %}
      <a class="nav-username" href="/profile/{{ username }}">{{ username }}</a>
      <span class="nav-sep">&mdash;</span>
      <a href="/logout">Logout</a>
    {% else %}
      <a href="/login">Login</a>
      <span class="nav-sep">&mdash;</span>
      <a href="/register">Register</a>
    {% endif %}
  </span>
</div>
"""

# ── INDEX page ────────────────────────────────────────────────────────────────
INDEX_TEMPLATE = HASHTAG_MACRO + AVATAR_MACRO + """<!DOCTYPE html>
<html><head><title>Legacy Fortress Forum</title>""" + BASE_STYLE + """</head><body>
""" + NAV + """
<div class="main-wrap">

{% if username %}
<div class="lce-panel">
  <div class="panel-title">&#9654;&nbsp; New Post</div>
  <div class="panel-body">
    <form method="POST" action="/post" enctype="multipart/form-data">
      <textarea name="content" placeholder="What's on your mind? Use #hashtags to tag your post. You can also paste an image with Ctrl+V / Cmd+V." style="height:80px"></textarea>
      <div class="form-row">
        <label class="file-label">""" + CLIP_SVG + """&nbsp;Attach
          <input type="file" name="attachment" style="display:none" onchange="showFilename(this)">
        </label>
        <span class="chosen-file"></span>
        <button type="submit" class="px-btn px-btn-green">&#9658; Post</button>
      </div>
    </form>
  </div>
</div>
{% else %}
<div class="lce-panel">
  <div class="panel-body">
    <span class="guest-note">&#9670; <a href="/login" style="color:var(--lce-blue)">Log in</a> or <a href="/register" style="color:var(--lce-blue)">register</a> to post.</span>
  </div>
</div>
{% endif %}

{% if trending_tags %}
<div class="lce-panel">
  <div class="panel-title">&#9670;&nbsp; Trending Hashtags</div>
  <div class="panel-body" style="padding:10px 14px;">
    <div class="tags-cloud">
      {% for tag, count in trending_tags %}
        <a class="hashtag-pill" href="/hashtag/{{ tag }}">
          #{{ tag }}<span class="pill-count">{{ count }}</span>
        </a>
      {% endfor %}
    </div>
  </div>
</div>
{% endif %}

<hr>

{% for post in posts %}
<div class="post-card">
  <a class="post-title-link" href="/post/{{ post.id }}">
    <div class="meta">{{ mini_avatar(post.author) }}<a class="author-link" href="/profile/{{ post.author }}" onclick="event.stopPropagation()">{{ post.author }}</a><span class="meta-sep">&mdash;</span><span class="meta-time">{{ post.time }}</span></div>
    {% if post.content %}<p>{{ markup_content(post.content) }}</p>{% endif %}
    {% if post.attachment %}
      {% set cat = file_category(post.attachment.mime) %}
      <div class="post-media">
      {% if cat == 'image' %}<img src="/uploads/{{ post.attachment.filename }}" alt="{{ post.attachment.original }}">
      {% elif cat == 'video' %}<video><source src="/uploads/{{ post.attachment.filename }}" type="{{ post.attachment.mime }}"></video>
      {% elif cat == 'audio' %}<audio controls><source src="/uploads/{{ post.attachment.filename }}" type="{{ post.attachment.mime }}"></audio>
      {% else %}<span class="file-download">""" + DL_SVG + """ {{ post.attachment.original }}</span>{% endif %}
      </div>
    {% endif %}
  </a>
  {{ hashtag_chips(post.hashtags) }}
  <div class="vote-bar">
    {% set uv = post.votes.get(username, 0) if username else 0 %}
    <button class="vote-btn {% if uv==1 %}liked{% endif %}"
      {% if username %}onclick="event.stopPropagation();votePost({{ post.id }}, 1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + UP_SVG + """ <span>{{ post.likes }}</span>
    </button>
    <button class="vote-btn {% if uv==-1 %}disliked{% endif %}"
      {% if username %}onclick="event.stopPropagation();votePost({{ post.id }}, -1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + DOWN_SVG + """ <span>{{ post.dislikes }}</span>
    </button>
    <a href="/post/{{ post.id }}" class="reply-count">
      """ + REPLY_SVG.replace('<svg', '<svg style="width:13px;height:13px;fill:currentColor;vertical-align:middle"') + """
      {{ post.reply_count }} repl{{ 'y' if post.reply_count == 1 else 'ies' }}
    </a>
  </div>
</div>
{% else %}
<div class="no-posts">&#9670; No posts yet. Be the first! &#9670;</div>
{% endfor %}

</div>
""" + BASE_JS + """</body></html>
"""

# ── THREAD page ───────────────────────────────────────────────────────────────
THREAD_TEMPLATE = COMMENT_MACRO + """<!DOCTYPE html>
<html><head><title>Post #{{ post.id }}</title>""" + BASE_STYLE + """</head><body>
""" + NAV + """
<div class="main-wrap">

<a class="back-link" href="/">&#9668; Back to Posts</a>

<div class="post-card">
  <div class="meta">{{ mini_avatar(post.author) }}<a class="author-link" href="/profile/{{ post.author }}">{{ post.author }}</a><span class="meta-sep">&mdash;</span><span class="meta-time">{{ post.time }}</span></div>
  {% if post.content %}<p>{{ markup_content(post.content) }}</p>{% endif %}
  {{ hashtag_chips(post.hashtags) }}
  {{ render_attachment(post.attachment, 'post-media') }}
  <div class="vote-bar">
    {% set uv = post.votes.get(username, 0) if username else 0 %}
    <button class="vote-btn {% if uv==1 %}liked{% endif %}"
      {% if username %}onclick="votePost({{ post.id }}, 1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + UP_SVG + """ <span>{{ post.likes }}</span>
    </button>
    <button class="vote-btn {% if uv==-1 %}disliked{% endif %}"
      {% if username %}onclick="votePost({{ post.id }}, -1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + DOWN_SVG + """ <span>{{ post.dislikes }}</span>
    </button>
  </div>
</div>

<div class="section-title">&#9670; Replies</div>

{% if username %}
<div class="lce-panel" style="margin-bottom:16px">
  <div class="panel-body">
    <form method="POST" action="/reply/{{ post.id }}/0" enctype="multipart/form-data">
      <textarea name="content" placeholder="Write a reply... (Ctrl+V / Cmd+V to paste an image)" style="height:60px"></textarea>
      <div class="form-row">
        <label class="file-label">""" + CLIP_SVG + """&nbsp;Attach
          <input type="file" name="attachment" style="display:none" onchange="showFilename(this)">
        </label>
        <span class="chosen-file"></span>
        <button type="submit" class="px-btn px-btn-stone">&#9658; Reply</button>
      </div>
    </form>
  </div>
</div>
{% else %}
<p class="guest-note" style="margin-bottom:16px">&#9670; <a href="/login" style="color:var(--lce-blue)">Log in</a> to reply.</p>
{% endif %}

{% if post.replies %}
  {% for reply in post.replies %}{{ render_comment(reply, username) }}{% endfor %}
{% else %}
  <div class="no-posts">&#9670; No replies yet.</div>
{% endif %}

</div>
""" + BASE_JS + """</body></html>
"""

LOGIN_TEMPLATE = """<!DOCTYPE html>
<html><head><title>{{ title }} — Legacy Fortress</title>""" + BASE_STYLE + """</head><body>
""" + NAV + """
<div class="main-wrap">
<div class="auth-box">
  <h1>&#9670; {{ title }}</h1>
  {% if error %}<div class="auth-error">&#9888; {{ error }}</div>{% endif %}
  <form method="POST">
    <input class="auth-input" type="text" name="username" placeholder="Username" required autocomplete="username"><br>
    <input class="auth-input" type="password" name="password" placeholder="Password" required autocomplete="current-password"><br>
    <button type="submit" class="px-btn px-btn-green" style="width:100%;justify-content:center;margin-top:4px">&#9658; {{ title }}</button>
  </form>
  <div class="auth-links">
    {% if title == "Login" %}<a href="/register">No account? Register &rsaquo;</a><br>
    {% else %}<a href="/login">Already have an account? Login &rsaquo;</a><br>{% endif %}
    <a href="/">&#9668; Back to Forum</a>
  </div>
</div>
</div></body></html>
"""

# ── helpers ───────────────────────────────────────────────────────────────────
def count_replies(replies):
    total = 0
    for r in replies:
        total += 1 + count_replies(r.get("replies", []))
    return total

# ── routes ────────────────────────────────────────────────────────────────────
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

@app.route("/")
def index():
    username = session.get("username")
    feed = list(reversed(posts))
    for p in feed:
        p["reply_count"] = count_replies(p["replies"])
    return render_template_string(INDEX_TEMPLATE, posts=feed,
                                   username=username, file_category=file_category,
                                   get_avatar_url=get_avatar_url,
                                   trending_tags=get_all_tags()[:12])

@app.route("/post/<int:post_id>")
def view_post(post_id):
    post = find_post(post_id)
    if not post:
        return "Post not found", 404
    username = session.get("username")
    return render_template_string(THREAD_TEMPLATE, post=post,
                                   username=username, file_category=file_category,
                                   get_avatar_url=get_avatar_url)

@app.route("/post", methods=["POST"])
def create_post():
    if "username" not in session:
        return redirect(url_for("login"))
    content = request.form.get("content", "").strip()
    attachment = save_file(request.files.get("attachment"))
    if content or attachment:
        posts.append({
            "id": new_id(), "author": session["username"],
            "content": content, "time": datetime.now().strftime("%b %d, %Y %H:%M"),
            "attachment": attachment, "replies": [],
            "hashtags": extract_hashtags(content),
            **make_votable()
        })
    return redirect(url_for("index"))

@app.route("/reply/<int:post_id>/<int:parent_id>", methods=["POST"])
def reply(post_id, parent_id):
    if "username" not in session:
        return redirect(url_for("login"))
    content = request.form.get("content", "").strip()
    attachment = save_file(request.files.get("attachment"))
    post = find_post(post_id)
    if not post or (not content and not attachment):
        return redirect(url_for("view_post", post_id=post_id))
    new_reply = {
        "id": new_id(), "post_id": post_id,
        "author": session["username"], "content": content,
        "time": datetime.now().strftime("%b %d, %Y %H:%M"),
        "attachment": attachment, "replies": [],
        "hashtags": extract_hashtags(content),
        **make_votable()
    }
    if parent_id == 0:
        post["replies"].append(new_reply)
    else:
        parent = find_comment(post["replies"], parent_id)
        if parent:
            parent["replies"].append(new_reply)
    return redirect(url_for("view_post", post_id=post_id))

@app.route("/vote/post/<int:post_id>", methods=["POST"])
def vote_post(post_id):
    if "username" not in session: return jsonify({"error": "not logged in"})
    val = int(request.args.get("v", 0))
    if val not in (1, -1): return jsonify({"error": "invalid"})
    post = find_post(post_id)
    if not post: return jsonify({"error": "not found"})
    return jsonify(apply_vote(post, session["username"], val))

@app.route("/vote/comment/<int:comment_id>", methods=["POST"])
def vote_comment(comment_id):
    if "username" not in session: return jsonify({"error": "not logged in"})
    val = int(request.args.get("v", 0))
    if val not in (1, -1): return jsonify({"error": "invalid"})
    for post in posts:
        comment = find_comment(post["replies"], comment_id)
        if comment:
            return jsonify(apply_vote(comment, session["username"], val))
    return jsonify({"error": "not found"})

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if username in users and users[username] == password:
            session["username"] = username
            return redirect(url_for("index"))
        error = "Invalid username or password."
    return render_template_string(LOGIN_TEMPLATE, title="Login", error=error)

@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            error = "Username and password are required."
        elif username in users:
            error = "Username already taken."
        else:
            users[username] = password
            user_profiles[username] = {"avatar": None}
            session["username"] = username
            return redirect(url_for("index"))
    return render_template_string(LOGIN_TEMPLATE, title="Register", error=error)

@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect(url_for("index"))

PROFILE_TEMPLATE = AVATAR_MACRO + """<!DOCTYPE html>
<html><head><title>{{ profile_user }} — Legacy Fortress</title>""" + BASE_STYLE + """</head><body>
""" + NAV + """
<div class="main-wrap">

<a class="back-link" href="/">&#9668; Back to Posts</a>

<div class="lce-panel">
  <div class="panel-title">&#9670;&nbsp; Player Profile</div>
  <div class="panel-body">
    <div class="profile-header">
      <div style="position:relative;flex-shrink:0;">
        {% if avatar_url %}
          <img src="{{ avatar_url }}" class="profile-avatar" style="object-fit:cover;padding:0;">
        {% else %}
          <div class="profile-avatar">{{ profile_user[0].upper() }}</div>
        {% endif %}
        {% if username == profile_user %}
        <form method="POST" action="/profile/{{ profile_user }}/upload_avatar"
            enctype="multipart/form-data" id="avatar-form">
          <label title="Change profile picture" style="position:absolute;bottom:-4px;right:-4px;width:22px;height:22px;
              background:#0a0a18;border:2px solid #1a1a3a;cursor:pointer;
              display:flex;align-items:center;justify-content:center;box-shadow:2px 2px 0 #000;">
            <svg viewBox="0 0 24 24" style="width:11px;height:11px;fill:none;stroke:var(--gold);stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round;pointer-events:none">
              <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
            </svg>
            <input type="file" name="avatar" accept="image/*" style="position:absolute;opacity:0;width:1px;height:1px;"
              onchange="document.getElementById('avatar-form').submit()">
          </label>
        </form>
        {% endif %}
      </div>
      <div>
        <div class="profile-name">{{ profile_user }}</div>
        <div class="profile-stats">
          <span><strong>{{ user_posts|length }}</strong> post{{ 's' if user_posts|length != 1 else '' }}</span>
          <span><strong>{{ reply_count }}</strong> repl{{ 'ies' if reply_count != 1 else 'y' }}</span>
        </div>
      </div>
    </div>
  </div>
</div>

<div class="section-title">&#9670; Posts by {{ profile_user }}</div>

{% if user_posts %}
  {% for post in user_posts %}
  <div class="profile-post-card">
    <div class="meta">{{ mini_avatar(post.author) }}<a class="author-link" href="/profile/{{ post.author }}">{{ post.author }}</a><span class="meta-sep">&mdash;</span><span class="meta-time">{{ post.time }}</span></div>
    <a href="/post/{{ post.id }}" style="text-decoration:none;display:block;">
      {% if post.content %}<p>{{ post.content }}</p>{% endif %}
      {% if post.attachment %}
        {% set cat = file_category(post.attachment.mime) %}
        <div class="post-media">
        {% if cat == 'image' %}<img src="/uploads/{{ post.attachment.filename }}" alt="{{ post.attachment.original }}">
        {% elif cat == 'video' %}<video><source src="/uploads/{{ post.attachment.filename }}" type="{{ post.attachment.mime }}"></video>
        {% else %}<span style="font-family:var(--vt);font-size:15px;color:#446;">&#128206; {{ post.attachment.original }}</span>{% endif %}
        </div>
      {% endif %}
    </a>
    <div class="vote-bar" style="margin-top:8px">
      {% set uv = post.votes.get(username, 0) if username else 0 %}
      <button class="vote-btn {% if uv==1 %}liked{% endif %}"
        {% if username %}onclick="votePost({{ post.id }}, 1, this)"{% endif %}
        {% if not username %}title="Log in to vote"{% endif %}>
        """ + UP_SVG + """ <span>{{ post.likes }}</span>
      </button>
      <button class="vote-btn {% if uv==-1 %}disliked{% endif %}"
        {% if username %}onclick="votePost({{ post.id }}, -1, this)"{% endif %}
        {% if not username %}title="Log in to vote"{% endif %}>
        """ + DOWN_SVG + """ <span>{{ post.dislikes }}</span>
      </button>
      <a href="/post/{{ post.id }}" style="font-family:var(--vt);font-size:16px;color:#445;text-decoration:none;display:inline-flex;align-items:center;gap:5px;padding:5px 6px;">
        """ + REPLY_SVG.replace('<svg', '<svg style="width:13px;height:13px;fill:currentColor"') + """
        {{ post.reply_count }} repl{{ 'y' if post.reply_count == 1 else 'ies' }}
      </a>
    </div>
  </div>
  {% endfor %}
{% else %}
  <div class="no-posts">&#9670; No posts yet.</div>
{% endif %}

</div>
""" + BASE_JS + """</body></html>
"""

@app.route("/profile/<username>")
def view_profile(username):
    if username not in users:
        return "User not found", 404
    current_user = session.get("username")
    user_posts = list(reversed([p for p in posts if p["author"] == username]))
    for p in user_posts:
        p["reply_count"] = count_replies(p["replies"])

    def count_user_replies(replies):
        total = 0
        for r in replies:
            if r["author"] == username:
                total += 1
            total += count_user_replies(r.get("replies", []))
        return total

    reply_count = sum(count_user_replies(p["replies"]) for p in posts)
    avatar_url = get_avatar_url(username)
    return render_template_string(PROFILE_TEMPLATE,
        profile_user=username, username=current_user,
        user_posts=user_posts, reply_count=reply_count,
        file_category=file_category, avatar_url=avatar_url,
        get_avatar_url=get_avatar_url)


def get_avatar_url(username):
    """Return URL for user's avatar, or None if they have none."""
    profile = user_profiles.get(username, {})
    fn = profile.get("avatar")
    return f"/uploads/{fn}" if fn else None

@app.route("/profile/<username>/upload_avatar", methods=["POST"])
def upload_avatar(username):
    if session.get("username") != username:
        return "Forbidden", 403
    f = request.files.get("avatar")
    if f and f.filename:
        filename = secure_filename(f.filename)
        uid = "avatar_" + username + "_" + filename
        f.save(os.path.join(UPLOAD_FOLDER, uid))
        if username not in user_profiles:
            user_profiles[username] = {}
        user_profiles[username]["avatar"] = uid
    return redirect(url_for("view_profile", username=username))


HASHTAG_TEMPLATE = HASHTAG_MACRO + AVATAR_MACRO + """<!DOCTYPE html>
<html><head><title>#{{ tag }} — Legacy Fortress</title>""" + BASE_STYLE + """</head><body>
""" + NAV + """
<div class="main-wrap">

<a class="back-link" href="/">&#9668; Back to Posts</a>

<div class="lce-panel">
  <div class="panel-title">&#9670;&nbsp; Hashtag Channel</div>
  <div class="panel-body">
    <div class="hashtag-page-title">#{{ tag }}</div>
    <div class="hashtag-page-sub">{{ tagged_posts|length }} post{{ 's' if tagged_posts|length != 1 else '' }} tagged</div>
  </div>
</div>

{% if other_tags %}
<div class="lce-panel">
  <div class="panel-title" style="font-size:16px;letter-spacing:2px;">&#9670;&nbsp; All Channels</div>
  <div class="panel-body" style="padding:10px 14px;">
    <div class="tags-cloud">
      {% for t, count in other_tags %}
        <a class="hashtag-pill {% if t == tag %}hashtag-pill-active{% endif %}" href="/hashtag/{{ t }}">
          #{{ t }}<span class="pill-count">{{ count }}</span>
        </a>
      {% endfor %}
    </div>
  </div>
</div>
{% endif %}

<hr>

{% for post in tagged_posts %}
<div class="post-card">
  <a class="post-title-link" href="/post/{{ post.id }}">
    <div class="meta">{{ mini_avatar(post.author) }}<a class="author-link" href="/profile/{{ post.author }}" onclick="event.stopPropagation()">{{ post.author }}</a><span class="meta-sep">&mdash;</span><span class="meta-time">{{ post.time }}</span></div>
    {% if post.content %}<p>{{ markup_content(post.content) }}</p>{% endif %}
    {% if post.attachment %}
      {% set cat = file_category(post.attachment.mime) %}
      <div class="post-media">
      {% if cat == 'image' %}<img src="/uploads/{{ post.attachment.filename }}" alt="{{ post.attachment.original }}">
      {% elif cat == 'video' %}<video><source src="/uploads/{{ post.attachment.filename }}" type="{{ post.attachment.mime }}"></video>
      {% else %}<span style="font-family:var(--vt);font-size:15px;color:#446;">&#128206; {{ post.attachment.original }}</span>{% endif %}
      </div>
    {% endif %}
  </a>
  {{ hashtag_chips(post.hashtags) }}
  <div class="vote-bar">
    {% set uv = post.votes.get(username, 0) if username else 0 %}
    <button class="vote-btn {% if uv==1 %}liked{% endif %}"
      {% if username %}onclick="event.stopPropagation();votePost({{ post.id }}, 1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + UP_SVG + """ <span>{{ post.likes }}</span>
    </button>
    <button class="vote-btn {% if uv==-1 %}disliked{% endif %}"
      {% if username %}onclick="event.stopPropagation();votePost({{ post.id }}, -1, this)"{% endif %}
      {% if not username %}title="Log in to vote"{% endif %}>
      """ + DOWN_SVG + """ <span>{{ post.dislikes }}</span>
    </button>
    <a href="/post/{{ post.id }}" class="reply-count">
      """ + REPLY_SVG.replace('<svg', '<svg style="width:13px;height:13px;fill:currentColor;vertical-align:middle"') + """
      {{ post.reply_count }} repl{{ 'y' if post.reply_count == 1 else 'ies' }}
    </a>
  </div>
</div>
{% else %}
<div class="no-posts">&#9670; No posts with #{{ tag }} yet.</div>
{% endfor %}

</div>
""" + BASE_JS + """
<style>
.hashtag-pill-active {
  border-color: var(--lce-blue) !important;
  background: rgba(68,136,255,0.18) !important;
  color: #fff !important;
  box-shadow: 2px 2px 0 #000, 0 0 8px rgba(68,136,255,0.3) !important;
}
</style>
</body></html>
"""

def get_all_tags():
    """Return sorted list of (tag, count) across all posts, by count desc."""
    counts = {}
    for p in posts:
        for t in p.get("hashtags", []):
            counts[t] = counts.get(t, 0) + 1
    return sorted(counts.items(), key=lambda x: -x[1])

@app.route("/hashtag/<tag>")
def hashtag_page(tag):
    tag = tag.lower()
    username = session.get("username")
    tagged = list(reversed([p for p in posts if tag in p.get("hashtags", [])]))
    for p in tagged:
        p["reply_count"] = count_replies(p["replies"])
    all_tags = get_all_tags()
    return render_template_string(HASHTAG_TEMPLATE,
        tag=tag, tagged_posts=tagged, username=username,
        other_tags=all_tags, file_category=file_category,
        get_avatar_url=get_avatar_url)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
