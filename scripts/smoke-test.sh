#!/usr/bin/env bash
# Teste de fumaça de ponta a ponta contra a stack do docker compose.
# Uso: ./scripts/smoke-test.sh [url-base]
set -euo pipefail

BASE="${1:-http://localhost:8000}"
USUARIO="${SEED_ADMIN_USERNAME:-admin}"
SENHA="${SEED_ADMIN_PASSWORD:-admin123}"

verde() { printf "\033[32m%s\033[0m\n" "$1"; }
titulo() { printf "\n\033[1m== %s ==\033[0m\n" "$1"; }

json() { python3 -m json.tool; }
extrai() { python3 -c "import sys,json; print(json.load(sys.stdin)$1)"; }

titulo "1. Readiness"
curl -sf "$BASE/health/ready" | json

titulo "2. Escrita sem token deve ser recusada"
codigo=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/produtos" \
  -H 'Content-Type: application/json' \
  -d '{"nome":"Teste","preco":10,"quantidade_em_estoque":1}')
[ "$codigo" = "401" ] && verde "401 como esperado" || { echo "ERRO: esperava 401, veio $codigo"; exit 1; }

titulo "3. Login"
TOKEN=$(curl -sf -X POST "$BASE/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"username\":\"$USUARIO\",\"password\":\"$SENHA\"}" | extrai "['access_token']")
verde "token obtido: ${TOKEN:0:24}..."
AUTH="Authorization: Bearer $TOKEN"

titulo "4. Listagem com paginação e ordenação"
curl -sf "$BASE/produtos?limit=3&ordenar_por=preco&ordem=desc" | json

titulo "5. Filtro de estoque baixo"
curl -sf "$BASE/produtos?estoque_baixo_ate=5" | extrai "['total']" | xargs -I{} echo "produtos com estoque <= 5: {}"

titulo "6. Filtro por nome e faixa de preço"
curl -sf "$BASE/produtos?nome=motor&preco_min=1000&preco_max=3000" | json

titulo "7. Validação: preço negativo deve ser recusado"
codigo=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/produtos" -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{"nome":"Item","preco":-5}')
[ "$codigo" = "422" ] && verde "422 como esperado" || { echo "ERRO: esperava 422, veio $codigo"; exit 1; }

titulo "8. Validação: nome numérico deve ser recusado"
codigo=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/produtos" -H "$AUTH" \
  -H 'Content-Type: application/json' -d '{"nome":"12345","preco":5}')
[ "$codigo" = "422" ] && verde "422 como esperado" || { echo "ERRO: esperava 422, veio $codigo"; exit 1; }

titulo "9. Criação de produto com estoque baixo (dispara a fila)"
ID=$(curl -sf -X POST "$BASE/produtos" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"nome":"Válvula pneumática 1/2","preco":345.90,"quantidade_em_estoque":4}' | extrai "['id']")
verde "produto criado com id $ID"

titulo "10. Nome duplicado deve dar 409"
codigo=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/produtos" -H "$AUTH" \
  -H 'Content-Type: application/json' \
  -d '{"nome":"Válvula pneumática 1/2","preco":10,"quantidade_em_estoque":1}')
[ "$codigo" = "409" ] && verde "409 como esperado" || { echo "ERRO: esperava 409, veio $codigo"; exit 1; }

titulo "11. Leitura por id (primeira: MISS, segunda: HIT no Redis)"
curl -sf "$BASE/produtos/$ID" > /dev/null
curl -sf "$BASE/produtos/$ID" | json

titulo "12. Atualização parcial"
curl -sf -X PATCH "$BASE/produtos/$ID" -H "$AUTH" -H 'Content-Type: application/json' \
  -d '{"preco":399.90}' | extrai "['preco']" | xargs -I{} echo "novo preço: {}"

titulo "13. Remoção"
codigo=$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$BASE/produtos/$ID" -H "$AUTH")
[ "$codigo" = "204" ] && verde "204 como esperado" || { echo "ERRO: esperava 204, veio $codigo"; exit 1; }

codigo=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/produtos/$ID")
[ "$codigo" = "404" ] && verde "404 após remoção (cache invalidado)" || { echo "ERRO: esperava 404, veio $codigo"; exit 1; }

titulo "RESULTADO"
verde "Todos os passos concluíram com sucesso."
