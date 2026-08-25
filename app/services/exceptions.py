"""Exceções de domínio.

O service levanta erro de negócio, não `HTTPException`: assim a mesma regra vale
quando quem chama é o worker da fila ou o agente da Parte 5, que não têm request
HTTP nenhum. A tradução para status code acontece só na borda, no router.
"""


class DomainError(Exception):
    """Base de todos os erros de negócio."""


class ProdutoNaoEncontrado(DomainError):
    def __init__(self, produto_id: int) -> None:
        self.produto_id = produto_id
        super().__init__(f"Produto {produto_id} não encontrado")


class ProdutoDuplicado(DomainError):
    def __init__(self, nome: str) -> None:
        self.nome = nome
        super().__init__(f"Já existe um produto com o nome {nome!r}")


class CredenciaisInvalidas(DomainError):
    def __init__(self) -> None:
        super().__init__("Usuário ou senha inválidos")
