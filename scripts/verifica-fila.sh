#!/usr/bin/env bash
# Prova que a tarefa em background é executada de verdade pelo worker:
# cria um produto abaixo do limite, espera o worker e mostra o alerta gravado.
set -euo pipefail
BASE="${1:-http://localhost:8000}"

TOKEN=$(curl -sf -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

NOME="Rele de estado solido 25A $(date +%s)"
echo "== criando produto com estoque 2 =="
curl -sf -X POST "$BASE/produtos" \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d "{\"nome\":\"$NOME\",\"preco\":98.50,\"quantidade_em_estoque\":2}" \
  | python3 -m json.tool

echo "== aguardando o worker =="
sleep 4

echo "== alertas gravados =="
docker compose exec -T db psql -U erp -d erp \
  -c "SELECT id, produto_id, produto_nome, quantidade_no_momento, limite_configurado, origem, data_criacao FROM alertas_estoque ORDER BY id;"
