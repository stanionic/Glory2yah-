"""Fetch the student ecole_biblique page with test user login"""
import requests
import re
import sys

s = requests.Session()

# Step 1: Get login page for CSRF token
r = s.get('http://localhost:8080/auth/login')
csrf_match = re.search(r'csrf-token[^>]+content="([^"]+)"', r.text)
if not csrf_match:
    print("ERROR: No CSRF token found", file=sys.stderr)
    sys.exit(1)
csrf = csrf_match.group(1)

# Find form field names
fields = re.findall(r'name="([^"]+)"', r.text)
print("Form fields:", fields)

# Step 2: Login with "Testeur Blueprint" - try different field combinations
# Try with 'whatsapp' and 'password' fields
login_data = {}
if 'whatsapp' in fields:
    login_data['whatsapp'] = 'Testeur Blueprint'
if 'password' in fields:
    login_data['password'] = 'Testeur Blueprint'
if 'csrf_token' in fields:
    login_data['csrf_token'] = csrf
if 'email' in fields:
    login_data['email'] = 'Testeur Blueprint'
if 'username' in fields:
    login_data['username'] = 'Testeur Blueprint'

print("Login data keys:", list(login_data.keys()))

r = s.post('http://localhost:8080/auth/login', data=login_data, allow_redirects=True)
print(f"Login -> {r.url} (status {r.status_code})")

# Step 3: Access ecole_biblique/student
r = s.get('http://localhost:8080/ecole_biblique/student', allow_redirects=True)
print(f"Student -> {r.url} (status {r.status_code})")

# Step 4: Check what the student sees
text = r.text
if 'Test' in text and 'Admission' in text:
    print(">>> Admission Test Section found")
    if 'Commencer le Test' in text:
        print("    - Button: Commencer le Test d'Admission")
    if 'Réussi' in text:
        print("    - Test already passed!")
    if 'inscription incompl' in text.lower():
        print("    - Registration incomplete")
if 'Modules Réussis' in text:
    print(">>> Dashboard with stats found")
if 'Module 1' in text:
    print(">>> Module 1 found in page")
if 'Introduction' in text:
    print(">>> 'Introduction' found in page")
if 'Premier' in text:
    print(">>> 'Premier' found in page")
if 'Théologie' in text or 'Th\xc3\xa9ologie' in text:
    print(">>> 'Théologie' found in page")

# Step 5: Extract main content
start = text.find('<main')
if start > 0:
    end = text.find('</main>', start)
    snippet = text[start:end][:3000]
    # Clean HTML entities
    snippet = snippet.replace('&#39;', "'")
    snippet = snippet.replace('&', '&')
    snippet = snippet.replace('<', '<')
    snippet = snippet.replace('>', '>')
    # Remove style tags
    snippet = re.sub(r'<style[^>]*>.*?</style>', '', snippet, flags=re.DOTALL)
    print("\n=== MAIN CONTENT ===")
    print(snippet[:3000])
else:
    print("\n=== PAGE START ===")
    print(text[:2000])