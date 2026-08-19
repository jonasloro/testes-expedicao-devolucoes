import streamlit as st

from ..database import listar_devolucoes


def render() -> None:
    st.header("📊 Indicadores")
    registros = listar_devolucoes()
    if not registros:
        st.info("Registre pelo menos uma devolução para gerar indicadores.")
        return

    total_loja = sum(r["total_pecas_loja"] or 0 for r in registros)
    total_cd = sum(r["total_pecas_entrada"] or 0 for r in registros)
    total_anapolis = sum(r.get("total_pecas_anapolis") or 0 for r in registros)
    c1, c2, c3 = st.columns(3)
    c1.metric("Peças da loja", total_loja)
    c2.metric("Peças da entrada CD", total_cd)
    c3.metric("Peças da entrada Anápolis", total_anapolis)
    st.metric("Diferença acumulada", total_cd + total_anapolis - total_loja)
