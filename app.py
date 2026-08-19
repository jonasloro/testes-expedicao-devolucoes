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
    resumo_tratamentos,
)

st.set_page_config(page_title="Centro de Tratamento de Devoluções", page_icon="📦", layout="wide")
preparar_banco()
init_tratamento_db()

st.title("📦 Centro de Tratamento de Devoluções")
st.caption("Ambiente isolado de testes — nenhuma lógica do aplicativo oficial é alterada aqui.")

LOJAS = [
    "01 - Curitiba Prime", "02 - Ponta Grossa Brands", "03 - Joinville Brands",
    "04 - Porto Aux", "05 - Porto Praia", "06 - Campinas Cambui",
    "07 - Caxias Porto", "08 - Campos Outlet", "09 - Brasilia Distrito",
    "10 - Camboriú Brands", "11 - Cascavel Distrito", "12 - Prime Bigorrilho",
    "13 - Iguaçu Distrito", "14 - Santos Outlet", "15 - Sampa Outlet",
]

for key, value in {
    "comparacao": None, "loja": None, "entrada": None,
    "loja_selecionada": None, "registrado_id": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

pages = {
    "🏠 Dashboard": "dashboard",
    "📥 Recebimento": "recebimento",
    "🔎 Conferência": "conferencia",
    "⚠️ Pendências": "pendencias",
    "📋 Tratamento": "tratamento",
    "🩹 Defeitos Anápolis": "anapolis",
    "🕘 Histórico": "historico",
    "📊 Indicadores": "indicadores",
    "⚙️ Configurações": "configuracoes",
}
selecao = st.sidebar.radio("Centro de Devoluções", list(pages.keys()))
parser = ParserRomaneio()

if pages[selecao] == "dashboard":
    registros = listar_devolucoes()
    st.header("Dashboard")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devoluções", len(registros))
    c2.metric("Aguardando tratamento", sum(1 for r in registros if r["status"] == "AGUARDANDO TRATAMENTO"))
    c3.metric("Divergentes", sum(1 for r in registros if r["status"] == "DIVERGENTE"))
    c4.metric("Concluídas", sum(1 for r in registros if r["status"] == "CONCLUÍDA"))
    st.info("Conferência: quantidade da loja = entrada no CD + defeitos registrados em Anápolis. Tratamento não altera estoque.")

elif pages[selecao] == "recebimento":
    st.header("📥 Recebimento da devolução")
    st.write("Selecione a loja e envie os dois romaneios. Defeitos já bipados em Anápolis entram automaticamente na conferência pelo documento.")

    loja = st.selectbox("Loja da devolução", ["Selecione uma loja"] + LOJAS, key="recebimento_loja")
    if loja != "Selecione uma loja":
        st.session_state.loja_selecionada = loja

    c1, c2 = st.columns(2)
    with c1:
        pdf_loja = st.file_uploader("1. Romaneio enviado pela loja", type=["pdf"], key="pdf_loja")
    with c2:
        pdf_entrada = st.file_uploader("2. Romaneio da entrada no CD", type=["pdf"], key="pdf_entrada")

    if loja != "Selecione uma loja" and pdf_loja and pdf_entrada:
        if st.button("🔎 Ler e comparar os documentos", type="primary"):
            try:
                with st.spinner("Lendo romaneios e defeitos de Anápolis..."):
                    loja_doc = parser.analisar(pdf_loja.getvalue())
                    entrada_doc = parser.analisar(pdf_entrada.getvalue())
                    documento = loja_doc["cabecalho"].get("numero_documento", "")
                    defeitos = obter_defeitos_documento(documento)
                    st.session_state.loja = loja_doc
                    st.session_state.entrada = entrada_doc
                    st.session_state.comparacao = comparar_documentos(loja_doc, entrada_doc, defeitos)
                    st.session_state.registrado_id = None
                st.success("Comparação criada com a entrada do CD e os defeitos de Anápolis.")
            except Exception as exc:
                st.error(f"Não foi possível processar os documentos: {exc}")

    if st.session_state.loja and st.session_state.entrada:
        df = pd.DataFrame(st.session_state.comparacao or [])
        total_anapolis = int(df["qtd_anapolis"].sum()) if not df.empty else 0
        total_encontrado = int(df["qtd_encontrada"].sum()) if not df.empty else 0
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Documento", st.session_state.loja["cabecalho"].get("numero_documento") or "—")
        c2.metric("Loja", st.session_state.loja_selecionada or "—")
        c3.metric("Peças loja", st.session_state.loja["total_pecas"])
        c4.metric("Entrada CD", st.session_state.entrada["total_pecas"])
        c5.metric("Defeitos Anápolis", total_anapolis)
        st.metric("Total contabilizado", total_encontrado)

        if not st.session_state.registrado_id:
            divergente = any(item.get("status") != "OK" for item in st.session_state.comparacao or [])
            if divergente:
                st.warning("Há divergências reais: nem a entrada do CD nem Anápolis explicam toda a quantidade da loja.")
            else:
                st.success("Conferência OK: toda quantidade da loja está explicada pela entrada do CD + Anápolis.")
            if st.button("✅ Registrar devolução", type="primary"):
                try:
                    st.session_state.registrado_id = registrar_conferencia(
                        numero_documento=st.session_state.loja["cabecalho"].get("numero_documento", ""),
                        data_documento=st.session_state.loja["cabecalho"].get("data_documento", ""),
                        arquivo_loja=pdf_loja.name,
                        arquivo_entrada=pdf_entrada.name,
                        resultado=st.session_state.comparacao or [],
                        total_pecas_loja=st.session_state.loja["total_pecas"],
                        total_pecas_entrada=st.session_state.entrada["total_pecas"],
                        loja=st.session_state.loja_selecionada or "",
                    )
                    st.success(f"Devolução registrada no Neon. ID interno: {st.session_state.registrado_id}")
                except Exception as exc:
                    st.error(f"Não foi possível registrar a devolução: {exc}")
        else:
            st.success(f"Devolução registrada no histórico. ID interno: {st.session_state.registrado_id}")

elif pages[selecao] == "conferencia":
    st.header("🔎 Conferência")
    if not st.session_state.comparacao:
        st.info("Faça uma leitura em Recebimento para iniciar a conferência.")
    else:
        df = pd.DataFrame(st.session_state.comparacao)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("✅ OK", int((df["status"] == "OK").sum()))
        c2.metric("🔴 Faltou", int((df["status"] == "FALTOU").sum()))
        c3.metric("🟡 Excesso", int((df["status"] == "EXCESSO").sum()))
        c4.metric("🩹 Anápolis", int(df["qtd_anapolis"].sum()))
        st.dataframe(
            df[["codigo_barras", "descricao", "grade", "qtd_loja", "qtd_entrada", "qtd_anapolis", "qtd_encontrada", "diferenca", "status"]],
            use_container_width=True,
            hide_index=True,
        )

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

elif pages[selecao] == "tratamento":
    st.header("📋 Tratamento da devolução")
    st.caption("Tratativa em lote. Aqui definimos apenas o destino físico/operacional; o estoque ainda não é alterado.")
    registros = listar_devolucoes_para_tratamento()
    if not registros:
        st.success("Não há devoluções aguardando tratamento.")
    else:
        opcoes = [f"#{r['id']} — {r['loja'] or 'Loja não informada'} — documento {r['numero_documento']}" for r in registros]
        escolha = st.selectbox("Devolução", opcoes)
        registro = registros[opcoes.index(escolha)]
        devolucao_id = int(registro["id"])
        itens = buscar_itens_devolucao(devolucao_id)
        tratados = quantidades_tratadas(devolucao_id)
        pendentes = []
        for item in itens:
            total = int(item["quantidade_entrada"] or 0)
            ja_tratado = int(tratados.get(int(item["id"]), 0))
            restante = max(total - ja_tratado, 0)
            if restante:
                pendentes.append((item, restante))
        total_restante = sum(q for _, q in pendentes)

        c1, c2, c3 = st.columns(3)
        c1.metric("Entrada CD", int(registro["total_pecas_entrada"] or 0))
        c2.metric("Já tratados", int(registro["pecas_tratadas"] or 0))
        c3.metric("Restante", total_restante)

        if total_restante == 0:
            st.success("Todas as peças que entraram no CD já receberam uma tratativa.")
        else:
            destino = st.selectbox("Destino para o lote restante", DESTINOS)
            observacao = st.text_input("Observação do lote (opcional)")
            st.write(f"Serão tratadas **{total_restante} peças** como **{destino}**.")
            if st.button("✅ Aplicar destino ao lote inteiro", type="primary"):
                try:
                    lancamentos = [
                        {"devolucao_item_id": int(item["id"]), "quantidade": restante, "destino": destino, "observacao": observacao}
                        for item, restante in pendentes
                    ]
                    salvar_tratamentos_em_lote(devolucao_id, lancamentos)
                    st.success(f"{total_restante} peças encaminhadas para {destino}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível registrar a tratativa: {exc}")

            st.dataframe(pd.DataFrame([
                {"Código": item["codigo_barras"], "Descrição": item["descricao"], "Grade": item["grade"], "Restante": restante}
                for item, restante in pendentes
            ]), use_container_width=True, hide_index=True)

        registros_trat = listar_tratamentos(devolucao_id)
        if registros_trat:
            st.subheader("Histórico de tratativas")
            st.dataframe(pd.DataFrame([dict(r) for r in registros_trat]), use_container_width=True, hide_index=True)
            resumo = resumo_tratamentos(devolucao_id)
            st.write("**Resumo:** " + " · ".join(f"{k}: {v}" for k, v in resumo.items()))

elif pages[selecao] == "anapolis":
    st.header("🩹 Defeitos — Anápolis")
    st.write("Cada bip representa **1 peça com defeito**. O lançamento fica associado ao número do documento e será usado na conferência.")
    documento = st.text_input("Número do documento/romaneio", placeholder="Ex.: 84630").strip()
    with st.form("bip_defeito", clear_on_submit=True):
        codigo = st.text_input("Código de barras", placeholder="Bipe com o leitor").strip()
        confirmar = st.form_submit_button("📦 Registrar bip")
    if confirmar:
        if not documento:
            st.error("Informe o documento.")
        elif not codigo:
            st.error("Bipe o código de barras.")
        else:
            try:
                bipar(documento, codigo)
                st.success(f"Bip registrado para o documento {documento}.")
            except Exception as exc:
                st.error(f"Não foi possível registrar o bip: {exc}")

    if documento:
        defeitos = resumo_anapolis(documento)
        total = sum(int(r["quantidade"]) for r in defeitos)
        c1, c2 = st.columns(2)
        c1.metric("Peças com defeito", total)
        c2.metric("Códigos distintos", len(defeitos))
        if defeitos:
            st.dataframe(pd.DataFrame([dict(r) for r in defeitos]), use_container_width=True, hide_index=True)

elif pages[selecao] == "historico":
    st.header("🕘 Histórico de devoluções")
    registros = listar_devolucoes()
    if not registros:
        st.info("Nenhuma devolução foi registrada ainda.")
    else:
        f1, f2, f3 = st.columns(3)
        busca = f1.text_input("Documento", placeholder="Ex.: 84630").strip().lower()
        lojas = sorted({str(r["loja"]) for r in registros if r.get("loja")})
        loja_filtro = f2.selectbox("Loja", ["Todas"] + lojas)
        status_filtro = f3.selectbox("Status", ["Todos"] + sorted({str(r["status"]) for r in registros if r["status"]}))
        filtrados = []
        for r in registros:
            if busca and busca not in str(r["numero_documento"] or "").lower():
                continue
            if loja_filtro != "Todas" and str(r["loja"] or "") != loja_filtro:
                continue
            if status_filtro != "Todos" and str(r["status"]) != status_filtro:
                continue
            filtrados.append(r)
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Devoluções", len(filtrados))
        c2.metric("Peças loja", sum(r["total_pecas_loja"] or 0 for r in filtrados))
        c3.metric("Entrada CD", sum(r["total_pecas_entrada"] or 0 for r in filtrados))
        c4.metric("Concluídas", sum(r["status"] == "CONCLUÍDA" for r in filtrados))
        if filtrados:
            st.dataframe(pd.DataFrame([
                {"ID": r["id"], "Loja": r["loja"] or "—", "Documento": r["numero_documento"],
                 "Data": r["data_documento"].strftime("%d/%m/%Y") if isinstance(r["data_documento"], date) else r["data_documento"],
                 "Status": r["status"], "Peças loja": r["total_pecas_loja"] or 0,
                 "Entrada CD": r["total_pecas_entrada"] or 0, "Diferença": r["diferenca_total"] or 0}
                for r in filtrados
            ]), use_container_width=True, hide_index=True)

elif pages[selecao] == "indicadores":
    st.header("📊 Indicadores")
    registros = listar_devolucoes()
    if registros:
        c1, c2, c3 = st.columns(3)
        c1.metric("Peças loja", sum(r["total_pecas_loja"] or 0 for r in registros))
        c2.metric("Entrada CD", sum(r["total_pecas_entrada"] or 0 for r in registros))
        c3.metric("Devoluções", len(registros))
    else:
        st.info("Registre uma devolução para gerar indicadores.")

elif pages[selecao] == "configuracoes":
    st.header("⚙️ Configurações")
    st.info("Configurações específicas do laboratório de devoluções.")

st.sidebar.divider()
st.sidebar.caption("🧪 AMBIENTE DE TESTE")
st.sidebar.caption("Projeto independente do app oficial.")
