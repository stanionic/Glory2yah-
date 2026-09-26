"""Check all key public routes of Glory2YahPub and report status."""
import urllib.request, urllib.error, ssl

BASE = "http://localhost:8080"
routes = [
    "/", "/mache/", "/about", "/terms", "/privacy", "/contact",
    "/auth/login", "/auth/register", "/submit_ad",
    "/gkach/", "/gadematch", "/tv", "/bank/", "/forms/",
    "/konferans", "/ecole_biblique", "/mennenm", "/dok", "/fet",
    "/pwa/offline", "/qr", "/demo", "/api/stories", "/api/feed",
    "/mache/categories",
]

results = []
for route in routes:
    url = BASE + route
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        r = urllib.request.urlopen(req, timeout=12)
        results.append(f"{r.status}  {route}")
    except urllib.error.HTTPError as e:
        results.append(f"{e.code}  {route}  ({e.reason})")
    except Exception as e:
        results.append(f"ERR  {route}  ({type(e).__name__}: {e})")

output = "\n".join(results)
print(output)
with open("_routes_check.txt", "w", encoding="utf-8") as f:
    f.write(output)

