import pandas as pd
import streamlit as st

from .conferencia import formatar_tabela


def render() -> None:
    st.header("⚠️ Pendências")
    if not st.session_state.comparacao:
        st.info("Nenhuma conferência foi executada ainda.")
        return

    df = pd.DataFrame(st.session_state.comparacao)
    pendencias = df[df["status"] != "OK"]
    if pendencias.empty:
        st.success("Nenhuma divergência encontrada.")
    else:
        st.dataframe(formatar_tabela(pendencias), use_container_width=True, hide_index=True)
