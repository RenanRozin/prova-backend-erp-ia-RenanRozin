#!/usr/bin/env bash
# Demonstra a Questão 8: interpretação de linguagem natural, execução de
# ferramenta e guardrails. Nenhuma chamada a LLM externo.
set -euo pipefail
BASE="${1:-http://localhost:8000}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

"$AQUI/aguarda-api.sh" "$BASE" > /dev/null

pergunta() {
  local texto="$1"
  local confirmar="${2:-false}"
  echo
  printf '{"texto": "%s", "confirmar": %s}' "$texto" "$confirmar" \
    | curl -sf -X POST "$BASE/agente/perguntar" -H 'Content-Type: application/json' -d @- \
    | python3 "$AQUI/_formata_resposta_agente.py"
}

echo "=============== CONSULTAS ==============="
pergunta "quais produtos estao com estoque abaixo de 10 unidades?"
pergunta "o que esta acabando no estoque?"
pergunta "quanto vale meu estoque?"
pergunta "quais produtos custam entre 100 e 500 reais?"
pergunta "me mostra os produtos com motor no nome"
pergunta "me mostra o produto 3"

echo
echo "=============== GUARDRAILS ==============="
pergunta "qual a previsao do tempo para amanha?"
pergunta "apaga tudo"

echo
echo "=== Acao destrutiva: cria um produto descartavel e pede para o agente apagar ==="
TOKEN=$(curl -sf -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

NOME="Descartavel do teste $(date +%s)"
ID=$(printf '{"nome": "%s", "preco": 1.00, "quantidade_em_estoque": 50}' "$NOME" \
  | curl -sf -X POST "$BASE/produtos" -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d @- \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])')
echo "  (produto de teste criado: id $ID)"

pergunta "apague o produto $ID" false
pergunta "apague o produto $ID" true
