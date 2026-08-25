# Questão 10 — Ser alocado para desenvolver em Go

## Como eu reagiria

Bem, e com interesse real — mas não por entusiasmo automático com tecnologia
nova. É por uma convicção que eu já testei na prática: **linguagem é ferramenta,
e quem se define por uma delas limita o próprio alcance.**

Falo isso com um caso concreto. Meus últimos anos foram em Python e Odoo, mas
em paralelo eu trabalhei num servidor de jogo em **C++** — arquitetura de quatro
processos se comunicando, persistência em SQL Server, sistemas de gameplay
inteiros portados entre bases de código diferentes. C++ não tem quase nada a ver
com Python: gerenciamento manual de memória, compilação, um modelo mental
completamente outro. Aprendi porque o problema exigia, não porque estava na moda.

Go, vindo de Python, é uma distância bem menor do que essa.

O que eu faria antes de escrever qualquer coisa seria uma pergunta, e ela não é
resistência — é diligência: **quais números levaram a essa conclusão?** Não para
contestar, mas porque saber o gargalo real (throughput de ingestão? latência de
cauda? custo de infraestrutura? tempo de GC?) muda como eu projeto o serviço. Se
a decisão já veio de um benchmark, ótimo — quero ver, porque ele é a
especificação de desempenho do que vou construir.

## Go é uma escolha razoável aqui? Sim.

Para ingestão e processamento de alto volume de eventos com baixa latência, é
uma das melhores escolhas disponíveis, e por motivos técnicos concretos:

| Característica | Por que importa neste caso |
|---|---|
| **Goroutines** | Concorrência barata de verdade, com paralelismo real de CPU — sem o GIL. É exatamente o que falta ao Python no cenário descrito. |
| **Coletor de lixo com pausas curtas** | Pausa na casa do sub-milissegundo. Em latência de cauda (p99), é a diferença entre atender o SLA e não atender. |
| **Binário único, estático** | Container `FROM scratch` com poucos MB, sem interpretador nem árvore de dependências. Deploy e escala horizontal ficam triviais. |
| **Tipagem estática compilada** | Erro de tipo aparece no build, não em produção às três da manhã. Em pipeline de ingestão, onde ninguém está olhando a tela, isso vale muito. |
| **Biblioteca padrão forte para rede** | HTTP, JSON, concorrência e contexto de cancelamento vêm na caixa. |
| **Previsibilidade de recursos** | Consumo de memória e CPU muito mais estável sob carga que o de um processo Python equivalente. |

Também gosto de uma característica que costuma ser criticada: **Go é uma
linguagem pequena**. Poucas construções, um jeito idiomático de fazer cada coisa,
formatação padronizada pelo `gofmt`. Isso reduz a variação de estilo entre
pessoas e encurta o tempo até alguém novo conseguir manter o código — o que
importa mais num serviço de infraestrutura do que expressividade.

## O que eu levantaria na discussão — sem discordar da escolha

Concordo com Go para o cenário. Mas eu colocaria três pontos na mesa, porque o
custo de uma segunda linguagem não é técnico, é organizacional:

1. **O custo é operacional, não de sintaxe.** Duas stacks significam dois
   pipelines de CI, dois padrões de observabilidade, duas formas de configurar,
   dois ecossistemas de biblioteca. Se só uma pessoa souber Go, criou-se um
   ponto único de falha humano. Isso se resolve com decisão consciente — mais de
   uma pessoa envolvida desde o começo, padrões comuns de log e métrica entre os
   serviços — e não ignorando.

2. **Vale confirmar onde está o gargalo.** Em muito sistema que eu vi, o limite
   não estava na linguagem: estava no banco, na serialização, em commit por
   evento em vez de lote, ou em índice faltando. Trocar a linguagem sem isso
   resolvido significa reescrever o gargalo em Go e continuar com ele. Se a
   medição já foi feita e aponta para o runtime, Go é a resposta certa.

3. **Fronteira bem escolhida.** Um serviço com contrato claro — consome do
   broker, valida, persiste, publica — é ótimo candidato. O que eu evitaria é
   espalhar Go por regra de negócio compartilhada com o resto do ERP, onde a
   duplicação de lógica entre linguagens vira dívida permanente.

Se, ainda assim, eu discordasse tecnicamente, o argumento que eu construiria
seria por **medição comparativa**: um protótipo dos dois lados com carga real,
comparando p99, throughput, consumo e custo de infraestrutura. Discussão de
linguagem sem número vira preferência pessoal disfarçada de argumento técnico —
e eu não quero ganhar esse tipo de discussão, quero acertar a decisão.

## Como eu me organizaria para entregar com qualidade sem experiência prévia

Foi exatamente o que fiz com C++, então o plano não é hipotético.

**Primeira semana — fundamentos e o modelo mental.**
Tour of Go e Effective Go, os dois inteiros. Foco em onde Go *não* se parece com
Python: erro como valor de retorno em vez de exceção, interfaces implícitas,
ponteiro e valor, `defer`, e o pacote `context` para cancelamento e prazo. Tentar
escrever Python com sintaxe de Go é o erro clássico de quem migra, e produz
código que compila e ninguém do time reconhece.

**Segunda semana — concorrência, que é o motivo de estarmos usando Go.**
Goroutines, canais, `select`, `sync`, e principalmente os padrões: worker pool,
fan-in/fan-out, pipeline com cancelamento, e o *race detector* (`go test -race`)
ligado desde o primeiro dia.

**Em paralelo, desde o começo — construir de verdade.**
Um consumidor pequeno do pipeline real, com teste, métrica e log no padrão da
casa. Aprender lendo é metade; a outra metade é errar em código que roda.

**O que eu faria questão de pedir:** revisão de código de alguém com experiência
em Go nas primeiras semanas, mesmo que seja de fora do time. Sem isso, eu
entregaria algo que funciona mas não é idiomático — e código não idiomático em
linguagem nova é dívida que o time inteiro paga depois.

**E o que eu levaria comigo do Python:** as partes que não mudam de linguagem —
desenho de camada, teste como parte do desenvolvimento, log estruturado,
observabilidade, cuidado com concorrência e com o que acontece quando uma
dependência cai. É a maior parte do trabalho, e ela viaja junto.
