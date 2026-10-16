import yaml
with open("render.yaml") as f:
    doc = yaml.safe_load(f)
svc = doc["services"][0]
keys = {e["key"]: e for e in svc["envVars"]}
print("render.yaml VALID YAML")
print("SECRET_KEY ->", "generateValue" if keys["SECRET_KEY"].get("generateValue") else keys["SECRET_KEY"].get("value"))
print("ADMIN_PASSWORD ->", "generateValue" if keys["ADMIN_PASSWORD"].get("generateValue") else "(fixed value set)")
print("ADMIN_PASSWORD_RESET ->", keys["ADMIN_PASSWORD_RESET"].get("value"))
