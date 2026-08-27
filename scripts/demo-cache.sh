#!/usr/bin/env bash
# Mostra a estrategia de invalidacao de cache funcionando, chave por chave.
# A prova pede para explicar a estrategia; este script deixa ela visivel.
set -euo pipefail
BASE="${1:-http://localhost:8000}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$AQUI/aguarda-api.sh" "$BASE" > /dev/null

redis() { docker compose exec -T redis redis-cli "$@"; }
titulo() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
chaves() { redis KEYS "$1" | sed 's/^/    /' | sort; }

titulo "0. Estado inicial do cache"
redis DEL "$(redis KEYS 'produto*' | tr '\n' ' ')" > /dev/null 2>&1 || true
echo "  versao do namespace: $(redis GET produtos:versao || echo '(vazia = 1)')"
echo "  chaves de produto:"; chaves 'produto*'

titulo "1. Duas listagens diferentes (MISS, depois popula)"
curl -sf "$BASE/produtos?limit=3" > /dev/null
curl -sf "$BASE/produtos?estoque_baixo_ate=5" > /dev/null
curl -sf "$BASE/produtos/1" > /dev/null
echo "  chaves agora:"; chaves 'produto*'

titulo "2. A mesma listagem de novo: agora e HIT"
echo "  (procure 'cache hit' no log da API)"
curl -sf "$BASE/produtos?limit=3" > /dev/null
docker compose logs api --since 5s 2>/dev/null | grep -o '"message": "cache hit".*chave": "[^"]*"' | tail -1 | sed 's/^/    /'

titulo "3. Uma ESCRITA acontece"
TOKEN=$(curl -sf -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123"}' \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
printf '{"nome": "Item que invalida o cache %s", "preco": 10.00, "quantidade_em_estoque": 500}' "$(date +%s)" \
  | curl -sf -X POST "$BASE/produtos" -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' -d @- > /dev/null
echo "  produto criado."
echo "  versao do namespace subiu para: $(redis GET produtos:versao)"
echo "  chaves apos a escrita:"; chaves 'produto*'
echo
echo "  As chaves da versao antiga continuam na memoria, mas nenhuma consulta"
echo "  vai gerar aquele prefixo de novo: ficaram inalcancaveis. Somem no TTL."

titulo "4. Nova listagem: chave nova, na versao nova"
curl -sf "$BASE/produtos?limit=3" > /dev/null
echo "  chaves agora:"; chaves 'produto*'
