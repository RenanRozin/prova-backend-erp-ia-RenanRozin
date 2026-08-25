"""Regras de validação de domínio, isoladas das classes de schema.

Ficam aqui, como funções puras, por dois motivos: são reaproveitadas por mais de
um schema (Create e Update) e podem ser testadas sem instanciar modelo nenhum.
"""


def validar_nome_produto(valor: str) -> str:
    """Nome não pode ser nulo, vazio, só espaços, nem um valor numérico.

    Requisito explícito da prova. O caso "só espaços" passaria por `min_length`
    e entraria no cadastro como lixo, por isso o strip vem antes.
    """
    limpo = valor.strip()
    if not limpo:
        raise ValueError("nome não pode ser vazio ou conter apenas espaços")
    # O replace cobre "123.45" e "1.999,00", que também não são nomes.
    if limpo.replace(".", "").replace(",", "").replace(" ", "").isdigit():
        raise ValueError("nome não pode ser um valor numérico")
    return limpo
