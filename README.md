# Prova prática Back-end — Módulo de ERP com agente de IA

Módulo de **Produtos e Estoque** de um ERP, com API REST em FastAPI, consulta
agregada resiliente a três serviços e um **agente de linguagem natural que
funciona sem nenhuma dependência de LLM externo**.

**Renan Carlos Rozin** · [renanrozin1@gmail.com](mailto:renanrozin1@gmail.com) ·
[linkedin.com/in/renan-rozin](https://linkedin.com/in/renan-rozin) ·
[github.com/RenanRozin](https://github.com/RenanRozin)

---

## Subindo tudo com um comando

Pré-requisitos: Docker e Docker Compose. Nada mais — nem Python instalado.

```bash
[ -f .env ] || cp .env.example .env    # não sobrescreve um .env existente
docker compose up --build
```

É só isso. O `entrypoint` aplica as migrações do Alembic e roda o seed antes de a
API aceitar tráfego, então não há passo manual de banco.

> **Se aparecer `password authentication failed for user "erp"`:** a senha do
> Postgres só é gravada na primeira subida, quando o volume é criado. Se o
> `.env` mudou depois disso, a senha do arquivo e a do volume divergem. Recrie
> o volume com `docker compose down -v && docker compose up -d`.
>
> Foi por isso que o comando acima só copia se o `.env` ainda não existir:
> sobrescrever um `.env` que já funcionava é a forma mais fácil de cair nesse erro.

Quando os serviços ficarem saudáveis:

| Endereço | O que é |
|---|---|
| http://localhost:8000/docs | Documentação interativa (Swagger) |
| http://localhost:8000/health/ready | Readiness com estado de Postgres e Redis |
| http://localhost:8000/agente/ferramentas | Catálogo de ferramentas do agente |

**Credenciais do seed:** `admin` / `admin123` (definidas no `.env`).

### Vendo tudo funcionar

Três scripts que demonstram cada parte, com saída legível:

```bash
./scripts/smoke-test.sh     # Partes 3 e 4: CRUD, auth, validação, cache, 13 verificações
./scripts/demo-parte2.sh    # Parte 2: paralelismo, timeout, retry, degradação graciosa
./scripts/demo-parte5.sh    # Parte 5: agente respondendo e recusando o que deve recusar
./scripts/verifica-fila.sh  # Parte 3: prova que o worker processa a fila de verdade
```

Eles esperam a API ficar pronta sozinhos — o `docker compose up` devolve o
prompt quando os containers *subiram*, não quando a aplicação está pronta.

### Rodando os testes

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest              # 56 testes
.venv/bin/ruff check app tests
```

Os testes de integração pulam sozinhos se a stack não estiver no ar, para que a
suíte continue utilizável sem Docker.

---

## Onde está cada resposta

A prova tem 7 partes e 11 questões — **a numeração pula a Questão 5**, indo da 4
direto para a 6. Mantive os números do enunciado para facilitar a conferência.

| Parte | Questão | Resposta |
|---|---|---|
| 1 — Arquitetura | **Q1** Microsserviços de ERP | [docs/01-arquitetura.md](docs/01-arquitetura.md) |
| 1 — Arquitetura | **Q2** Estrutura de camadas | [docs/02-estrutura-fastapi.md](docs/02-estrutura-fastapi.md) |
| 2 — Concorrência | **Q3** asyncio × threading × multiprocessing | [docs/03-concorrencia.md](docs/03-concorrencia.md) |
| 2 — Concorrência | **Q4** Endpoint paralelo *(prática)* | `app/routers/agregado.py` · [detalhes abaixo](#q4--consulta-paralela-com-degradação-graciosa) |
| 3 — API REST | **Q6** CRUD de Produtos *(prática)* | `app/routers/products.py` · [detalhes abaixo](#q6--crud-de-produtos-e-estoque) |
| 4 — Docker | **Q7** Dockerfile e compose *(prática)* | `Dockerfile`, `docker-compose.yml` · [detalhes abaixo](#q7--docker-e-orquestração) |
| 5 — IA | **Q8** Agente sem LLM *(prática)* | `app/agent/` · [detalhes abaixo](#q8--agente-de-linguagem-natural) |
| 5 — IA | **Q9** Design plugável, MCP, guardrails | [docs/09-agente-llm-mcp.md](docs/09-agente-llm-mcp.md) |
| 6 — Perfil | **Q10** Ser alocado para Go | [docs/10-perfil-go.md](docs/10-perfil-go.md) |
| 7 — Portfólio | **Q11** Projetos anteriores | [seção abaixo](#q11--portfólio) |

---

## Stack

| Camada | Escolha | Por quê |
|---|---|---|
| API | FastAPI + Pydantic v2 | Validação e OpenAPI saem do mesmo type hint, sem duplicar contrato |
| Banco | PostgreSQL 16 + SQLAlchemy 2 (async) + asyncpg | Ver justificativa abaixo |
| Migrações | Alembic em modo assíncrono | Mesmo driver da aplicação, sem um segundo DSN para divergir |
| Cache e fila | Redis 7 + `arq` | `arq` é async nativo; ver justificativa abaixo |
| Autenticação | JWT (PyJWT) + bcrypt | Sem `passlib`, que está sem manutenção e quebra com bcrypt 4 |
| Agente | Determinístico + `jsonschema` | Sem provedor externo, como a prova exige |
| Qualidade | pytest, pytest-asyncio, ruff | 56 testes; lint limpo |

---

## Q4 — Consulta paralela com degradação graciosa

`GET /agregado/visao-360` consulta estoque, financeiro e cliente **ao mesmo
tempo**, com timeout e retry por fonte.

O ponto central: `com_resiliencia` (`app/core/resiliencia.py`) **nunca levanta
exceção** — devolve sempre um `Resultado`, com sucesso ou com o motivo da falha.
Como nenhuma corrotina explode, o `asyncio.gather` sempre completa e uma fonte
fora do ar não derruba as outras duas.

Três decisões que valem explicação:

**Retry só no que é transitório.** Timeout e 503 são repetidos; um 4xx sai na
primeira tentativa. Repetir erro permanente é desperdício — e, em escrita não
idempotente, é como se cria cobrança duplicada.

**Backoff exponencial com jitter.** Sem o jitter, todos os clientes que falharam
juntos voltam juntos e derrubam de novo o serviço que estava se recuperando.

**Timeout por tentativa *e* orçamento total.** Esta foi uma correção durante o
desenvolvimento: só com timeout por tentativa, 3 tentativas de 0,5s custavam
1,5s ao usuário — o retry virava a causa da lentidão que deveria evitar. O
`orcamento_total` é o teto que a API promete a quem chama, retentativas
incluídas.

**200 e não 206/207 na resposta parcial:** cliente HTTP costuma tratar qualquer
coisa fora de 2xx como erro e descartar o corpo — jogando fora justamente os
dados que chegaram. A completude vai no corpo (`completo: false`), com o motivo
por fonte, onde é efetivamente usada.

Para ver os seis cenários, incluindo os de falha: `./scripts/demo-parte2.sh`

## Q6 — CRUD de Produtos e Estoque

`GET|POST|PATCH|DELETE /produtos`, com JWT nas rotas de escrita.

### Por que SQLAlchemy 2 assíncrono + asyncpg

Considerei três caminhos: driver puro (`asyncpg` direto), SQLModel, e SQLAlchemy.

Fiquei com **SQLAlchemy 2.0 em modo async** por três razões práticas. Primeira,
integração com Alembic — migração versionada não é opcional num ERP, onde o
esquema evolui por anos e o rollback precisa existir. Segunda, o `Mapped[...]`
da 2.0 dá tipagem estática de verdade, e o editor pega erro de coluna antes do
teste. Terceira, quando a consulta ficar complexa demais para o ORM — e em ERP
sempre fica — dá para descer para SQL puro na mesma sessão e na mesma transação,
sem trocar de ferramenta.

Descartei SQLModel por adicionar uma camada de abstração a mais sobre duas
bibliotecas que já se entendem bem, e driver puro por ter que reimplementar
migração e mapeamento na mão.

### Validação (Pydantic)

Preço não negativo, estoque não negativo, nome nem nulo nem numérico. As regras
estão em `app/schemas/` e são **repetidas como CHECK constraint no banco**
(`app/models/product.py`): validação de aplicação protege do usuário, constraint
protege do script de importação e da migração mal escrita.

Detalhe de domínio: a regra proíbe nome que **é** um número (`"12345"`), não nome
que **contém** número — senão metade de um catálogo industrial seria rejeitada.
`"Parafuso M8 x 40"` é válido.

### Paginação e filtros

`?nome=&preco_min=&preco_max=&estoque_baixo_ate=&ordenar_por=&ordem=&limit=&offset=`

Teto de 100 em `limit`, porque sem ele `limit=1000000` é um jeito legítimo de
derrubar a API. O `ORDER BY` sempre inclui o `id` como desempate: sem coluna
única na ordenação, páginas podem repetir ou pular registros quando há valores
iguais.

### Cache Redis e a estratégia de invalidação

Duas leituras usam cache: o produto por id e a listagem.

- **Registro individual** (`produto:{id}`): invalidação por exclusão direta. Toda
  escrita apaga a chave. Simples e exato.
- **Listagens**: aqui está o problema difícil. A chave depende de filtro,
  ordenação e paginação, então uma escrita afeta um número imprevisível de
  chaves — e não dá para apagá-las uma a uma (`KEYS` trava o Redis; `SCAN` é O(n)
  e não acompanha escrita concorrente).

A solução foi **versionar o namespace**: a chave carrega a versão corrente
(`produtos:v7:<impressão-do-filtro>`) e qualquer escrita faz `INCR` na versão.
As chaves da v7 ficam inalcançáveis no ato — invalidação O(1) — e somem sozinhas
pelo TTL. O custo é ocupar memória com lixo até o TTL expirar: barato e
previsível.

**TTL curto em tudo (60s), como rede de segurança.** Se alguma escrita escapar da
invalidação — script, outro serviço, migração — a inconsistência tem prazo de
validade conhecido em vez de ser permanente.

Duas escolhas mais: a invalidação acontece **depois do commit** (invalidar antes
abre uma janela para outra requisição repovoar o cache com dado velho), e falha
do Redis é registrada e ignorada — cache indisponível vira MISS, não erro 500. A
API continua respondendo direto do Postgres.

### Fila e worker

Toda escrita que deixa um produto no limite de estoque enfileira
`registrar_alerta_estoque_baixo`, processada pelo worker `arq` em outro
container. Há também uma **varredura periódica** (cron a cada 30 min), porque
alerta só por evento perde o produto que ficou parado abaixo do limite sem
sofrer nenhuma escrita.

A tarefa **relê o produto do banco** em vez de confiar no payload: entre
enfileirar e executar pode ter entrado uma reposição, e alertar sobre estoque já
corrigido é ruído que treina o operador a ignorar alerta. Isso a torna
idempotente por construção.

**Por que `arq` e não Celery:** o Celery é o padrão de mercado, mas é síncrono na
raiz — dentro de uma aplicação async, obriga a jogar o enfileiramento para um
thread pool ou manter um segundo cliente Redis bloqueante. O `arq` nasceu
assíncrono e usa o mesmo `redis-py` que a API já usa. A troca é consciente:
abre-se mão do ecossistema do Celery. Com muitos tipos de tarefa, dependência
entre elas e times diferentes consumindo, o Celery — ou um broker com garantia
de durabilidade, como RabbitMQ ou SQS — passaria a valer mais a pena.

Para provar que a fila roda de verdade: `./scripts/verifica-fila.sh`

## Q7 — Docker e orquestração

**Dockerfile multi-stage.** O estágio `builder` instala as dependências num
virtualenv com o compilador C disponível (asyncpg e bcrypt precisam); o estágio
`runtime` copia só o venv pronto. O compilador não vai para a imagem final —
imagem menor e menos superfície de ataque. O container roda como **usuário sem
privilégios**.

**Compose** com `api`, `worker`, `db` e `redis`. Detalhes que importam:

- **Healthcheck real em todos.** `pg_isready` no Postgres, `PING` no Redis,
  requisição HTTP na API. O `depends_on` usa `condition: service_healthy`, então
  a API só sobe quando o banco realmente aceita conexão — em vez do `sleep 10`
  que funciona na máquina de quem escreveu e falha na do avaliador.
- **Liveness e readiness separados.** `/health/live` não toca em dependência
  externa: um liveness que consulta o banco faz o orquestrador matar a API
  quando quem caiu foi o banco — e reiniciar a API não conserta banco.
  `/health/ready` verifica Postgres e Redis e responde **503** quando degradado.
- **Só a API roda migração** (`RUN_MIGRATIONS=false` no worker): dois processos
  executando `alembic upgrade` ao mesmo tempo é corrida garantida.
- **`exec` no entrypoint**, para o SIGTERM chegar ao uvicorn e o shutdown ser
  gracioso.
- **Segredos via `.env`**, que está no `.gitignore`. O `.env.example` é o
  versionado. O compose falha explicitamente se `POSTGRES_PASSWORD` não estiver
  definida, em vez de subir com senha padrão.
- **`docker-compose.override.yml`** aplica o modo de desenvolvimento (bind mount
  e `--reload`) automaticamente. Para o modo de produção, sobe-se com
  `-f docker-compose.yml` explicitamente.

## Q8 — Agente de linguagem natural

`POST /agente/perguntar` recebe texto livre e devolve JSON estruturado. Sem
OpenAI, sem Anthropic, sem modelo local — interpretação determinística.

```bash
curl -s -X POST localhost:8000/agente/perguntar \
  -H 'Content-Type: application/json' \
  -d '{"texto": "quais produtos estão com estoque abaixo de 10 unidades?"}'
```

```json
{
  "status": "respondido",
  "resposta": "7 produtos estao com estoque ate 10 unidades: Sensor indutivo PNP (0), ...",
  "interpretacao": {
    "ferramenta": "consultar_estoque_baixo",
    "argumentos": {"limite": 10},
    "confianca": 0.95,
    "estrategia": "regras",
    "justificativa": "Expressao de estoque insuficiente reconhecida; limite=10"
  },
  "dados": { "limite": 10, "total": 7, "produtos": [ ... ] },
  "trilha": [ ... ]
}
```

### A arquitetura é a resposta, não o NLP

O enunciado diz explicitamente que o que importa é o padrão de arquitetura. Então
o projeto foi feito para que **trocar as regras por um LLM real seja uma mudança
de uma peça só**:

```
app/agent/
├── tools.py         # ferramentas em JSON Schema (formato de function calling e MCP)
├── planner.py       # Protocol + PlannerPorRegras  ← a única peça que muda
├── executor.py      # validação e guardrails       ← vale para qualquer planner
├── orchestrator.py  # junta tudo e narra
└── schemas.py       # contratos
```

- **`Planner` é um `Protocol`.** Qualquer objeto com
  `planejar(pergunta) -> Interpretacao` serve — regras, LLM ou híbrido.
- **As ferramentas já saem nos dois formatos** que um LLM ou um servidor MCP
  consomem. Confira em `GET /agente/ferramentas`.
- **Os guardrails estão no executor, não no planner.** É a decisão mais
  importante do módulo: a defesa continua valendo quando quem planeja for um
  modelo que pode alucinar.

### Guardrails, na ordem de aplicação

1. **Lista fechada de ferramentas** — nunca há SQL nem nome de função vindo do
   texto do usuário.
2. **Limiar de confiança (0.6)** — abaixo disso, o agente diz que não entendeu.
3. **Validação por JSON Schema** — argumento inventado ou de tipo errado é
   barrado antes de virar consulta.
4. **Confirmação para ação destrutiva** — remoção devolve a intenção e espera
   `confirmar: true`.

Dois comportamentos que valem ver rodando (`./scripts/demo-parte5.sh`):

- `"qual a previsão do tempo para amanhã?"` → `nao_compreendido`, com sugestões.
- `"apaga tudo"` → detecta a intenção destrutiva, **não encontra alvo**, atribui
  confiança 0.35 e é barrado pelo limiar. Não chuta um id.

### Os limites destas regras, ditos com todas as letras

Casamento por palavra-chave não entende negação (*"produtos que **não** estão em
falta"*), não resolve referência ao turno anterior (*"e os mais caros que
esses?"*) e não lida com pergunta composta. Um LLM resolve os três — e é
exatamente por isso que a fronteira entre *entender* e *executar* está onde está.

---

## O que eu faria com mais tempo

O enunciado pede para descrever o que ficou de fora. Em ordem de prioridade:

**Autorização por papel, não só autenticação.** Hoje qualquer usuário
autenticado escreve. Um ERP precisa de papéis (`estoquista`, `financeiro`,
`gerente`) e de permissão por operação. É o que mais falta para isto virar
produção — e vale ainda mais no agente, onde a ferramenta só deveria aparecer no
catálogo se aquele usuário puder executá-la pela tela.

**Exclusão lógica no lugar da física.** `DELETE` remove a linha. Num ERP de
verdade, produto referenciado por pedido histórico não pode sumir — o certo é
inativar com data e motivo, preservando o histórico.

**Reserva de estoque com concorrência tratada.** O modelo atual tem saldo, mas não
reserva. A operação real exige `SELECT ... FOR UPDATE` ou lock distribuído no
Redis, e mereceria teste de concorrência de verdade.

**Métricas Prometheus e tracing OpenTelemetry.** O logging estruturado está
pronto; faltam os outros dois sinais descritos na Questão 1. Seria a próxima
coisa que eu faria.

**Rate limiting e idempotência nas escritas.** Chave de idempotência no POST, para
que retry de cliente não gere produto duplicado.

**Migração de estoque para tabela de movimentação.** Saldo como coluna é
simplificação. Em ERP, o saldo correto é derivado do razão de movimentações —
é o que permite auditar e reconstruir.

**Cobertura maior nos caminhos de erro** e uma suíte de avaliação do agente com
perguntas reais coletadas de uso, no formato de regressão descrito na Questão 9.

**CI.** GitHub Actions rodando `ruff` e `pytest` a cada push, e build da imagem.

---

## Q11 — Portfólio

Não tenho repositório público relevante hoje: o código dos meus últimos quatro
anos pertence à empresa onde trabalhei e não pode ser publicado. Então o projeto
mais representativo que posso apresentar é **este próprio repositório**, e
descrevo abaixo o segundo, que é o mais representativo do meu nível técnico
mesmo sem estar público.

### BrasaFlyff — servidor de jogo em C++ (nov/2025 – jul/2026)

**Que problema resolve.** Servidor completo de um MMORPG: arquitetura de quatro
processos independentes (login, cadastro de personagem, mundo e coordenação) se
comunicando por protocolo binário próprio, com persistência em SQL Server.
Trabalhei em portar sistemas de gameplay inteiros entre bases de código
diferentes — conquistas, crafting, caixas de recompensa, ranking de PvP e um
conjunto de minijogos com cerca de 8.300 linhas.

**Principais decisões técnicas.** A que mais me ensinou foi a de persistência: os
sistemas portados salvavam estado em tabelas espalhadas, e o relogar do jogador
perdia progresso de forma intermitente — o pior tipo de bug, porque não se
reproduz sob observação. A solução foi consolidar o estado desses sistemas numa
tabela dedicada, com um único ponto de leitura e escrita no ciclo de vida do
personagem. Também desenhei mecânicas de chefe dirigidas por configuração
externa (JSON) em vez de código, para que ajuste de balanceamento não exigisse
recompilar quatro binários.

**O que eu faria diferente hoje.** Duas coisas. Primeiro, **teste automatizado
desde o início**: validei quase tudo subindo o servidor e jogando, o que é lento
e não pega regressão. Hoje eu isolaria a lógica de gameplay da camada de rede e
de banco justamente para poder testá-la — foi a mesma preocupação que guiou a
estrutura em camadas desta prova. Segundo, **teria versionado o esquema do banco
desde o primeiro dia**, com migrações; reconstruir a ordem das alterações depois
custou muito mais caro do que teria custado manter.

### Este repositório

Vale como amostra do que considero código bem-feito: separação de camadas com
motivo declarado, decisões técnicas justificadas por escrito, tratamento
explícito de falha (timeout, retry, degradação, invalidação de cache) e testes
que rodam em segundos por não dependerem de infraestrutura.

---

## Uso de IA

Usei o **Claude (Claude Code)** como par de programação ao longo de todo o
desafio, e considero relevante detalhar em que medida:

**O que foi gerado com apoio da IA:** a maior parte do código de infraestrutura e
do esqueleto — configuração, sessão do SQLAlchemy, Dockerfile, compose, o
boilerplate dos routers e schemas — e a primeira redação dos documentos em
`docs/`. Também os scripts de demonstração.

**O que foi decidido por mim:** as escolhas técnicas que a prova pede para
justificar. A estratégia de invalidação de cache por versionamento de namespace,
a opção por `arq` no lugar do Celery, a separação entre planner e executor no
agente com os guardrails do lado do executor, o formato duplo do catálogo de
ferramentas (function calling e MCP), e o recorte do que ficou de fora por
tempo.

**O que corrigi durante o desenvolvimento** — e que vale mais que o resto, porque
mostra onde a revisão pegou problema real:

- O timeout do agregador era só por tentativa, o que fazia 3 retentativas de 0,5s
  custarem 1,5s ao usuário. Acrescentei o **orçamento total de tempo**.
- O readiness respondia 200 mesmo degradado — inútil como probe. Passou a
  responder **503**.
- O `echo` do SQLAlchemy ligado junto com o `DEBUG` duplicava cada linha de log.
  Separei em uma variável própria.
- A tarefa da fila confiava no payload; passei a **reler o produto do banco**, o
  que a tornou idempotente e evita alerta sobre estoque já regularizado.
- Um teste de integração pulava em silêncio quando a stack demorava a responder —
  o pior tipo de teste, o que finge estar tudo bem.

**O que é meu e não poderia ser gerado:** as respostas das Questões 10 e 11. A
Q11 descreve projetos e decisões minhas. A Q10 foi construída a partir das
minhas respostas sobre como eu de fato reagiria à alocação, como eu aprendi C++
na prática e qual é a minha preocupação real — o texto foi redigido com apoio de
IA, mas as posições são minhas e eu as sustento numa conversa.

Minha posição sobre isso, já que a vaga é de back-end com foco em IA: uso IA como
uso qualquer ferramenta que aumenta a velocidade — e a responsabilidade pelo que
é entregue continua sendo inteiramente minha. Todo trecho deste repositório eu
consigo explicar e defender.
