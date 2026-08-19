from collections import defaultdict

from .database import init_db, listar_devolucoes


def preparar_banco() -> None:
    init_db()


def resumo_dashboard() -> dict:
    registros = listar_devolucoes()
    resumo = {"recebidas": 0, "conferencia": 0, "pendentes": 0, "concluidas": 0}
    for registro in registros:
        status = str(registro["status"]).upper()
        if status == "RECEBIDA":
            resumo["recebidas"] += 1
        elif status == "EM CONFERÊNCIA":
            resumo["conferencia"] += 1
        elif status in {"PENDENTE", "DIVERGENTE"}:
            resumo["pendentes"] += 1
        elif status in {"CONCLUÍDA", "CONCLUIDA"}:
            resumo["concluidas"] += 1
    return resumo


def comparar_documentos(romaneio_loja: dict, romaneio_entrada: dict) -> list[dict]:
    """Compara as quantidades por código de barras.

    A chave do cruzamento é o código de barras. Um código ausente em um dos
    documentos também aparece no resultado, permitindo identificar faltas e excessos.
    """
    loja = defaultdict(int)
    entrada = defaultdict(int)
    dados = {}

    for item in romaneio_loja.get("itens", []):
        codigo = str(item["codigo_barras"]).strip()
        loja[codigo] += int(item["quantidade"])
        dados.setdefault(codigo, item)

    for item in romaneio_entrada.get("itens", []):
        codigo = str(item["codigo_barras"]).strip()
        entrada[codigo] += int(item["quantidade"])
        dados.setdefault(codigo, item)

    resultado = []
    for codigo in sorted(set(loja) | set(entrada)):
        qtd_loja = loja[codigo]
        qtd_entrada = entrada[codigo]
        diferenca = qtd_entrada - qtd_loja
        if diferenca == 0:
            status = "OK"
        elif diferenca < 0:
            status = "FALTOU"
        else:
            status = "EXCESSO"

        base = dados[codigo]
        resultado.append(
            {
                "codigo_barras": codigo,
                "referencia": base.get("referencia", ""),
                "descricao": base.get("descricao", ""),
                "grade": base.get("grade", ""),
                "qtd_loja": qtd_loja,
                "qtd_entrada": qtd_entrada,
                "diferenca": diferenca,
                "status": status,
            }
        )
    return resultado
