# Questão 10 — Ser alocado para desenvolver em Go

## Como eu reagiria

Com animação, e sem ressalva nenhuma na primeira reação. Eu gosto de aprender
linguagem nova, e tenho uma convicção que já testei na prática: **linguagem é
ferramenta, e quem se define por uma delas limita o próprio alcance.**

Falo isso com um caso concreto. Meus últimos anos foram em Python e Odoo, mas em
paralelo eu trabalhei num servidor de jogo em **C++** — arquitetura de quatro
processos se comunicando, persistência em SQL Server, sistemas de gameplay
inteiros portados entre bases de código diferentes. Eu não tinha experiência
prévia com C++. Aprendi porque o problema exigia, e C++ está muito mais longe do
Python do que Go está: gerenciamento manual de memória, compilação, um modelo
mental completamente outro.

Então a pergunta "e se você não tiver experiência em Go?" tem, para mim, uma
resposta empírica: já aconteceu, com uma linguagem mais difícil, e funcionou.

## Go é uma escolha razoável para esse cenário? Sim.

Para ingestão e processamento de alto volume de eventos com baixa latência, é uma
das melhores escolhas disponíveis, e por motivos concretos:

| Característica | Por que importa neste caso |
|---|---|
| **Goroutines** | Concorrência barata com paralelismo real de CPU, sem o GIL. É exatamente o que falta ao Python no cenário descrito. |
| **Coletor de lixo com pausas curtas** | Pausa na casa do sub-milissegundo. Em latência de cauda (p99), é a diferença entre atender o SLA e não atender. |
| **Binário único, estático** | Container com poucos MB, sem interpretador nem árvore de dependências. Deploy e escala horizontal ficam triviais. |
| **Tipagem estática compilada** | Erro de tipo aparece no build. Em pipeline de ingestão, onde ninguém está olhando a tela, isso vale muito. |
| **Biblioteca padrão forte para rede** | HTTP, JSON, concorrência e cancelamento vêm na caixa. |
| **Previsibilidade de recursos** | Consumo de memória e CPU muito mais estável sob carga que o de um processo Python equivalente. |

Também gosto de uma característica que costuma ser criticada: **Go é uma
linguagem pequena**. Poucas construções, um jeito idiomático de fazer cada coisa,
formatação padronizada pelo `gofmt`. Isso reduz a variação de estilo entre
pessoas e encurta o tempo até alguém novo conseguir manter o código — o que
importa mais num serviço de infraestrutura do que expressividade.

## O que eu levantaria na discussão — sem discordar da escolha

Concordo com Go para o cenário. Mas levaria três pontos para a conversa, porque o
custo de uma segunda linguagem não é técnico, é organizacional:

1. **Eu ia querer ver os números.** Não para contestar a decisão, e sim porque
   saber o gargalo real — throughput? latência de cauda? custo de
   infraestrutura? tempo de GC? — muda como eu projeto o serviço. Se a decisão
   já veio de um benchmark, melhor ainda: ele é a especificação de desempenho do
   que vou construir.

2. **O custo é operacional, não de sintaxe.** Duas stacks significam dois
   pipelines de CI, dois padrões de observabilidade, dois ecossistemas de
   biblioteca. E se só uma pessoa souber Go, criou-se um ponto único de falha
   humano. Isso se resolve com decisão consciente — mais de uma pessoa envolvida
   desde o começo, padrões comuns de log e métrica entre os serviços — e não
   ignorando.

3. **Fronteira bem escolhida.** Um serviço com contrato claro (consome do broker,
   valida, persiste, publica) é ótimo candidato. O que eu evitaria é espalhar Go
   por regra de negócio compartilhada com o resto do ERP, onde a duplicação de
   lógica entre linguagens vira dívida permanente.

Se, mesmo assim, eu discordasse tecnicamente, o argumento que eu construiria
seria por **medição comparativa**: um protótipo dos dois lados com carga real,
comparando p99, throughput, consumo e custo. Discussão de linguagem sem número
vira preferência pessoal disfarçada de argumento técnico — e eu não quero ganhar
esse tipo de discussão, quero acertar a decisão.

## Como eu me organizaria para entregar com qualidade

Vou responder com o método que eu de fato usei no C++, e não com um cronograma
de estudos que soaria bem mas não é como eu aprendo.

**Eu aprendo construindo e quebrando.** Documentação, para mim, funciona como
consulta e não como etapa inicial — eu preciso de código rodando na frente para
que o conceito faça sentido. Então eu começaria pegando uma fatia pequena e real
do pipeline, com contrato claro, e entregaria ela de ponta a ponta: consumir,
validar, persistir, publicar, com teste e métrica desde o começo.

**E aprendo lendo o código que já existe.** Foi assim que peguei o idioma do C++:
lendo a base existente e imitando os padrões dela, em vez de inventar os meus. Em
Go isso é ainda mais eficiente, porque a comunidade é bastante uniforme sobre o
que é idiomático — dá para aprender muito lendo a biblioteca padrão, que é escrita
com esse cuidado.

**Uso IA e comunidade como par de programação**, para destravar o que não entendo
e para pedir explicação de trecho que não está claro. Com uma ressalva que eu
faço questão de dizer, porque é justamente o meu ponto de atenção: **IA produz
código não idiomático com muita confiança.** Ela resolve o problema e me ensina o
que a linguagem faz — mas não substitui alguém que conheça a convenção da casa.

### A minha preocupação real, e como eu a trataria

Sendo honesto: **o que me preocuparia não é aprender a sintaxe, é entregar código
que funciona mas não é idiomático.** Sintaxe se aprende em dias. Escrever Python
com sintaxe de Go é o erro clássico de quem migra, e produz código que passa nos
testes e que ninguém do time reconhece como Go — dívida que o time inteiro paga
depois, e que eu teria dificuldade de perceber sozinho justamente por ser novo.

Três coisas que eu faria contra isso, na ordem:

1. **Pedir revisão de código de alguém com experiência em Go** nas primeiras
   semanas, mesmo que seja de fora do time. É a correção mais barata e a mais
   eficaz, e eu pediria explicitamente — não esperaria que acontecesse sozinho.
2. **Ligar tudo que a linguagem oferece de verificação automática**: `gofmt`,
   `go vet`, um linter como o `golangci-lint`, e o **race detector**
   (`go test -race`) desde o primeiro teste de concorrência. Em Go, boa parte da
   convenção é verificável por ferramenta — é de graça e eu usaria desde o
   primeiro commit.
3. **Focar o estudo dirigido no que não se parece com Python**, porque é ali que
   mora o não idiomático: erro como valor de retorno em vez de exceção,
   interfaces implícitas, ponteiro e valor, `defer`, e o `context` para
   cancelamento e prazo. E, como Go foi escolhido justamente por concorrência,
   os padrões dela: worker pool, fan-in/fan-out, pipeline com cancelamento.

### O que eu levo comigo do Python

A maior parte do trabalho não muda de linguagem: desenho de camadas, teste como
parte do desenvolvimento, log estruturado, observabilidade, cuidado com
concorrência e com o que acontece quando uma dependência cai. Isso viaja junto —
e é o que me faz achar que a curva seria mais curta do que parece.
