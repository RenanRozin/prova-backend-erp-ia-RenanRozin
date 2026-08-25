"""Tradução de linguagem natural em chamada de ferramenta.

## O ponto de extensão da arquitetura

Planner é o **único** componente que precisa mudar para trocar regras por um LLM
de verdade. Ele recebe texto e devolve uma Interpretacao — nome da ferramenta,
argumentos e confiança. Quem executa, valida e aplica guardrail não sabe se essa
interpretação veio de um regex ou de um modelo de 400 bilhões de parâmetros.

    Protocolo Planner
      |-- PlannerPorRegras   (implementado aqui, sem dependência externa)
      |-- PlannerLLM         (Questão 9: mesmo contrato, chamando tool calling)
      +-- PlannerHibrido     (regras para o caminho quente, LLM para o resto)

## Os limites destas regras, ditos com todas as letras

Casamento por palavra-chave não entende negação ("produtos que NAO estao em
falta"), não resolve referência ao turno anterior ("e os mais caros que esses?")
e não lida com pergunta composta ("estoque baixo e valor total"). Um LLM resolve
os três. O que este módulo demonstra não é NLP: é que a fronteira entre entender
e executar está no lugar certo — e que o resto do sistema não precisa saber quem
entendeu.
"""

import re
import unicodedata
from typing import Protocol

from app.agent.schemas import Interpretacao
from app.agent.tools import REGISTRO


class Planner(Protocol):
    """Contrato que qualquer interpretador precisa cumprir."""

    nome: str

    async def planejar(self, pergunta: str) -> Interpretacao: ...


def normalizar(texto: str) -> str:
    """Minúsculas, sem acento e sem espaço sobrando.

    Sem isso, "está" e "esta" viram padrões diferentes e o usuário que digita sem
    acento — a maioria, no chat de um ERP — não é entendido.
    """
    sem_acento = "".join(
        c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn"
    )
    return re.sub(r"\s+", " ", sem_acento.lower()).strip()


def _para_numero(bruto: str) -> float:
    """Converte número escrito no formato brasileiro.

    Trata "1.500" como mil e quinhentos e "1,99" como um e noventa e nove — a
    confusão entre separador de milhar e decimal é a fonte clássica de erro de
    valor em sistema brasileiro.
    """
    texto = bruto.strip()
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d+)?", texto):  # 1.500 ou 1.500,50
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:  # 1,99
        texto = texto.replace(",", ".")
    return float(texto)


def _numeros(texto: str) -> list[float]:
    return [_para_numero(m) for m in re.findall(r"\d+(?:[.,]\d+)*", texto)]


# Palavras que revelam se o número citado é quantidade ou dinheiro. É o que
# desfaz a ambiguidade de "menos de 100": 100 unidades ou 100 reais?
UNIDADE_QUANTIDADE = r"(unidade|unidades|pecas|peca|itens|item|caixas|em estoque|de estoque)"
UNIDADE_DINHEIRO = r"(reais|real|r\$|preco|precos|custa|custam|custo|valor unitario)"


