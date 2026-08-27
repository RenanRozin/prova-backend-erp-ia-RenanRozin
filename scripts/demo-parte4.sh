#!/usr/bin/env bash
# Mostra as decisoes da Parte 4 na pratica: tamanho da imagem multi-stage,
# healthchecks reais e a diferenca entre liveness e readiness.
set -euo pipefail
BASE="${1:-http://localhost:8000}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
"$AQUI/aguarda-api.sh" "$BASE" > /dev/null

titulo() { printf '\n\033[1m== %s ==\033[0m\n' "$1"; }
probe() { curl -s -o /tmp/probe.out -w '%{http_code}' "$BASE/$1"; }

titulo "1. Imagem final (multi-stage: sem compilador C)"
docker images prova-backend-erp-ia-api --format '    {{.Repository}}  {{.Size}}'
echo "    usuario do processo: $(docker compose exec -T api whoami)"

titulo "2. Healthchecks declarados no compose"
docker compose ps --format 'table {{.Service}}\t{{.Status}}'

titulo "3. Com tudo no ar"
echo "    /health/live  -> $(probe health/live)   $(cat /tmp/probe.out)"
echo "    /health/ready -> $(probe health/ready)  $(cat /tmp/probe.out)"

titulo "4. Derrubando o Redis de proposito"
docker compose stop redis > /dev/null 2>&1
sleep 3
echo "    /health/live  -> $(probe health/live)   $(cat /tmp/probe.out)"
echo "    /health/ready -> $(probe health/ready)  $(cat /tmp/probe.out)"
echo
echo "    Liveness continua 200: o processo esta vivo, e reiniciar a API"
echo "    nao consertaria o Redis. Readiness caiu para 503: o orquestrador"
echo "    tira esta instancia do balanceador ate a dependencia voltar."

titulo "5. E a API ainda responde consulta, sem cache"
echo "    GET /produtos -> $(probe 'produtos?limit=1')"
echo "    (cache indisponivel vira MISS, nao erro 500)"

titulo "6. Subindo o Redis de volta"
docker compose start redis > /dev/null 2>&1
sleep 5
echo "    /health/ready -> $(probe health/ready)  $(cat /tmp/probe.out)"
