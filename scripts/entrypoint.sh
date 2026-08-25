#!/bin/sh
# Entrypoint da API. Roda as migrações antes de aceitar tráfego e então entrega
# o PID 1 para o comando real (exec), para que SIGTERM chegue ao uvicorn e o
# shutdown seja gracioso.
set -e

# Só o serviço da API migra; o worker sobe com RUN_MIGRATIONS=false.
if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
  echo "[entrypoint] aplicando migrações..."
  alembic upgrade head
  echo "[entrypoint] migrações aplicadas"

  if [ "${RUN_SEED:-true}" = "true" ]; then
    echo "[entrypoint] executando seed..."
    python -m app.seed
  fi
fi

exec "$@"
