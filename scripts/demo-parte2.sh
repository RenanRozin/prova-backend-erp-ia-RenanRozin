#!/usr/bin/env bash
# Demonstra a Questão 4: paralelismo, timeout por fonte, retry e degradação graciosa.
set -euo pipefail
BASE="${1:-http://localhost:8000}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$AQUI/aguarda-api.sh" "$BASE" > /dev/null

resumo() {
  python3 -c '
import sys, json
d = json.load(sys.stdin)
print(f"  completo={d["completo"]}  duracao_total={d["duracao_total_ms"]}ms")
for nome, f in d["fontes"].items():
    erro = f"  erro={f["erro"]}" if f["erro"] else ""
    print(f"  {nome:12} status={f["status"]:13} tentativas={f["tentativas"]}  {f["latencia_ms"]}ms{erro}")
'
}

echo "== A. Caminho feliz: as 3 fontes respondem =="
curl -sf "$BASE/agregado/visao-360?cliente_id=7&produto_id=3" | resumo

echo
echo "== B. Financeiro lento: estoura o timeout de 0.5s e degrada =="
curl -sf "$BASE/agregado/visao-360?lenta=financeiro" | resumo

echo
echo "== C. Estoque fora do ar (503): 3 tentativas e desiste =="
curl -sf "$BASE/agregado/visao-360?indisponivel=estoque" | resumo

echo
echo "== D. Falha transitória no cliente: a retentativa salva =="
curl -sf "$BASE/agregado/visao-360?falha_transitoria=cliente" | resumo

echo
echo "== E. Erro permanente (4xx): NÃO repete, sai na primeira =="
curl -sf "$BASE/agregado/visao-360?invalida=financeiro" | resumo

echo
echo "== F. Duas fontes caídas ao mesmo tempo: ainda assim responde =="
curl -sf "$BASE/agregado/visao-360?lenta=financeiro&indisponivel=estoque" | resumo
