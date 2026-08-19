import streamlit as st

from modules.devolucoes.interface import render_recebimento
from modules.devolucoes.services import preparar_banco, resumo_dashboard

st.set_page_config(
    page_title="Centro de Tratamento de Devoluções",
    page_icon="📦",
    layout="wide",
)

preparar_banco()

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
    resumo = resumo_dashboard()
    st.info("Visão geral do fluxo de devoluções em teste.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recebidas", resumo["recebidas"])
    c2.metric("Em conferência", resumo["conferencia"])
    c3.metric("Pendentes", resumo["pendentes"])
    c4.metric("Concluídas", resumo["concluidas"])

elif pages[selecao] == "recebimento":
    render_recebimento()

elif pages[selecao] == "conferencia":
    st.header("🔎 Conferência")
    st.info("Aqui vamos comparar o que consta no romaneio com o que efetivamente foi recebido.")
    st.caption("Próxima etapa do laboratório: conferência item a item.")

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
