from .database import listar_devolucoes, init_db


def preparar_banco() -> None:
    init_db()


def resumo_dashboard() -> dict:
    registros = listar_devolucoes()
    resumo = {
        "recebidas": 0,
        "conferencia": 0,
        "pendentes": 0,
        "concluidas": 0,
    }

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
