import streamlit as st

from modules.devolucoes.parser import ParserRomaneio
from modules.devolucoes.services import preparar_banco
from modules.devolucoes.tratamento import init_tratamento_db
from modules.devolucoes.pages import (
    anapolis as page_anapolis,
    conferencia as page_conferencia,
    configuracoes as page_configuracoes,
    dashboard as page_dashboard,
    historico as page_historico,
    indicadores as page_indicadores,
    pendencias as page_pendencias,
    recebimento as page_recebimento,
    tratamento as page_tratamento,
)

st.set_page_config(
    page_title="Centro de Tratamento de Devoluções",
    page_icon="📦",
    layout="wide",
)

preparar_banco()
init_tratamento_db()

st.title("📦 Centro de Tratamento de Devoluções")
st.caption("Ambiente isolado de testes — nenhuma lógica do aplicativo oficial é alterada aqui.")

LOJAS = [
    "01 - Curitiba Prime",
    "02 - Ponta Grossa Brands",
    "03 - Joinville Brands",
    "04 - Porto Aux",
    "05 - Porto Praia",
    "06 - Campinas Cambui",
    "07 - Caxias Porto",
    "08 - Campos Outlet",
    "09 - Brasilia Distrito",
    "10 - Camboriú Brands",
    "11 - Cascavel Distrito",
    "12 - Prime Bigorrilho",
    "13 - Iguaçu Distrito",
    "14 - Santos Outlet",
    "15 - Sampa Outlet",
]

for key, value in {
    "comparacao": None,
    "loja": None,
    "entrada": None,
    "anapolis_romaneio": None,
    "loja_selecionada": None,
    "registrado_id": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

PAGINAS = {
    "🏠 Dashboard": page_dashboard,
    "📥 Recebimento": page_recebimento,
    "🔎 Conferência": page_conferencia,
    "⚠️ Pendências": page_pendencias,
    "📋 Aguardando decisão": page_tratamento,
    "🩹 Defeitos Anápolis": page_anapolis,
    "🕘 Histórico": page_historico,
    "📊 Indicadores": page_indicadores,
    "⚙️ Configurações": page_configuracoes,
}

selecao = st.sidebar.radio("Centro de Devoluções", list(PAGINAS.keys()))
parser = ParserRomaneio()
pagina = PAGINAS[selecao]

if pagina is page_recebimento:
    pagina.render(LOJAS, parser)
else:
    pagina.render()

st.sidebar.divider()
st.sidebar.caption("🧪 AMBIENTE DE TESTE")
st.sidebar.caption("Projeto independente do app oficial.")
