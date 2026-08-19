import pandas as pd
import streamlit as st

from modules.devolucoes.parser import ParserRomaneio
from modules.devolucoes.services import comparar_documentos, preparar_banco

st.set_page_config(page_title="Centro de Tratamento de Devoluções", page_icon="📦", layout="wide")
preparar_banco()

st.title("📦 Centro de Tratamento de Devoluções")
st.caption("Ambiente isolado de testes — nenhuma lógica do aplicativo oficial é alterada aqui.")

if "comparacao" not in st.session_state:
    st.session_state.comparacao = None
if "loja" not in st.session_state:
    st.session_state.loja = None
if "entrada" not in st.session_state:
    st.session_state.entrada = None

pages = {
    "🏠 Dashboard": "dashboard",
    "📥 Recebimento": "recebimento",
    "🔎 Conferência": "conferencia",
    "⚠️ Pendências": "pendencias",
    "📋 Aguardando decisão": "decisao",
    "🕘 Histórico": "historico",
    "📊 Indicadores": "indicadores",
    "⚙️ Configurações": "configuracoes",
}
selecao = st.sidebar.radio("Centro de Devoluções", list(pages.keys()))
parser = ParserRomaneio()

if pages[selecao] == "dashboard":
    st.header("Dashboard")
    st.info("Fluxo de teste: romaneio da loja + romaneio da entrada → conferência por código de barras.")
    st.metric("Comparações realizadas nesta sessão", 1 if st.session_state.comparacao else 0)

elif pages[selecao] == "recebimento":
    st.header("📥 Recebimento da devolução")
    st.write("Envie os dois documentos. Nada é lançado no estoque nesta etapa.")
    col1, col2 = st.columns(2)
    with col1:
        pdf_loja = st.file_uploader("1. Romaneio enviado pela loja", type=["pdf"], key="pdf_loja")
    with col2:
        pdf_entrada = st.file_uploader("2. Romaneio da entrada no CD", type=["pdf"], key="pdf_entrada")

    if pdf_loja and pdf_entrada and st.button("🔎 Ler e comparar os dois romaneios", type="primary"):
        with st.spinner("Lendo os documentos..."):
            try:
                resultado_loja = parser.analisar(pdf_loja.getvalue())
                resultado_entrada = parser.analisar(pdf_entrada.getvalue())
                st.session_state.loja = resultado_loja
                st.session_state.entrada = resultado_entrada
                st.session_state.comparacao = comparar_documentos(resultado_loja, resultado_entrada)
                st.success("Documentos lidos e comparação criada.")
            except Exception as exc:
                st.error(f"Não foi possível processar os PDFs: {exc}")

    if st.session_state.loja and st.session_state.entrada:
        st.subheader("Resumo")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documento loja", st.session_state.loja["cabecalho"].get("numero_documento") or "—")
        c2.metric("Peças loja", st.session_state.loja["total_pecas"])
        c3.metric("Peças entrada", st.session_state.entrada["total_pecas"])
        c4.metric("Itens distintos", len(st.session_state.comparacao or []))

elif pages[selecao] == "conferencia":
    st.header("🔎 Conferência")
    if not st.session_state.comparacao:
        st.info("Envie os dois romaneios na tela Recebimento para iniciar a conferência.")
    else:
        df = pd.DataFrame(st.session_state.comparacao)
        c1, c2, c3 = st.columns(3)
        c1.metric("✅ OK", int((df["status"] == "OK").sum()))
        c2.metric("🔴 Faltou", int((df["status"] == "FALTOU").sum()))
        c3.metric("🟡 Excesso", int((df["status"] == "EXCESSO").sum()))
        st.dataframe(df, use_container_width=True, hide_index=True)

elif pages[selecao] == "pendencias":
    st.header("⚠️ Pendências")
    if st.session_state.comparacao:
        df = pd.DataFrame(st.session_state.comparacao)
        pendencias = df[df["status"] != "OK"]
        if pendencias.empty:
            st.success("Nenhuma divergência encontrada.")
        else:
            st.dataframe(pendencias, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma conferência foi executada ainda.")

elif pages[selecao] == "decisao":
    st.header("📋 Aguardando decisão")
    st.info("Depois da conferência, esta área receberá as decisões sobre as mercadorias.")

elif pages[selecao] == "historico":
    st.header("🕘 Histórico")
    st.info("O histórico definitivo será conectado depois que o fluxo de conferência for validado.")

elif pages[selecao] == "indicadores":
    st.header("📊 Indicadores")
    if st.session_state.comparacao:
        df = pd.DataFrame(st.session_state.comparacao)
        a, b, c = st.columns(3)
        a.metric("Peças da loja", int(df["qtd_loja"].sum()))
        b.metric("Peças da entrada", int(df["qtd_entrada"].sum()))
        c.metric("Diferença total", int(df["diferenca"].sum()))
    else:
        st.info("Faça uma conferência para gerar os indicadores.")

elif pages[selecao] == "configuracoes":
    st.header("⚙️ Configurações")
    st.info("Configurações específicas do laboratório de devoluções.")

st.sidebar.divider()
st.sidebar.caption("🧪 AMBIENTE DE TESTE")
st.sidebar.caption("Projeto independente do app oficial.")
