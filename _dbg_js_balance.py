"""Tokenizer-based bracket balance check for extracted room JS.

Usage as module:  from _dbg_js_balance import check_js_balance
Usage as script:  python _dbg_js_balance.js [path]  (default: _dbg_room_main.js)
"""
import io
import sys


def check_js_balance(src):
    """Returns (ok, message) — tokenizer handles strings, template literals
    with nested ${...}, regex literals, and comments."""
    stack = []
    line = 1
    i = 0
    n = len(src)
    mode = []  # 'tpl' entries track template-literal ${...} contexts

    def scan_template(i):
        """Scan a template literal starting after an opening backtick.
        Returns (i, ok)."""
        nonlocal line
        while i < n:
            if src[i] == '\\':
                i += 2
                continue
            if src[i] == '\n':
                line += 1
            if src[i] == '`':
                return i + 1, True
            if src[i] == '$' and i + 1 < n and src[i + 1] == '{':
                stack.append(('{', line))
                mode.append('tpl')
                return i + 2, True
            i += 1
        return i, False

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
            i, _ok = scan_template(i + 1)
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
                # regex literal
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
        if c in '{([':
            stack.append((c, line))
            mode.append(None)
            i += 1
            continue
        if c in '})]':
            opener = {'}': '{', ')': '(', ']': '['}[c]
            if not stack or stack[-1][0] != opener:
                return False, f'UNBALANCED at line {line}: unexpected {c!r}, stack top={stack[-1] if stack else None}'
            stack.pop()
            if mode and mode[-1] == 'tpl':
                mode.pop()
                i, _ok = scan_template(i + 1)
                continue
            mode.pop()
            i += 1
            continue
        i += 1

    if stack:
        return False, f'UNCLOSED: {stack[-5:]} (total open={len(stack)})'
    return True, f'JS balanced OK ({n} chars, {line} lines)'


if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else '_dbg_room_main.js'
    src = io.open(path, encoding='utf-8').read()
    ok, msg = check_js_balance(src)
    print(msg)
    sys.exit(0 if ok else 1)
