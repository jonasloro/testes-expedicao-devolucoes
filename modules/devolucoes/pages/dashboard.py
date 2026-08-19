import streamlit as st

from ..database import listar_devolucoes


def render() -> None:
    st.header("Dashboard")
    registros = listar_devolucoes()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devoluções registradas", len(registros))
    c2.metric(
        "Aguardando tratamento",
        sum(1 for r in registros if r["status"] in {"AGUARDANDO TRATAMENTO", "DIVERGENTE", "CONFERIDA"}),
    )
    c3.metric("Concluídas", sum(1 for r in registros if r["status"] == "CONCLUÍDA"))
    c4.metric("Lojas com registros", len({r["loja"] for r in registros if r.get("loja")}))
    st.info(
        "Fluxo: romaneio da loja + romaneio CD + romaneio Anápolis → conferência → registro → tratamento. "
        "Bipagem de defeitos permanece como recurso auxiliar."
    )
