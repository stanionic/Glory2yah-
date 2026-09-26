import importlib.util
mods = ['playwright', 'bs4', 'segno', 'imageio_ffmpeg', 'flask', 'PIL', 'imageio']
lines = [f"{m}: {'OK' if importlib.util.find_spec(m) else 'MISSING'}" for m in mods]
out = "\n".join(lines)
print(out)
with open("_verify_installs.txt", "w", encoding="utf-8") as f:
    f.write(out)
