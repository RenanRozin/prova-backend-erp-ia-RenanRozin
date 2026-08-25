#!/usr/bin/env bash
# Espera a API ficar pronta. Usado pelos demos e util logo apos `docker compose up`:
# o compose devolve o prompt quando os containers SUBIRAM, nao quando a aplicacao
# terminou de migrar o banco e esta aceitando requisicao.
set -euo pipefail
BASE="${1:-http://localhost:8000}"
LIMITE="${2:-60}"

printf 'aguardando %s ' "$BASE"
for _ in $(seq 1 "$LIMITE"); do
  if curl -sf -o /dev/null "$BASE/health/ready" 2>/dev/null; then
    printf ' pronta\n'
    exit 0
  fi
  printf '.'
  sleep 1
done

printf '\nERRO: a API nao ficou pronta em %ss\n' "$LIMITE" >&2
echo "Verifique com: docker compose ps && docker compose logs api" >&2
exit 1
