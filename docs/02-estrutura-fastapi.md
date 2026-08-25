# Questão 2 — Estrutura de um serviço FastAPI de médio/grande porte

A estrutura abaixo é a que este repositório usa de verdade. Preferi responder com
o código que está aqui em vez de um diagrama ideal: dá para conferir cada
afirmação abrindo o arquivo.

```
app/
├── main.py              # factory da aplicação e registro dos routers
├── core/                # infraestrutura transversal (não conhece o domínio)
│   ├── config.py        # env vars validadas pelo Pydantic no boot
│   ├── db.py            # engine, sessão, Base declarativa
│   ├── redis_client.py  # pool único por processo
│   ├── cache.py         # política de cache (aside + versionamento)
│   ├── logging.py       # logging estruturado em JSON
│   ├── security.py      # hash de senha e JWT
│   └── resiliencia.py   # timeout, retry, orçamento de tempo
├── models/              # tabelas (SQLAlchemy) — a forma do dado no banco
├── schemas/             # contratos de API (Pydantic) — a forma do dado na borda
├── repositories/        # acesso a dados; a única camada que escreve consulta
├── services/            # regra de negócio, transação, orquestração
├── routers/             # HTTP: rota, status code, dependências
├── workers/             # produtor e consumidor da fila
└── agent/               # domínio próprio do agente (Parte 5)
tests/
```

## Por que cada camada existe

### `models` e `schemas` separados

É a separação que mais gera pergunta, e a que mais paga. São **duas formas
diferentes do mesmo conceito**: `Product` descreve a tabela; `ProductCreate`,
`ProductUpdate` e `ProductRead` descrevem o que entra e o que sai da API.

Sem essa separação acontecem três coisas, todas ruins: o cliente consegue mandar
`id` e `data_criacao` num POST; qualquer coluna nova vaza para a resposta pública
sem ninguém decidir (inclusive `hashed_password`); e mudar o banco vira mudança
quebrando contrato de API.

Com a separação, o schema de saída é uma **decisão explícita** sobre o que é
público.

### `repositories` — o único lugar com consulta

Concentra `select`, `join` e paginação. O ganho real não é "trocar de banco um
dia" — isso quase nunca acontece. Os ganhos que acontecem toda semana são:

- a consulta complexa mora num lugar só, em vez de replicada em três endpoints
  com variações sutis;
- o service pode ser testado com um duplo em memória, sem subir Postgres;
- otimizar uma consulta é uma mudança local e auditável.

### `services` — onde a regra de negócio mora

É a camada que conhece transação, cache e fila ao mesmo tempo, e a única que
conhece. Duas regras que sigo à risca:

1. **Service não levanta `HTTPException`.** Levanta erro de domínio
   (`ProdutoNaoEncontrado`). Quem traduz para status HTTP é o router. Sem isso, a
   mesma regra deixa de funcionar quando quem chama é o worker da fila ou o
   agente — que não têm requisição HTTP nenhuma. Neste projeto o
   `ProductService` é usado pelos dois caminhos.
2. **Service não recebe `Request`.** Recebe dados. Assim o teste não precisa
   simular um ciclo HTTP.

### `routers` — só a borda

Três responsabilidades: declarar o contrato (que o FastAPI transforma em OpenAPI),
resolver dependências e traduzir erro de domínio em status code. Router com regra
de negócio é o começo do endpoint de 300 linhas que ninguém consegue testar nem
reaproveitar.

### `core` — infraestrutura que não conhece o domínio

A dependência aponta **para dentro**: `services` importa de `core`, nunca o
contrário. `core/resiliencia.py` não sabe o que é produto; por isso serve
igualmente ao agregador da Parte 2 e a qualquer integração futura.

## Princípios que inspiraram, e o que eu deixei de fora

**Clean Architecture** — fiquei com a regra de dependência (o de fora conhece o de
dentro, nunca o inverso) e com a inversão nas bordas. **Não** adotei entidades de
domínio puras separadas dos modelos ORM: numa aplicação deste porte, isso dobra o
número de classes e adiciona uma camada de tradução para pagar um benefício que
só aparece em sistema muito maior. Foi uma escolha de custo-benefício, e mudaria
se o domínio ficasse mais rico.

**SOLID**, dos cinco:

- **Responsabilidade única** é o que sustenta a divisão em camadas.
- **Aberto/fechado** e **inversão de dependência** aparecem no ponto mais
  importante do projeto: o `Planner` do agente é um `Protocol`
  (`app/agent/planner.py`). Trocar as regras por um LLM não exige tocar no
  executor, nos guardrails nem nas ferramentas — só entregar outra
  implementação do mesmo contrato.
- **Substituição de Liskov** e **segregação de interface** aparecem menos, porque
  há pouca hierarquia. Prefiro composição.

**DDD leve** — adotei a linguagem ubíqua e as fronteiras de contexto, sem o
ferramental pesado. Concretamente: **o domínio é escrito em português**
(`quantidade_em_estoque`, `ProdutoDuplicado`, `consultar_estoque_baixo`) e a
infraestrutura em inglês (`repositories`, `settings`, `engine`). Parece detalhe,
mas em ERP não é: quando o código usa a mesma palavra que o usuário do sistema,
some a camada de tradução mental em toda conversa entre quem programa e quem
opera. Não adotei agregados formais, repositórios genéricos nem event sourcing —
seria cerimônia sem retorno neste tamanho.

## O efeito prático na testabilidade

A estrutura acima é o que permite a suíte deste projeto rodar em **menos de 4
segundos**:

| O que se testa | Precisa de quê | Arquivo |
|---|---|---|
| Validação de domínio | nada | `tests/test_validacao_produto.py` |
| Política de retry e timeout | nada | `tests/test_resiliencia.py` |
| Interpretação e guardrails do agente | nada | `tests/test_agente.py` |
| Fluxo completo pela API | stack no ar (pula sozinho se não estiver) | `tests/test_integracao_api.py` |

Três dos quatro arquivos não sobem banco, não sobem Redis e não abrem porta. Isso
não é sorte: é consequência de a regra de negócio não estar amarrada ao
framework nem ao driver. Teste que precisa de Docker para rodar é teste que
ninguém executa antes do commit — e suíte que ninguém roda não protege nada.
