from datetime import date

import pandas as pd
import streamlit as st

from modules.devolucoes.anapolis import bipar, resumo as resumo_anapolis
from modules.devolucoes.database import (
    buscar_itens_devolucao,
    listar_devolucoes,
    registrar_conferencia,
)
from modules.devolucoes.parser import ParserRomaneio
from modules.devolucoes.services import comparar_documentos, obter_defeitos_documento, preparar_banco
from modules.devolucoes.tratamento import (
    DESTINOS,
    init_tratamento_db,
    listar_devolucoes_para_tratamento,
    quantidades_tratadas,
    salvar_tratamentos_em_lote,
    listar_tratamentos,
)

st.set_page_config(page_title="Centro de Tratamento de Devoluções", page_icon="📦", layout="wide")
preparar_banco()
init_tratamento_db()

st.title("📦 Centro de Tratamento de Devoluções")
st.caption("Ambiente isolado de testes — nenhuma lógica do aplicativo oficial é alterada aqui.")
