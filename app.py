from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from pathlib import Path
from datetime import datetime
import json, sqlite3, shutil, subprocess
from organizer import Organizer
from rules import RuleStore

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
DATA.mkdir(exist_ok=True)
DB = DATA / 'fileflow.db'
CONFIG = DATA / 'config.json'
app = Flask(__name__)
app.secret_key = 'fileflow-local-v2'
store = RuleStore()

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY AUTOINCREMENT, created TEXT, moved INTEGER, errors INTEGER)')
    c.execute('CREATE TABLE IF NOT EXISTS moves(id INTEGER PRIMARY KEY AUTOINCREMENT,batch_id INTEGER,source TEXT,destination TEXT,size INTEGER)')
    c.commit()
    return c

def load_config():
    try:
        return json.loads(CONFIG.read_text())
    except Exception:
        return {'folder': '', 'conflict_policy': 'rename', 'theme': 'system'}

def save_config(c):
    CONFIG.write_text(json.dumps(c, indent=2))

def org():
    return Organizer(load_config().get('folder', ''), store.rules)

def scan_data():
    o = org()
    items = o.scan()
    cats, total_size = {}, 0
    for x in items:
        total_size += x['size']
        cats[x['category'] or 'Unknown'] = cats.get(x['category'] or 'Unknown', 0) + 1
    return items, cats, total_size

@app.get('/')
def dashboard():
    config = load_config()
    items, cats, total = scan_data() if Path(config.get('folder', '')).is_dir() else ([], {}, 0)
    con = db(); recent = con.execute('SELECT * FROM batches ORDER BY id DESC LIMIT 5').fetchall(); con.close()
    return render_template('dashboard.html', config=config, items=items, cats=cats, total_size=total, recent=recent, rules=store.rules)

@app.post('/folder')
def set_folder():
    folder = request.form.get('folder', '').strip(); p = Path(folder).expanduser()
    if not p.is_dir():
        flash('That folder does not exist or is not accessible.', 'error'); return redirect(url_for('dashboard'))
    c = load_config(); c['folder'] = str(p.resolve()); save_config(c)
    flash('Workspace connected.', 'success'); return redirect(url_for('dashboard'))

@app.get('/preview')
def preview():
    c = load_config(); p = Path(c.get('folder', ''))
    if not p.is_dir():
        flash('Choose a valid folder first.', 'error'); return redirect(url_for('dashboard'))
    return render_template('preview.html', items=org().preview(), folder=str(p), config=c, rules=store.rules)

@app.post('/organize')
def organize():
    c = load_config(); p = Path(c.get('folder', ''))
    if not p.is_dir():
        flash('Choose a valid folder first.', 'error'); return redirect(url_for('dashboard'))
    selected = request.form.getlist('selected')
    items = org().preview()
    if selected:
        items = [x for x in items if x['source'] in selected]
    else:
        items = []
    policy = request.form.get('conflict_policy', c.get('conflict_policy', 'rename'))
    if policy not in {'rename', 'skip', 'replace'}:
        policy = 'rename'
    c['conflict_policy'] = policy; save_config(c)
    try:
        result = org().execute(items, policy)
    except PermissionError as exc:
        flash(str(exc), 'error'); return redirect(url_for('preview'))
    con = db()
    cur = con.execute('INSERT INTO batches(created,moved,errors) VALUES(?,?,?)', (datetime.now().isoformat(timespec='seconds'), len(result['moved']), len(result['errors'])))
    bid = cur.lastrowid
    con.executemany('INSERT INTO moves(batch_id,source,destination,size) VALUES(?,?,?,?)', [(bid, x['source'], x['destination'], x.get('size', 0)) for x in result['moved']])
    con.commit(); con.close()
    if result['errors']:
        flash(f"Organized {len(result['moved'])}; {len(result['errors'])} item(s) need attention.", 'info')
    else:
        flash(f"Organized {len(result['moved'])} file(s).", 'success')
    return redirect(url_for('activity'))