class PlannerPorRegras:
    """Interpretador determinístico, sem modelo e sem chamada externa.

    As regras são avaliadas em ordem e a primeira que casa vence. A ordem não é
    arbitrária: intenção destrutiva vem primeiro para que "apague os produtos com
    estoque baixo" nunca seja confundida com uma consulta inofensiva.
    """

    nome = "regras"

    async def planejar(self, pergunta: str) -> Interpretacao:
        texto = normalizar(pergunta)

        for regra in (
            self._intencao_destrutiva,
            self._detalhar_produto,
            self._estoque_baixo,
            self._resumo,
            self._faixa_de_preco,
            self._busca_por_nome,
        ):
            interpretacao = regra(texto)
            if interpretacao is not None:
                return interpretacao

        return Interpretacao(
            ferramenta=None,
            argumentos={},
            confianca=0.0,
            estrategia=self.nome,
            justificativa="Nenhuma regra reconheceu a intencao da pergunta",
        )

    # ------------------------------------------------------------------ regras

    def _intencao_destrutiva(self, texto: str) -> Interpretacao | None:
        if not re.search(r"\b(apag|delet|remov|exclu|zerar|limpar)", texto):
            return None

        ids = [int(n) for n in _numeros(texto) if float(n).is_integer()]
        if not ids:
            # Detectou a intenção mas não o alvo. Devolver confiança baixa é
            # melhor que chutar um id: o executor vai pedir esclarecimento em vez
            # de apagar o produto errado.
            return Interpretacao(
                ferramenta="remover_produto",
                argumentos={},
                confianca=0.35,
                estrategia=self.nome,
                justificativa="Intencao de remocao detectada, mas sem id de produto identificavel",
            )

        return Interpretacao(
            ferramenta="remover_produto",
            argumentos={"produto_id": ids[0]},
            confianca=0.85,
            estrategia=self.nome,
            justificativa="Verbo de remocao acompanhado de identificador numerico",
        )

    def _detalhar_produto(self, texto: str) -> Interpretacao | None:
        casamento = re.search(r"(?:produto|item|sku)\s*(?:de\s*id\s*)?#?\s*(\d+)\b", texto)
        if not casamento:
            return None
        # "produtos com estoque abaixo de 10" também casaria; exigir contexto de
        # detalhe evita sequestrar a pergunta de estoque.
        if not re.search(r"\b(detalh|mostra|ver|exib|consulta|qual)\b", texto):
            return None
        if re.search(r"\b(estoque|abaixo|acabando)\b", texto):
            return None
        return Interpretacao(
            ferramenta="detalhar_produto",
            argumentos={"produto_id": int(casamento.group(1))},
            confianca=0.9,
            estrategia=self.nome,
            justificativa="Pedido de visualizacao de um produto identificado por id",
        )

    def _estoque_baixo(self, texto: str) -> Interpretacao | None:
        sinais = re.search(
            r"(estoque baixo|estoque esta baixo|acabando|repor|reposicao|ruptura|"
            r"em falta|faltando|zerado|sem estoque|abaixo de|menor que|menos de)",
            texto,
        )
        if not sinais or "estoque" not in texto and "unidad" not in texto and "falta" not in texto:
            return None

        # Se o número está falando de dinheiro, a pergunta é de preço, não de estoque.
        if re.search(UNIDADE_DINHEIRO, texto):
            return None

        numeros = [n for n in _numeros(texto) if float(n).is_integer()]
        limite = int(numeros[0]) if numeros else 10
        confianca = 0.95 if numeros else 0.75

        return Interpretacao(
            ferramenta="consultar_estoque_baixo",
            argumentos={"limite": limite},
            confianca=confianca,
            estrategia=self.nome,
            justificativa=(
                f"Expressao de estoque insuficiente reconhecida; limite={limite}"
                + ("" if numeros else " assumido por ausencia de valor explicito")
            ),
        )

    def _resumo(self, texto: str) -> Interpretacao | None:
        if not re.search(
            r"(quanto vale|valor total|valor do estoque|resumo|consolidado|"
            r"quantos produtos|quantas unidades|total de produtos|total de itens)",
            texto,
        ):
            return None
        return Interpretacao(
            ferramenta="resumo_do_estoque",
            argumentos={},
            confianca=0.9,
            estrategia=self.nome,
            justificativa="Pergunta por numero consolidado do estoque",
        )

    def _faixa_de_preco(self, texto: str) -> Interpretacao | None:
        if not re.search(UNIDADE_DINHEIRO, texto) and not re.search(r"\bentre\b", texto):
            return None

        entre = re.search(r"entre\s+(?:r\$\s*)?([\d.,]+)\s+e\s+(?:r\$\s*)?([\d.,]+)", texto)
        if entre:
            return Interpretacao(
                ferramenta="buscar_produtos",
                argumentos={
                    "preco_min": _para_numero(entre.group(1)),
                    "preco_max": _para_numero(entre.group(2)),
                },
                confianca=0.92,
                estrategia=self.nome,
                justificativa="Faixa de preco explicita com limite inferior e superior",
            )

        acima = re.search(r"(mais de|acima de|maior que|a partir de)\s+(?:r\$\s*)?([\d.,]+)", texto)
        if acima:
            return Interpretacao(
                ferramenta="buscar_produtos",
                argumentos={"preco_min": _para_numero(acima.group(2))},
                confianca=0.88,
                estrategia=self.nome,
                justificativa="Limite inferior de preco reconhecido",
            )

        abaixo = re.search(r"(menos de|abaixo de|menor que|ate)\s+(?:r\$\s*)?([\d.,]+)", texto)
        if abaixo:
            return Interpretacao(
                ferramenta="buscar_produtos",
                argumentos={"preco_max": _para_numero(abaixo.group(2))},
                confianca=0.88,
                estrategia=self.nome,
                justificativa="Limite superior de preco reconhecido",
            )
        return None

    def _busca_por_nome(self, texto: str) -> Interpretacao | None:
        padroes = (
            r"(?:com|contendo|que tenha[m]?)\s+(.+?)\s+no nome",
            r"(?:busca|buscar|procura|procurar|pesquisa|pesquisar|encontr\w+)\s+(?:por\s+)?(.+)",
            r"produtos?\s+(?:de|do|da)\s+(.+)",
        )
        for padrao in padroes:
            casamento = re.search(padrao, texto)
            if not casamento:
                continue
            termo = casamento.group(1).strip(" ?.!")
            # Termo muito curto vira busca que devolve o catálogo inteiro.
            if len(termo) < 3:
                continue
            return Interpretacao(
                ferramenta="buscar_produtos",
                argumentos={"nome": termo},
                confianca=0.7,
                estrategia=self.nome,
                justificativa=f"Busca textual pelo termo {termo!r}",
            )
        return None


def sugestoes_de_uso(maximo: int = 5) -> list[str]:
    """Exemplos extraídos do próprio registro de ferramentas.

    Ficam junto da ferramenta e não numa lista solta: ferramenta nova já nasce
    com o exemplo aparecendo para o usuário, sem ninguém lembrar de atualizar
    uma constante em outro arquivo.
    """
    exemplos: list[str] = []
    for ferramenta in REGISTRO.values():
        if ferramenta.destrutiva:
            continue  # não se sugere ao usuário que apague coisas
        exemplos.extend(ferramenta.exemplos)
    return exemplos[:maximo]


def planner_padrao() -> Planner:
    """Ponto único de troca do interpretador.

    Quando existir um PlannerLLM, é esta função que passa a decidir qual usar —
    por variável de ambiente, por porcentagem de tráfego ou por fallback quando
    o provedor de IA estiver fora do ar (Questao 9).
    """
    return PlannerPorRegras()

