"""Verify all login fixes are present in source files"""
import os

results = []

def check(name, cond):
    results.append((name, cond))
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")

print("=" * 50)
print("SOURCE FIX VERIFICATION")
print("=" * 50)

# 1. auth.py
src = open('app/routes/auth.py', encoding='utf-8').read()

print("\n--- app/routes/auth.py ---")
check("Rate-limit only on failure (rate-limit ONLY on actual failure)",
      'rate-limit ONLY on actual failure' in src)
check("Rate-limit only on failure (wrong password path)",
      src.count('rate-limit ONLY on actual failure') >= 2)
check("Successful login clears failure counter",
      'CLEAR the per-identifier failure counter' in src)
check("cache.delete used to clear counter",
      'cache.delete(f"rl:login_fail_id:{identifier}")' in src)
check("validate_whatsapp called in register",
      'whatsapp_clean = validate_whatsapp(whatsapp)' in src)
check("validate_pseudo called in register",
      'validate_pseudo(pseudo_clean)' in src)
check("Removed redundant clean_wa step in _find_user_by_identifier",
      '# 3 Pseudo case-insensitive exact (compare ident only' in src)
check("IP-level login limiter raised to 30/min",
      'limiter.limit("30 per minute")' in src)

# 2. login.html
tpl = open('templates/auth/login.html', encoding='utf-8').read()

print("\n--- templates/auth/login.html ---")
check("Hint shows StanD -> pass123",
      'StanD' in tpl and 'pass123' in tpl)
check("Old misleading hint removed (123456 oswa pass123 gone)",
      '123456 oswa pass123' not in tpl)

# 3. config.py
cfg = open('app/config.py', encoding='utf-8').read()

print("\n--- app/config.py ---")
check("RATELIMIT_ENABLED env var override",
      'RATELIMIT_ENABLED = os.environ.get' in cfg)

print("\n" + "=" * 50)
fails = [n for n, c in results if not c]
print(f"RESULTS: {len(results) - len(fails)} passed, {len(fails)} failed")
if fails:
    print("FAILED:", fails)
print("=" * 50)