@app.post('/undo/<int:batch_id>')
def undo(batch_id):
    con = db(); rows = con.execute('SELECT * FROM moves WHERE batch_id=? ORDER BY id DESC', (batch_id,)).fetchall(); restored = 0
    for r in rows:
        src, dst = Path(r['destination']), Path(r['source'])
        try:
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True); src.rename(dst); restored += 1
        except OSError:
            pass
    con.execute('DELETE FROM moves WHERE batch_id=?', (batch_id,)); con.execute('DELETE FROM batches WHERE id=?', (batch_id,)); con.commit(); con.close()
    flash(f'Undid {restored} move(s).', 'success'); return redirect(url_for('activity'))

@app.get('/activity')
def activity():
    con = db(); batches = con.execute('SELECT * FROM batches ORDER BY id DESC LIMIT 50').fetchall(); con.close()
    return render_template('activity.html', batches=batches, config=load_config())

@app.route('/rules', methods=['GET', 'POST'])
def rules():
    if request.method == 'POST':
        action = request.form.get('action'); name = request.form.get('name', '').strip()
        if action == 'delete':
            store.rules.pop(name, None)
        elif action in ('add', 'save'):
            exts = [e.strip().lower() for e in request.form.get('extensions', '').split(',') if e.strip()]
            exts = [e if e.startswith('.') else '.' + e for e in exts]
            keywords = [x.strip().lower() for x in request.form.get('keywords', '').split(',') if x.strip()]
            try: priority = max(1, int(request.form.get('priority', '100')))
            except ValueError: priority = 100
            destination = request.form.get('destination', '').strip() or name
            if name:
                store.rules[name] = {'extensions': exts, 'filename_contains': keywords, 'priority': priority, 'destination': destination}
        store.save(); flash('Rules saved.', 'success'); return redirect(url_for('rules'))
    return render_template('rules.html', rules=store.rules, config=load_config())

@app.post('/theme')
def theme():
    selected = request.form.get('theme', 'system')
    if selected not in {'system', 'light', 'dark'}:
        selected = 'system'
    c = load_config(); c['theme'] = selected; save_config(c)
    return jsonify(ok=True, theme=selected)

@app.get('/pick-folder')
def pick_folder():
    """Open a native directory chooser on the machine running FileFlow.

    FileFlow is intentionally local-first, so this endpoint is meant for the
    localhost app. KDE users get kdialog; GNOME/GTK users get zenity/yad.
    """
    current = load_config().get('folder', '')
    candidates = []
    if shutil.which('kdialog'):
        cmd = ['kdialog', '--getexistingdirectory', current or str(Path.home()), '--title', 'Choose a FileFlow workspace']
        candidates.append(cmd)
    if shutil.which('zenity'):
        cmd = ['zenity', '--file-selection', '--directory', '--title=Choose a FileFlow workspace']
        if current and Path(current).is_dir():
            cmd.append(f'--filename={str(Path(current).resolve())}/')
        candidates.append(cmd)
    if shutil.which('yad'):
        cmd = ['yad', '--file-selection', '--directory', '--title=Choose a FileFlow workspace']
        candidates.append(cmd)

    if not candidates:
        return jsonify(ok=False, error='No native folder picker found. Install kdialog or zenity.'), 501

    for cmd in candidates:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode != 0:
                return jsonify(ok=False, cancelled=True)
            folder = result.stdout.strip()
            if not folder:
                return jsonify(ok=False, cancelled=True)
            p = Path(folder).expanduser()
            if not p.is_dir():
                return jsonify(ok=False, error='The selected folder is not accessible.'), 400
            c = load_config(); c['folder'] = str(p.resolve()); save_config(c)
            return jsonify(ok=True, folder=str(p.resolve()))
        except (OSError, subprocess.SubprocessError) as exc:
            last_error = str(exc)
            continue
    return jsonify(ok=False, error=locals().get('last_error', 'Could not open the native folder picker.')), 500

@app.get('/api/scan')
def api_scan():
    items, cats, total = scan_data(); return jsonify({'items': items, 'categories': cats, 'total_size': total})

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000, debug=True)
