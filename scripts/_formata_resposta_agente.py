"""Formata a resposta do agente para leitura no terminal (usado pelos demos)."""

import json
import sys

d = json.load(sys.stdin)
i = d["interpretacao"]
print(f"  pergunta   : {d['pergunta']}")
print(f"  interpretou: {i['ferramenta']} {i['argumentos']}  (confianca {i['confianca']})")
print(f"  status     : {d['status']}")
print(f"  resposta   : {d['resposta']}")
if d.get("sugestoes"):
    print(f"  sugestoes  : {d['sugestoes'][:2]}")
