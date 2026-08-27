"""Imprime o catálogo de ferramentas do agente nos dois formatos (usado no demo)."""

import json
import sys

d = json.load(sys.stdin)
print("total de ferramentas registradas:", d["total"])
print()
print("--- formato function calling: o payload que iria junto do prompt ---")
print(json.dumps(d["function_calling"][0], indent=2, ensure_ascii=False))
print()
print("--- a ferramenta destrutiva no formato MCP ---")
mcp = next(f for f in d["mcp"] if f["name"] == "remover_produto")
print(json.dumps(mcp, indent=2, ensure_ascii=False))
