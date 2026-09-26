"""
Scan the rendered konferans room page for TOP-LEVEL duplicate JS declarations.

A duplicate `const`/`let` at the same script scope is a fatal SyntaxError:
the whole <script> block dies at parse time (no socket, no chat, no video).
The brace-balance smoke test cannot catch this — this scanner can.

Renders the room page as OWNER and as GUEST (different Jinja branches),
extracts every inline <script> block, and reports identifiers declared more
than once at depth 0 of the same block.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app, db
from app.models import User, KonferansRoom

app = create_app()
app.config['WTF_CSRF_ENABLED'] = False
app.config['TESTING'] = True

OWNER_WA = '+50990000031'
ROOM_ID = 'SCAN_DECL_ROOM'
ROOM_CODE = 'SCNDCL'

fails = []


def check(name, cond):
    print(('  [OK]  ' if cond else '  [FAIL] ') + name)
    if not cond:
        fails.append(name)


# ---------- tokenizer: returns {(index): depth} only at declaration keywords ----------
DECL_KW = re.compile(r'\b(const|let|var)\b')


def top_level_decl_dupes(src, label):
    """Adapted from _dbg_js_balance tokenizer; records depth at every declaration
    keyword the tokenizer actually visits (string/comment contents are skipped
    automatically), then parses declared names for depth-0 hits."""
    n = len(src)
    line = 1
    i = 0
    stack = []
    mode = []
    kw_positions = {}  # index -> (depth, line)

    def scan_template(i):
        nonlocal line
        while i < n:
            if src[i] == '\\':
                i += 2
                continue
            if src[i] == '\n':
                line += 1
            if src[i] == '`':
                return i + 1
            if src[i] == '$' and i + 1 < n and src[i + 1] == '{':
                stack.append(('{', line))
                mode.append('tpl')
                return i + 2
            i += 1
        return i

    while i < n:
        c = src[i]
        if c == '\n':
            line += 1
            i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '/':
            while i < n and src[i] != '\n':
                i += 1
            continue
        if c == '/' and i + 1 < n and src[i + 1] == '*':
            i += 2
            while i + 1 < n and not (src[i] == '*' and src[i + 1] == '/'):
                if src[i] == '\n':
                    line += 1
                i += 1
            i += 2
            continue
        if c in ('"', "'"):
            quote = c
            i += 1
            while i < n:
                if src[i] == '\\':
                    i += 2
                    continue
                if src[i] == '\n':
                    line += 1
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == '`':
            i = scan_template(i + 1)
            continue
        if c == '/':
            prev = ''
            j = i - 1
            while j >= 0:
                if src[j] not in ' \t\n':
                    prev = src[j]
                    break
                j -= 1
            if prev == '' or prev in '(,=:[!&|?{;+-*%^~<':
                i += 1
                in_class = False
                while i < n:
                    if src[i] == '\\':
                        i += 2
                        continue
                    if src[i] == '\n':
                        break
                    if src[i] == '[':
                        in_class = True
                    elif src[i] == ']':
                        in_class = False
                    elif src[i] == '/' and not in_class:
                        i += 1
                        break
                    i += 1
                while i < n and src[i].isalpha():
                    i += 1
                continue
        # declaration keyword check (identifier boundary)
        if c.isalpha() or c in '_$':
            m = re.match(r'[A-Za-z_$][\w$]*', src[i:])
            word = m.group(0)
            if word in ('const', 'let', 'var'):
                kw_positions[i] = (len([s for s in stack if s[0] == '{']), line)
            i += len(word)
            continue
        if c in '{([':
            stack.append((c, line))
            mode.append(None)
            i += 1
            continue
        if c in '})]':
            if stack:
                stack.pop()
                if mode and mode[-1] == 'tpl':
                    mode.pop()
                    i = scan_template(i + 1)
                    continue
                mode.pop()
            i += 1
            continue
        i += 1

    # parse names for depth-0 declarations
    declared = {}  # name -> [lines]
    for idx in sorted(kw_positions):
        depth, ln = kw_positions[idx]
        if depth != 0:
            continue
        m = re.match(r'(?:const|let|var)\s+([A-Za-z_$][\w$]*)', src[idx:])
        if not m:
            continue
        declared.setdefault(m.group(1), []).append(ln)
        # comma list: scan rest of statement for `, name =` at raw depth 0
        rest = src[idx:]
        stop = re.search(r';', rest)
        stmt = rest[:stop.end()] if stop else rest[:200]
        # crude but effective: names after top-level commas
        depth2 = 0
        k = 0
        while k < len(stmt):
            ch = stmt[k]
            if ch in '{([':
                depth2 += 1
            elif ch in '})]':
                depth2 -= 1
            elif ch == ',' and depth2 == 0:
                mm = re.match(r'\s*([A-Za-z_$][\w$]*)\s*=', stmt[k + 1:])
                if mm:
                    declared.setdefault(mm.group(1), []).append(ln)
            k += 1

    dupes = {name: lines for name, lines in declared.items() if len(lines) > 1}
    return dupes, len(declared)


# ---------- setup ----------
with app.app_context():
    db.create_all()
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp == OWNER_WA).delete(synchronize_session=False)
    db.session.commit()
    owner = User(name='Scan Owner', pseudo='ScanOwner', whatsapp=OWNER_WA, password_hash='x')
    db.session.add(owner)
    db.session.commit()
    db.session.add(KonferansRoom(room_id=ROOM_ID, room_code=ROOM_CODE, room_name='Scan Room',
                                 creator_name='Scan Owner', user_id=owner.id, is_active=True))
    db.session.commit()
    owner_id = owner.id

client = app.test_client()

for variant, do_login in (('owner', True), ('guest', False)):
    c = app.test_client()
    if do_login:
        with c.session_transaction() as s:
            s['_user_id'] = str(owner_id)
            s['_fresh'] = True
    r = c.get(f'/konferans/room/{ROOM_CODE}')
    html = r.get_data(as_text=True)
    check(f'{variant}: room page -> 200', r.status_code == 200)

    scripts = re.findall(r'<script>(.*?)</script>', html, flags=re.S)
    print(f'  .. {variant}: {len(scripts)} inline script block(s)')
    total_dupes = {}
    for si, src in enumerate(scripts):
        if len(src) < 200:
            continue  # tiny bootstrap blocks — skip noise
        dupes, total = top_level_decl_dupes(src, f'{variant}#script{si}')
        for name, lines in dupes.items():
            total_dupes.setdefault(name, []).extend(lines)
    if total_dupes:
        for name, lines in total_dupes.items():
            check(f'{variant}: NO duplicate top-level `{name}` (lines {lines})', False)
    else:
        check(f'{variant}: no duplicate top-level declarations', True)

# ---------- cleanup ----------
with app.app_context():
    KonferansRoom.query.filter_by(room_id=ROOM_ID).delete()
    User.query.filter(User.whatsapp == OWNER_WA).delete(synchronize_session=False)
    db.session.commit()

print()
if fails:
    print(f'{len(fails)} FAILURES: {fails}')
    sys.exit(1)
print('DECLARATION SCAN PASSED')
