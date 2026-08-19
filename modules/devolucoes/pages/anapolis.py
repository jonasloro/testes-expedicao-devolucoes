import pandas as pd
import streamlit as st

from .. import anapolis as anapolis_service


def render() -> None:
    st.header("🩹 Defeitos Anápolis")
    st.write("Recurso auxiliar para situações em que o romaneio de Anápolis ainda não estiver disponível. O fluxo oficial usa o terceiro romaneio.")

    documento = st.text_input("Documento da devolução", placeholder="Ex.: 84630", key="anapolis_documento").strip()
    codigo = st.text_input("Código de barras", placeholder="Bipe ou digite o código", key="anapolis_codigo").strip()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📦 Registrar bip", type="primary", disabled=not documento or not codigo):
            try:
                anapolis_service.bipar(documento, codigo)
                st.success("Bip auxiliar registrado em Anápolis.")
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível registrar o bip: {exc}")
    with c2:
        st.info("O bip é apenas um recurso auxiliar. A conferência oficial passa a usar o romaneio de Anápolis.")

    if documento:
        registros_anapolis = anapolis_service.resumo(documento)
        if registros_anapolis:
            df_a = pd.DataFrame([dict(r) for r in registros_anapolis])
            st.subheader("Bips auxiliares registrados")
            st.dataframe(df_a, use_container_width=True, hide_index=True)
            st.metric("Total de peças bipadas", int(df_a["quantidade"].sum()))
        else:
            st.info("Nenhum bip auxiliar para este documento.")
