from pathlib import Path

path = Path("aninexus_frontend/src/pages/MediaAdmin.tsx")
text = path.read_text(encoding="utf-8")
old = "  useEffect(() => {\n    if (!selected && results.length === 1) void loadAssets(results[0]);\n  }, [results]);\n"
new = "  useEffect(() => {\n    const onlyResult = results[0];\n    if (!selected && results.length === 1 && onlyResult) void loadAssets(onlyResult);\n  }, [results, selected]);\n"
if old not in text:
    raise RuntimeError("MediaAdmin guard block not found")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
