import streamlit as st

st.set_page_config(
    page_title="Centro de Tratamento de Devoluções",
    page_icon="📦",
    layout="wide",
)

st.title("📦 Centro de Tratamento de Devoluções")
st.caption("Ambiente isolado de testes — nenhuma lógica do aplicativo oficial é alterada aqui.")

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

if pages[selecao] == "dashboard":
    st.header("Dashboard")
    st.info("Painel inicial do laboratório. Os indicadores serão alimentados pelo módulo de devoluções.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recebidas", 0)
    c2.metric("Em conferência", 0)
    c3.metric("Pendentes", 0)
    c4.metric("Concluídas", 0)

elif pages[selecao] == "recebimento":
    st.header("📥 Recebimento de devolução")
    st.write("Importe um romaneio para criar um processo de devolução.")
    st.file_uploader("Romaneio da devolução", type=["pdf"], key="romaneio_pdf")
    st.caption("Nesta primeira versão, a leitura do PDF ainda será validada antes de gravar qualquer dado.")

elif pages[selecao] == "conferencia":
    st.header("🔎 Conferência")
    st.info("Aqui vamos comparar o que consta no romaneio com o que efetivamente foi recebido.")

elif pages[selecao] == "pendencias":
    st.header("⚠️ Pendências")
    st.info("Divergências de quantidade, itens, avarias e outras ocorrências aparecerão aqui.")

elif pages[selecao] == "decisao":
    st.header("📋 Aguardando decisão")
    st.info("Área para decidir o destino das mercadorias após a conferência.")

elif pages[selecao] == "historico":
    st.header("🕘 Histórico")
    st.info("Histórico de processos, conferências e decisões.")

elif pages[selecao] == "indicadores":
    st.header("📊 Indicadores")
    st.info("Indicadores de volume, divergências, tempo de tratamento e desempenho por loja.")

elif pages[selecao] == "configuracoes":
    st.header("⚙️ Configurações")
    st.info("Configurações específicas do laboratório de devoluções.")

st.sidebar.divider()
st.sidebar.caption("🧪 AMBIENTE DE TESTE")
st.sidebar.caption("Projeto independente do app oficial.")
