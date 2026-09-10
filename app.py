"""
The website: all your fantasy matchups on one page.

Run:  python app.py
Then open the link it prints (http://127.0.0.1:8733) in your browser.

- Pick a week from the dropdown at the top.
- Click Refresh to pull the latest scores.
- Sleeper and ESPN leagues appear together as cards.

This runs entirely on your own machine and only reads your own leagues.
"""

import json
import os
import secrets
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from urllib.parse import urlparse, parse_qs

import ff_data

# On Render, PORT is provided and the app must listen on all interfaces.
# On your laptop, it defaults to localhost only (private to your machine).
PORT = int(os.environ.get("PORT", "8733"))
HOST = "0.0.0.0" if os.environ.get("PORT") else "127.0.0.1"

# Active login sessions: token -> True. Reset when the server restarts,
# so you'll simply log in again after a restart.
SESSIONS = set()

PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>My Fantasy Matchups</title>
<style>
  :root { --bg:#0f1420; --card:#1a2233; --line:#2a3550; --text:#e8edf7;
          --muted:#8f9ec0; --win:#34d399; --lose:#f87171; --tie:#fbbf24;
          --sleeper:#ff5a5f; --espn:#d50a0a; }
  * { box-sizing:border-box; }
  body { margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:var(--bg); color:var(--text); }
  header { padding:20px 24px; border-bottom:1px solid var(--line);
           display:flex; align-items:center; gap:16px; flex-wrap:wrap; }
  h1 { font-size:20px; margin:0; font-weight:650; }
  .controls { margin-left:auto; display:flex; align-items:center; gap:10px; }
  select, button { background:var(--card); color:var(--text);
    border:1px solid var(--line); border-radius:8px; padding:8px 12px;
    font-size:14px; cursor:pointer; }
  button:hover { border-color:#3a4a70; }
  .wrap { padding:24px; max-width:1100px; margin:0 auto; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(320px,1fr));
          gap:16px; }
  .card { background:var(--card); border:1px solid var(--line);
          border-radius:14px; padding:16px 18px; }
  .badge { font-size:11px; font-weight:700; letter-spacing:.04em;
           text-transform:uppercase; padding:3px 8px; border-radius:6px;
           color:#fff; }
  .badge.Sleeper { background:var(--sleeper); }
  .badge.ESPN { background:var(--espn); }
  .league { font-size:13px; color:var(--muted); margin:10px 0 14px; }
  .row { display:flex; justify-content:space-between; align-items:center;
         padding:8px 0; }
  .row + .row { border-top:1px solid var(--line); }
  .name { font-weight:600; }
  .name.me { color:var(--text); }
  .name.opp { color:var(--muted); }
  .score { font-variant-numeric:tabular-nums; font-weight:700; font-size:18px; }
  .tag { font-size:12px; margin-top:12px; font-weight:600; }
  .tag.winning { color:var(--win); } .tag.losing { color:var(--lose); }
  .tag.tied { color:var(--tie); }
  .empty, .err { color:var(--muted); padding:20px; text-align:center; }
  .err { color:var(--lose); }
  .summary { color:var(--muted); font-size:13px; margin-bottom:16px; }
  .loading { opacity:.5; }
</style>
</head>
<body>
<header>
  <h1>🏈 My Fantasy Matchups</h1>
  <div class="controls">
    <label for="week" style="color:var(--muted);font-size:13px">Week</label>
    <select id="week"></select>
    <button id="refresh">Refresh</button>
    <a href="/logout" style="color:var(--muted);font-size:13px;text-decoration:none">Sign out</a>
  </div>
</header>
<div class="wrap">
  <div class="summary" id="summary"></div>
  <div class="grid" id="grid"></div>
</div>
<script>
const weekSel = document.getElementById('week');
const grid = document.getElementById('grid');
const summary = document.getElementById('summary');
for (let w = 1; w <= 18; w++) {
  const o = document.createElement('option'); o.value = w; o.textContent = 'Week ' + w;
  weekSel.appendChild(o);
}

async function load() {
  const week = weekSel.value;
  grid.classList.add('loading');
  summary.textContent = 'Loading week ' + week + '…';
  try {
    const res = await fetch('/api/matchups?week=' + week);
    const data = await res.json();
    render(data, week);
  } catch (e) {
    grid.innerHTML = '<div class="err">Could not load data. Is the server running?</div>';
    summary.textContent = '';
  }
  grid.classList.remove('loading');
}

function render(data, week) {
  grid.innerHTML = '';
  const rows = data.rows || [];
  const errs = data.errors || [];
  const leagues = new Set(rows.map(r => r.league));
  summary.textContent = rows.length
    ? rows.length + ' matchup(s) across ' + leagues.size + ' league(s) — season ' + data.season
    : 'No matchups found for week ' + week + '.';

  rows.forEach(r => {
    const tagText = r.status === 'winning' ? "You're ahead"
      : r.status === 'losing' ? "You're behind" : 'Tied';
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <span class="badge ${r.platform}">${r.platform}</span>
      <div class="league">${escape(r.league)}</div>
      <div class="row"><span class="name me">${escape(r.my_name)}</span>
        <span class="score">${r.my_score.toFixed(1)}</span></div>
      <div class="row"><span class="name opp">${escape(r.opp_name)}</span>
        <span class="score">${r.opp_score.toFixed(1)}</span></div>
      <div class="tag ${r.status}">${tagText}</div>`;
    grid.appendChild(card);
  });

  if (errs.length) {
    const e = document.createElement('div');
    e.className = 'err';
    e.style.gridColumn = '1 / -1';
    e.innerHTML = errs.map(escape).join('<br>');
    grid.appendChild(e);
  }
  if (!rows.length && !errs.length) {
    grid.innerHTML = '<div class="empty">Nothing to show yet.</div>';
  }
}

function escape(s) {
  return String(s).replace(/[&<>"]/g, c =>
    ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
}

weekSel.addEventListener('change', load);
document.getElementById('refresh').addEventListener('click', load);
weekSel.value = 1;
load();
</script>
</body>
</html>"""


LOGIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sign in — My Fantasy Matchups</title>
<style>
  body { margin:0; min-height:100vh; display:flex; align-items:center;
    justify-content:center; background:#0f1420; color:#e8edf7;
    font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif; }
  .box { background:#1a2233; border:1px solid #2a3550; border-radius:16px;
    padding:32px; width:320px; }
  h1 { font-size:20px; margin:0 0 4px; }
  p { color:#8f9ec0; font-size:13px; margin:0 0 20px; }
  label { display:block; font-size:12px; color:#8f9ec0; margin:14px 0 6px; }
  input { width:100%; padding:10px 12px; border-radius:8px;
    border:1px solid #2a3550; background:#0f1420; color:#e8edf7; font-size:15px; }
  button { width:100%; margin-top:20px; padding:11px; border:none;
    border-radius:8px; background:#ff5a5f; color:#fff; font-size:15px;
    font-weight:600; cursor:pointer; }
  .err { color:#f87171; font-size:13px; margin-top:14px; min-height:18px; }
</style>
</head>
<body>
  <form class="box" method="POST" action="/login">
    <h1>🏈 My Fantasy Matchups</h1>
    <p>Sign in to see your leagues.</p>
    <label>Username</label>
    <input name="user" autocomplete="username" autofocus>
    <label>Password</label>
    <input name="password" type="password" autocomplete="current-password">
    <button type="submit">Sign in</button>
    <div class="err">%ERROR%</div>
  </form>
</body>
</html>"""


def _cookie_token(headers):
    raw = headers.get("Cookie", "")
    if not raw:
        return None
    jar = SimpleCookie()
    jar.load(raw)
    m = jar.get("ffsession")
    return m.value if m else None


def _is_authed(headers):
    tok = _cookie_token(headers)
    return bool(tok and tok in SESSIONS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass  # keep the console quiet

    def do_GET(self):
        parsed = urlparse(self.path)

        # The login page is the only thing visible when not signed in.
        if parsed.path == "/login":
            self._send(200, "text/html; charset=utf-8",
                       LOGIN_PAGE.replace("%ERROR%", "").encode("utf-8"))
            return

        if not _is_authed(self.headers):
            # Not signed in — send everyone to the login page.
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return

        if parsed.path == "/":
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        elif parsed.path == "/logout":
            tok = _cookie_token(self.headers)
            SESSIONS.discard(tok)
            self.send_response(302)
            self.send_header("Location", "/login")
            self.send_header("Set-Cookie", "ffsession=; Path=/; Max-Age=0")
            self.end_headers()
        elif parsed.path == "/api/matchups":
            qs = parse_qs(parsed.query)
            try:
                week = int(qs.get("week", ["1"])[0])
            except ValueError:
                week = 1
            rows, errors, season = ff_data.get_all_matchups(week)
            body = json.dumps(
                {"rows": rows, "errors": errors, "season": season}
            ).encode("utf-8")
            self._send(200, "application/json", body)
        else:
            self._send(404, "text/plain", b"Not found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/login":
            self._send(404, "text/plain", b"Not found")
            return

        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        form = parse_qs(body)
        user = form.get("user", [""])[0]
        password = form.get("password", [""])[0]

        cfg = ff_data.load_config()
        real_user = cfg.get("login_user", "")
        real_pass = cfg.get("login_password", "")

        # Constant-time compare so timing can't leak the password.
        ok = (
            real_user and real_pass
            and hmac.compare_digest(user, real_user)
            and hmac.compare_digest(password, real_pass)
        )
        if ok:
            token = secrets.token_urlsafe(32)
            SESSIONS.add(token)
            # On Render (HTTPS) mark the cookie Secure so it's only sent
            # over an encrypted connection.
            secure = "; Secure" if os.environ.get("PORT") else ""
            self.send_response(302)
            self.send_header("Location", "/")
            self.send_header(
                "Set-Cookie",
                f"ffsession={token}; Path=/; HttpOnly; SameSite=Lax; "
                f"Max-Age=86400{secure}",
            )
            self.end_headers()
        else:
            page = LOGIN_PAGE.replace("%ERROR%", "Wrong username or password.")
            self._send(200, "text/html; charset=utf-8", page.encode("utf-8"))

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"\n  Your fantasy dashboard is running at:  http://{HOST}:{PORT}\n")
    print("  Open that link in your browser. Press Ctrl+C here to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
        server.shutdown()


if __name__ == "__main__":
    main()
