# Questão 3 — asyncio, threading e multiprocessing

## A pergunta que decide qual usar

Só existe uma: **o processo está esperando ou está calculando?**

Esperando (rede, disco, banco) é I/O-bound; calculando é CPU-bound. Essa
distinção manda mais do que qualquer preferência, porque ela decide se o GIL
atrapalha ou não.

O **GIL** garante que só uma thread execute bytecode Python por vez num
interpretador. Ele é liberado durante operação de I/O — por isso threads ajudam
quem espera e não ajudam quem calcula.

## asyncio — concorrência cooperativa, uma thread só

Um event loop alterna entre tarefas nos pontos de `await`. Não há paralelismo:
há **muita espera acontecendo ao mesmo tempo**.

**Quando uso:** I/O-bound com bibliotecas async disponíveis — HTTP (`httpx`),
Postgres (`asyncpg`), Redis (`redis.asyncio`). É a base deste projeto inteiro.

**Vantagem:** milhares de operações simultâneas com um custo de memória
irrisório. Uma corrotina esperando custa alguns KB; uma thread esperando custa
memória de pilha e troca de contexto do sistema operacional.

**Custo:** basta **uma** chamada bloqueante para travar o loop inteiro — e com
ele todas as outras requisições do processo. É a armadilha da seção final.

**Exemplo de ERP:** a tela de detalhe do pedido precisa de estoque, situação
financeira e cadastro do cliente. Em série, o tempo é a soma; com
`asyncio.gather`, é o máximo entre elas.

> Implementado na Questão 4: `app/routers/agregado.py`. Medido nos demos: ~0,1s
> em paralelo contra ~0,5s que a soma daria.

## threading — concorrência preemptiva, várias threads

O sistema operacional alterna as threads quando quer. Também não dá paralelismo
de CPU (por causa do GIL), mas dá concorrência sem precisar que a biblioteca
seja async.

**Quando uso:** I/O-bound com biblioteca **síncrona que não tem versão async** —
o caso mais comum em ERP, porque driver de sistema legado raramente tem.

**Exemplo de ERP:** integração com o TOTVS Datasul via driver ODBC síncrono. Não
existe versão async; embrulhar em thread é o único jeito de não travar o loop:

```python
resultado = await asyncio.to_thread(consulta_odbc_bloqueante, parametros)
```

**Cuidado:** estado compartilhado entre threads precisa de lock, e é onde nascem
os bugs que só aparecem em produção sob carga, uma vez por semana, sem se
reproduzir na máquina de ninguém. Prefiro passar dado por fila a compartilhar
memória.

## multiprocessing — paralelismo de verdade

Processos separados, cada um com seu interpretador e seu GIL. É o único que usa
mais de um núcleo para código Python.

**Quando uso:** CPU-bound. E só.

**Custo:** cada processo carrega o interpretador inteiro na memória, e os dados
precisam ser serializados para atravessar a fronteira. Para tarefa pequena, o
custo de comunicação é maior que o ganho.

**Exemplo de ERP:** recálculo de custo de produto numa estrutura de manufatura —
explodir a árvore de componentes (BOM) de milhares de itens, aplicar rateio de
mão de obra e overhead nível a nível. É aritmética pura sobre muitos itens, e
particiona bem: cada worker pega uma faixa de produtos.

Foi um caso que enfrentei de verdade: o cálculo de custo de um configurador de
produto rodando sobre estrutura explodida. Em processo único, ficava preso num
núcleo enquanto os outros onze estavam ociosos.

> Nota: em muitos casos o melhor "multiprocessing" é **não usar Python para o
> laço quente**. `numpy`/`pandas` já liberam o GIL em operação vetorizada, e
> agregação pesada em cima de dado que já está no Postgres costuma ser mais
> rápida em SQL do que trazendo tudo para a aplicação. Vale medir antes de
> paralelizar.

## Resumo

| Critério | asyncio | threading | multiprocessing |
|---|---|---|---|
| Paralelismo real de CPU | não | não | **sim** |
| Custo por unidade | baixíssimo | médio | alto |
| Escala típica | milhares | dezenas | núcleos disponíveis |
| Troca de contexto | cooperativa (`await`) | preemptiva (SO) | processos do SO |
| Melhor para | I/O com libs async | I/O com libs síncronas | CPU |
| Risco principal | um bloqueio trava tudo | condição de corrida | custo de serialização |

## Os três cenários do enunciado

| Cenário | Escolha | Por quê |
|---|---|---|
| Chamar 3 APIs externas | **asyncio** | Espera pura. `gather` resolve com uma linha e custo irrisório. |
| Processar um CSV grande | **depende do gargalo** | Se é ler e gravar no banco: I/O, então async com inserção em lote. Se é transformar e validar linha a linha com regra pesada: CPU, então multiprocessing por blocos. **Medir antes de decidir** — a intuição erra muito aqui. |
| Gerar um relatório pesado em PDF | **multiprocessing**, e fora da requisição | Renderização é CPU-bound. Em ERP, a resposta certa nem é "qual primitiva": é **fila**. O endpoint aceita, devolve 202 com um id, e um worker gera. Relatório síncrono é o que faz gateway estourar timeout em 30s e o usuário clicar cinco vezes, gerando cinco relatórios. |

## A armadilha que realmente derruba ERP em produção

No FastAPI, `def` e `async def` têm comportamentos diferentes:

- endpoint com **`def`** roda num **thread pool** — chamada bloqueante ali é
  segura;
- endpoint com **`async def`** roda **no event loop** — uma chamada bloqueante
  ali congela **todas** as requisições do processo, não só a dela.

```python
@app.get("/relatorio")
async def relatorio():
    dados = consulta_odbc_bloqueante()   # trava o servidor inteiro
    return processa(dados)
```

O sintoma é traiçoeiro: funciona perfeitamente em desenvolvimento, com um
usuário. Em produção, com trinta pessoas, a aplicação inteira engasga a cada
consulta ao legado — e o gráfico de latência não aponta para o culpado, porque
todas as rotas ficam lentas ao mesmo tempo.

As correções: `asyncio.to_thread` para o trecho bloqueante, ou declarar o
endpoint como `def` e deixar o FastAPI cuidar do thread pool.

## Nota sobre o futuro

As versões recentes do CPython trazem a construção **free-threaded**, sem GIL, e
os **subinterpretadores** com GIL próprio. Isso tende a mudar a resposta da
coluna "paralelismo real de CPU" para threads. Ainda assim, para trabalho
I/O-bound o asyncio continua sendo o modelo mais econômico — e o motivo não é o
GIL, é o custo de uma thread comparado ao de uma corrotina.
