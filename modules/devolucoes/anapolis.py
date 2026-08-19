from .database import listar_defeitos_anapolis, registrar_bip_anapolis, remover_ultimo_bip_anapolis


def bipar(numero_documento: str, codigo_barras: str, usuario: str = "") -> None:
    registrar_bip_anapolis(numero_documento, codigo_barras, usuario)


def remover_ultimo(numero_documento: str, codigo_barras: str) -> None:
    remover_ultimo_bip_anapolis(numero_documento, codigo_barras)


def resumo(numero_documento: str):
    return listar_defeitos_anapolis(numero_documento)
