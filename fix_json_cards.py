import json

INPUT = "personagens_anilist.txt"
OUTPUT = "personagens_fix.json"

with open(INPUT, "r", encoding="utf-8") as f:
    text = f.read()

# tenta corrigir vírgulas faltando entre objetos
text = text.replace("}\n    {", "},\n    {")

# remove vírgulas duplicadas
text = text.replace(",]", "]")
text = text.replace(",}", "}")

data = json.loads(text)

with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("JSON corrigido salvo em:", OUTPUT)
