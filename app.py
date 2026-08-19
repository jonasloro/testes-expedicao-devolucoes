import pandas as pd
import streamlit as st
from datetime import date

from modules.devolucoes.database import (
    buscar_itens_devolucao,
    listar_devolucoes,
    registrar_conferencia,
)
from modules.devolucoes.parser import ParserRomaneio
from modules.devolucoes.services import comparar_documentos, preparar_banco

st.set_page_config(
    page_title="Centro de Tratamento de Devoluções",
    page_icon="📦",
    layout="wide",
)

preparar_banco()

st.title("📦 Centro de Tratamento de Devoluções")
st.caption("Ambiente isolado de testes — nenhuma lógica do aplicativo oficial é alterada aqui.")

for key, value in {
    "comparacao": None,
    "loja": None,
    "entrada": None,
    "registrado_id": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

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
    registros = listar_devolucoes()
    st.info("Fluxo: romaneio da loja + romaneio da entrada → conferência → registro histórico.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Devoluções registradas", len(registros))
    c2.metric("Conferidas", sum(1 for r in registros if r["status"] == "CONFERIDA"))
    c3.metric("Divergentes", sum(1 for r in registros if r["status"] == "DIVERGENTE"))

elif pages[selecao] == "recebimento":
    st.header("📥 Recebimento da devolução")
    st.write("Envie os dois documentos. Nada é lançado no estoque nesta etapa.")
    col1, col2 = st.columns(2)
    with col1:
        pdf_loja = st.file_uploader(
            "1. Romaneio enviado pela loja", type=["pdf"], key="pdf_loja"
        )
    with col2:
        pdf_entrada = st.file_uploader(
            "2. Romaneio da entrada no CD", type=["pdf"], key="pdf_entrada"
        )

    if pdf_loja and pdf_entrada and st.button(
        "🔎 Ler e comparar os dois romaneios", type="primary"
    ):
        with st.spinner("Lendo os documentos..."):
            try:
                resultado_loja = parser.analisar(pdf_loja.getvalue())
                resultado_entrada = parser.analisar(pdf_entrada.getvalue())
                st.session_state.loja = resultado_loja
                st.session_state.entrada = resultado_entrada
                st.session_state.comparacao = comparar_documentos(
                    resultado_loja, resultado_entrada
                )
                st.session_state.registrado_id = None
                st.success("Documentos lidos e comparação criada.")
            except Exception as exc:
                st.error(f"Não foi possível processar os PDFs: {exc}")

    if st.session_state.loja and st.session_state.entrada:
        st.subheader("Resumo")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "Documento loja",
            st.session_state.loja["cabecalho"].get("numero_documento") or "—",
        )
        c2.metric("Peças loja", st.session_state.loja["total_pecas"])
        c3.metric("Peças entrada", st.session_state.entrada["total_pecas"])
        c4.metric("Itens distintos", len(st.session_state.comparacao or []))

        if st.session_state.registrado_id:
            st.success(
                f"Devolução registrada no histórico. ID interno: {st.session_state.registrado_id}"
            )
        else:
            st.divider()
            st.subheader("Registrar resultado")
            divergente = any(
                item.get("status") != "OK"
                for item in st.session_state.comparacao or []
            )
            if divergente:
                st.warning(
                    "Esta conferência possui divergências. O registro será salvo como DIVERGENTE, sem alterar o estoque."
                )
            else:
                st.success(
                    "Esta conferência está 100% OK. O registro será salvo como CONFERIDA."
                )

            if st.button("✅ Registrar devolução no histórico", type="primary"):
                try:
                    st.session_state.registrado_id = registrar_conferencia(
                        numero_documento=st.session_state.loja["cabecalho"].get(
                            "numero_documento", ""
                        ),
                        data_documento=st.session_state.loja["cabecalho"].get(
                            "data_documento", ""
                        ),
                        arquivo_loja=pdf_loja.name if pdf_loja else "",
                        arquivo_entrada=pdf_entrada.name if pdf_entrada else "",
                        resultado=st.session_state.comparacao or [],
                        total_pecas_loja=st.session_state.loja["total_pecas"],
                        total_pecas_entrada=st.session_state.entrada["total_pecas"],
                    )
                    st.success(
                        "Devolução registrada com sucesso. Nenhuma movimentação de estoque foi realizada."
                    )
                except Exception as exc:
                    st.error(f"Não foi possível registrar a devolução: {exc}")

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
    st.info(
        "Depois do registro, esta área será usada para decidir o destino das mercadorias. Ainda não há alteração de estoque."
    )

