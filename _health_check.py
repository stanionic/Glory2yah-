import urllib.request, json, time
time.sleep(3)
out = []
for url in ["http://localhost:8080/health", "http://localhost:8080/", "http://localhost:8080/mache/"]:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        r = urllib.request.urlopen(req, timeout=10)
        out.append(f"{url} => {r.status} len={len(r.read())}")
    except Exception as e:
        out.append(f"{url} => ERROR {e}")
result = "\n".join(out)
print(result)
with open("_health_check.txt", "w", encoding="utf-8") as f:
    f.write(result)
