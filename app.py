import streamlit as st

st.set_page_config(
    page_title="Laboratório de Devoluções",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Laboratório de Devoluções")
st.caption("Ambiente isolado para testar melhorias da Expedição.")

st.info("Use o menu lateral para acessar o módulo de Devoluções.")

st.subheader("Status do laboratório")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Módulos", "1")
with col2:
    st.metric("Devoluções registradas", "0")
with col3:
    st.metric("Ambiente", "TESTE")

st.warning(
    "Este repositório é independente do aplicativo principal. "
    "Nenhuma alteração feita aqui deve afetar o sistema oficial."
)
