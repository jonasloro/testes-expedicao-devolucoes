import pandas as pd
import streamlit as st

# Rótulos oficiais da tela de conferência, na ordem pedida:
# Código | Produto | Grade | Loja | CD | Anápolis | Total encontrado | Diferença | Status
COLUNAS_CONFERENCIA = {
    "codigo_barras": "Código",
    "descricao": "Produto",
    "grade": "Grade",
    "qtd_loja": "Loja",
    "qtd_entrada": "CD",
    "qtd_anapolis": "Anápolis",
    "qtd_encontrada": "Total encontrado",
    "diferenca": "Diferença",
    "status": "Status",
}


def formatar_tabela(df: pd.DataFrame) -> pd.DataFrame:
    colunas_presentes = [c for c in COLUNAS_CONFERENCIA if c in df.columns]
    return df[colunas_presentes].rename(columns=COLUNAS_CONFERENCIA)


def render() -> None:
    st.header("🔎 Conferência")
    if not st.session_state.comparacao:
        st.info("Envie os três romaneios na tela Recebimento para iniciar a conferência.")
        return

    df = pd.DataFrame(st.session_state.comparacao)
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ OK", int((df["status"] == "OK").sum()))
    c2.metric("🔴 Faltou", int((df["status"] == "FALTOU").sum()))
    c3.metric("🟡 Excesso", int((df["status"] == "EXCESSO").sum()))
    st.caption("Regra: Loja = Entrada CD + Entrada Anápolis. A origem que causou a diferença aparece nas colunas CD e Anápolis.")
    st.dataframe(formatar_tabela(df), use_container_width=True, hide_index=True)
