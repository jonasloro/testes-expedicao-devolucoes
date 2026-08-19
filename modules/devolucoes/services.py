from collections import defaultdict

from .database import init_db, listar_devolucoes, listar_defeitos_anapolis


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
        elif status in {"AGUARDANDO TRATAMENTO"}:
            resumo["pendentes"] += 1
        elif status in {"CONCLUÍDA", "CONCLUIDA"}:
            resumo["concluidas"] += 1
    return resumo


def obter_defeitos_documento(numero_documento: str) -> dict[str, int]:
    return {
        str(row["codigo_barras"]): int(row["quantidade"])
        for row in listar_defeitos_anapolis(numero_documento)
    }


def comparar_documentos(romaneio_loja: dict, romaneio_entrada: dict, defeitos_anapolis: dict[str, int] | None = None) -> list[dict]:
    """Compara loja x entrada CD + defeitos bipados em Anápolis.

    Uma peça é considerada encontrada quando estiver na entrada do CD ou
    registrada como defeito em Anápolis. Portanto:

        encontrado = entrada_cd + anapolis

    O código de barras continua sendo a chave do cruzamento.
    """
    loja = defaultdict(int)
    entrada = defaultdict(int)
    anapolis = defaultdict(int, defeitos_anapolis or {})
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
    for codigo in sorted(set(loja) | set(entrada) | set(anapolis)):
        qtd_loja = loja[codigo]
        qtd_entrada = entrada[codigo]
        qtd_anapolis = anapolis[codigo]
        qtd_encontrada = qtd_entrada + qtd_anapolis
        diferenca = qtd_encontrada - qtd_loja

        if diferenca == 0:
            status = "OK"
        elif diferenca < 0:
            status = "FALTOU"
        else:
            status = "EXCESSO"

        base = dados.get(codigo, {})
        resultado.append(
            {
                "codigo_barras": codigo,
                "referencia": base.get("referencia", ""),
                "descricao": base.get("descricao", ""),
                "grade": base.get("grade", ""),
                "qtd_loja": qtd_loja,
                "qtd_entrada": qtd_entrada,
                "qtd_anapolis": qtd_anapolis,
                "qtd_encontrada": qtd_encontrada,
                "diferenca": diferenca,
                "status": status,
            }
        )
    return resultado