elif pages[selecao] == "historico":
    st.header("🕘 Histórico de devoluções")
    registros = listar_devolucoes()

    if not registros:
        st.info("Nenhuma devolução foi registrada ainda.")
    else:
        st.subheader("Filtros")
        f1, f2, f3, f4 = st.columns([1.4, 1.2, 1.2, 1.4])

        busca_documento = f1.text_input(
            "Documento",
            placeholder="Ex.: 84630",
            key="historico_busca_documento",
        ).strip()

        status_options = ["Todos"] + sorted(
            {str(r["status"]) for r in registros if r["status"]}
        )
        filtro_status = f2.selectbox(
            "Status", status_options, key="historico_status"
        )

        datas_validas = []
        for r in registros:
            valor = r["data_documento"]
            if valor:
                try:
                    datas_validas.append(
                        value if False else (valor if isinstance(valor, date) else date.fromisoformat(str(valor)))
                    )
                except (TypeError, ValueError):
                    pass

        data_inicial = f3.date_input(
            "Data inicial",
            value=min(datas_validas) if datas_validas else date.today(),
            key="historico_data_inicial",
        )
        data_final = f4.date_input(
            "Data final",
            value=max(datas_validas) if datas_validas else date.today(),
            key="historico_data_final",
        )

        if data_inicial > data_final:
            st.error("A data inicial não pode ser maior que a data final.")
        else:
            filtrados = []
            for r in registros:
                documento = str(r["numero_documento"] or "")
                if busca_documento and busca_documento.lower() not in documento.lower():
                    continue

                if filtro_status != "Todos" and str(r["status"]) != filtro_status:
                    continue

                data_registro = r["data_documento"]
                try:
                    data_registro = (
                        data_registro
                        if isinstance(data_registro, date)
                        else date.fromisoformat(str(data_registro))
                    )
                except (TypeError, ValueError):
                    data_registro = None

                if data_registro and not (data_inicial <= data_registro <= data_final):
                    continue

                filtrados.append(r)

            st.subheader("Resumo")
            total_pecas_loja = sum(r["total_pecas_loja"] or 0 for r in filtrados)
            total_pecas_entrada = sum(r["total_pecas_entrada"] or 0 for r in filtrados)
            divergentes = sum(1 for r in filtrados if r["status"] == "DIVERGENTE")

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Devoluções", len(filtrados))
            c2.metric("Peças loja", total_pecas_loja)
            c3.metric("Peças entrada", total_pecas_entrada)
            c4.metric("Divergentes", divergentes)

            if not filtrados:
                st.warning("Nenhuma devolução corresponde aos filtros selecionados.")
            else:
                dados = [
                    {
                        "ID": r["id"],
                        "Documento": r["numero_documento"],
                        "Data": (
                            r["data_documento"].strftime("%d/%m/%Y")
                            if isinstance(r["data_documento"], date)
                            else r["data_documento"]
                        ),
                        "Status": r["status"],
                        "Peças loja": r["total_pecas_loja"] or 0,
                        "Peças entrada": r["total_pecas_entrada"] or 0,
                        "Diferença": r["diferenca_total"] or 0,
                        "Itens distintos": r["itens_distintos"] or 0,
                        "Registrado em": r["registrado_em"] or r["criado_em"],
                    }
                    for r in filtrados
                ]
                st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)

                st.subheader("Detalhamento")
                opcoes = [
                    f"#{r['id']} — documento {r['numero_documento']}"
                    for r in filtrados
                ]
                escolha = st.selectbox("Selecione uma devolução", opcoes, key="historico_detalhe")
                registro = filtrados[opcoes.index(escolha)]
                registro_id = int(registro["id"])

                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Documento", registro["numero_documento"])
                c2.metric("Status", registro["status"])
                c3.metric("Peças loja", registro["total_pecas_loja"] or 0)
                c4.metric("Peças entrada", registro["total_pecas_entrada"] or 0)

                if isinstance(registro["data_documento"], date):
                    data_display = registro["data_documento"].strftime("%d/%m/%Y")
                else:
                    data_display = registro["data_documento"] or "—"

                st.write(f"**Data:** {data_display}")
                st.write(f"**Resultado da conferência:** {registro['resultado_conferencia'] or '—'}")
                st.write(f"**Romaneio da loja:** {registro['arquivo_loja'] or '—'}")
                st.write(f"**Romaneio da entrada:** {registro['arquivo_entrada'] or '—'}")

                itens = buscar_itens_devolucao(registro_id)
                if itens:
                    itens_df = pd.DataFrame([dict(item) for item in itens])
                    st.write(f"**Itens: {len(itens_df)} códigos distintos**")
                    st.dataframe(itens_df, use_container_width=True, hide_index=True)
                else:
                    st.info("Esta devolução não possui itens registrados.")

elif pages[selecao] == "indicadores":
    st.header("📊 Indicadores")
    registros = listar_devolucoes()
    if registros:
        total_loja = sum(r["total_pecas_loja"] or 0 for r in registros)
        total_entrada = sum(r["total_pecas_entrada"] or 0 for r in registros)
        c1, c2, c3 = st.columns(3)
        c1.metric("Peças da loja", total_loja)
        c2.metric("Peças da entrada", total_entrada)
        c3.metric("Diferença acumulada", total_entrada - total_loja)
    else:
        st.info("Registre pelo menos uma devolução para gerar indicadores.")

elif pages[selecao] == "configuracoes":
    st.header("⚙️ Configurações")
    st.info("Configurações específicas do laboratório de devoluções.")

st.sidebar.divider()
st.sidebar.caption("🧪 AMBIENTE DE TESTE")
st.sidebar.caption("Projeto independente do app oficial.")
