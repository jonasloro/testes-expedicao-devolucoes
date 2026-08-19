from datetime import date

import pandas as pd
import streamlit as st

from modules.devolucoes.anapolis import bipar, resumo as resumo_anapolis
from modules.devolucoes.database import buscar_itens_devolucao, listar_devolucoes, registrar_conferencia
from modules.devolucoes.parser import ParserRomaneio
from modules.devolucoes.services import comparar_documentos, obter_defeitos_documento, preparar_banco
from modules.devolucoes.tratamento import (
    DESTINOS,
    init_tratamento_db,
    listar_devolucoes_para_tratamento,
    quantidades_tratadas,
    listar_tratamentos,
    salvar_tratamentos_em_lote,
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

pages = {
    "🏠 Dashboard": "dashboard",
    "📥 Recebimento": "recebimento",
    "🔎 Conferência": "conferencia",
    "⚠️ Pendências": "pendencias",
    "📋 Aguardando decisão": "decisao",
    "🩹 Defeitos Anápolis": "anapolis",
    "🕘 Histórico": "historico",
    "📊 Indicadores": "indicadores",
    "⚙️ Configurações": "configuracoes",
}

selecao = st.sidebar.radio("Centro de Devoluções", list(pages.keys()))
parser = ParserRomaneio()

if pages[selecao] == "dashboard":
    st.header("Dashboard")
    registros = listar_devolucoes()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devoluções registradas", len(registros))
    c2.metric("Aguardando tratamento", sum(1 for r in registros if r["status"] in {"AGUARDANDO TRATAMENTO", "DIVERGENTE", "CONFERIDA"}))
    c3.metric("Concluídas", sum(1 for r in registros if r["status"] == "CONCLUÍDA"))
    c4.metric("Lojas com registros", len({r["loja"] for r in registros if r.get("loja")}))
    st.info("Fluxo: romaneio da loja + romaneio CD + romaneio Anápolis → conferência → registro → tratamento. Bipagem de defeitos permanece como recurso auxiliar.")

elif pages[selecao] == "recebimento":
    st.header("📥 Recebimento da devolução")
    st.write("Selecione a loja e envie os três documentos. A conferência oficial considera Entrada CD + Entrada Anápolis.")

    loja_selecionada = st.selectbox(
        "Loja da devolução",
        ["Selecione uma loja"] + LOJAS,
        index=(LOJAS.index(st.session_state.loja_selecionada) + 1) if st.session_state.loja_selecionada in LOJAS else 0,
        key="recebimento_loja",
    )
    if loja_selecionada != "Selecione uma loja":
        st.session_state.loja_selecionada = loja_selecionada

    c1, c2, c3 = st.columns(3)
    with c1:
        pdf_loja = st.file_uploader("1. Romaneio enviado pela loja", type=["pdf"], key="pdf_loja")
    with c2:
        pdf_entrada = st.file_uploader("2. Romaneio da entrada no CD", type=["pdf"], key="pdf_entrada")
    with c3:
        pdf_anapolis = st.file_uploader("3. Romaneio da entrada em Anápolis", type=["pdf"], key="pdf_anapolis")

    pode_comparar = (
        loja_selecionada != "Selecione uma loja"
        and pdf_loja is not None
        and pdf_entrada is not None
        and pdf_anapolis is not None
    )

    if pode_comparar and st.button("🔎 Ler e comparar os três romaneios", type="primary"):
        try:
            with st.spinner("Lendo os três documentos e montando a conferência..."):
                resultado_loja = parser.analisar(pdf_loja.getvalue())
                resultado_entrada = parser.analisar(pdf_entrada.getvalue())
                resultado_anapolis = parser.analisar(pdf_anapolis.getvalue())

                defeitos_anapolis = {}
                for item in resultado_anapolis.get("itens", []):
                    codigo = str(item["codigo_barras"]).strip()
                    defeitos_anapolis[codigo] = defeitos_anapolis.get(codigo, 0) + int(item["quantidade"])

                st.session_state.loja = resultado_loja
                st.session_state.entrada = resultado_entrada
                st.session_state.anapolis_romaneio = resultado_anapolis
                st.session_state.comparacao = comparar_documentos(
                    resultado_loja,
                    resultado_entrada,
                    defeitos_anapolis,
                )
                st.session_state.registrado_id = None

            st.success("Os três romaneios foram lidos e a conferência foi criada.")
        except Exception as exc:
            st.error(f"Não foi possível processar os PDFs: {exc}")

    if st.session_state.loja and st.session_state.entrada and st.session_state.anapolis_romaneio:
        total_anapolis = int(st.session_state.anapolis_romaneio["total_pecas"] or 0)
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Documento", st.session_state.loja["cabecalho"].get("numero_documento") or "—")
        c2.metric("Loja", st.session_state.loja_selecionada or "—")
        c3.metric("Peças loja", st.session_state.loja["total_pecas"])
        c4.metric("Entrada CD", st.session_state.entrada["total_pecas"])
        c5.metric("Entrada Anápolis", total_anapolis)

        df = pd.DataFrame(st.session_state.comparacao or [])
        st.metric("Itens distintos", len(df))

        if not st.session_state.registrado_id:
            divergente = not df.empty and (df["status"] != "OK").any()
            if divergente:
                st.warning("A conferência possui diferenças: Loja ≠ Entrada CD + Entrada Anápolis.")
            else:
                st.success("A conferência está 100% OK: Loja = Entrada CD + Entrada Anápolis.")

            if st.button("✅ Registrar devolução no histórico", type="primary"):
                try:
                    st.session_state.registrado_id = registrar_conferencia(
                        numero_documento=st.session_state.loja["cabecalho"].get("numero_documento", ""),
                        data_documento=st.session_state.loja["cabecalho"].get("data_documento", ""),
                        arquivo_loja=pdf_loja.name,
                        arquivo_entrada=pdf_entrada.name,
                        arquivo_anapolis=pdf_anapolis.name,
                        resultado=st.session_state.comparacao or [],
                        total_pecas_loja=st.session_state.loja["total_pecas"],
                        total_pecas_entrada=st.session_state.entrada["total_pecas"],
                        total_pecas_anapolis=st.session_state.anapolis_romaneio["total_pecas"],
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
        st.info("Envie os três romaneios na tela Recebimento para iniciar a conferência.")
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
    st.header("📋 Tratamento da devolução")
    st.caption("Tratativa em lote. Os destinos atuais são somente: Avaria, Estocar, Armazenar Porta-Palete e Armazenar — Rua 1.")

    registros = listar_devolucoes_para_tratamento()
    if not registros:
        st.success("Não há devoluções aguardando tratamento.")
    else:
        opcoes = [f"#{r['id']} — {r['loja'] or 'Loja não informada'} — doc. {r['numero_documento']}" for r in registros]
        escolha = st.selectbox("Devolução", opcoes, key="tratamento_devolucao")
        registro = registros[opcoes.index(escolha)]
        devolucao_id = int(registro["id"])

        itens = buscar_itens_devolucao(devolucao_id)
        tratadas = quantidades_tratadas(devolucao_id)
        total_entrada = int(registro["total_pecas_entrada"] or 0)
        total_tratada = int(registro["pecas_tratadas"] or 0)
        restante_total = max(total_entrada - total_tratada, 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documento", registro["numero_documento"])
        c2.metric("Loja", registro["loja"] or "—")
        c3.metric("Peças entrada CD", total_entrada)
        c4.metric("Restantes", restante_total)

        pendentes = []
        for item in itens:
            restante = int(item["quantidade_entrada"] or 0) - int(tratadas.get(int(item["id"]), 0))
            if restante > 0:
                pendentes.append((item, restante))

        if pendentes:
            opcoes_item = [f"{item['codigo_barras']} — {item['descricao']} — {item['grade']} — restante: {restante}" for item, restante in pendentes]
            selecionados = st.multiselect("Itens que receberão a mesma tratativa", opcoes_item, key="trat_itens_lote")
            destino = st.selectbox("Destino do lote", DESTINOS, key="trat_destino_lote")
            observacao = st.text_input("Observação do lote", key="trat_obs_lote")

            if selecionados:
                escolhidos = []
                total_selecionado = 0
                for texto in selecionados:
                    idx = opcoes_item.index(texto)
                    item, restante = pendentes[idx]
                    escolhidos.append((item, restante))
                    total_selecionado += restante
                st.info(f"Serão tratadas até **{total_selecionado} peças** desses {len(escolhidos)} itens.")
                tratar_total = st.checkbox("Tratar todo o restante desses itens", value=True, key="trat_todo_lote")
                quantidade_parcial = None
                if not tratar_total:
                    quantidade_parcial = st.number_input("Quantidade total do lote", min_value=1, max_value=total_selecionado, value=min(total_selecionado, 1), step=1, key="trat_qtd_lote")

                if st.button("✅ Aplicar tratativa ao lote", type="primary"):
                    try:
                        lancamentos = []
                        restante_para_distribuir = int(quantidade_parcial or total_selecionado) if not tratar_total else None
                        for item, restante in escolhidos:
                            qtd = restante if tratar_total else min(restante, restante_para_distribuir or 0)
                            if qtd > 0:
                                lancamentos.append({
                                    "devolucao_item_id": int(item["id"]),
                                    "quantidade": qtd,
                                    "destino": destino,
                                    "observacao": observacao,
                                })
                                if restante_para_distribuir is not None:
                                    restante_para_distribuir -= qtd
                                    if restante_para_distribuir <= 0:
                                        break
                        salvar_tratamentos_em_lote(devolucao_id, lancamentos)
                        st.success("Tratativa em lote registrada. Nenhuma movimentação de estoque foi realizada.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Não foi possível registrar a tratativa: {exc}")
        else:
            st.success("Todas as peças dessa devolução já foram tratadas.")

        historico_trat = listar_tratamentos(devolucao_id)
        if historico_trat:
            st.subheader("Tratamentos registrados")
            dados_trat = [
                {
                    "Código": x["codigo_barras"],
                    "Produto": x["descricao"],
                    "Grade": x["grade"],
                    "Quantidade": x["quantidade"],
                    "Destino": x["destino"],
                    "Observação": x["observacao"] or "",
                }
                for x in historico_trat
            ]
            st.dataframe(pd.DataFrame(dados_trat), use_container_width=True, hide_index=True)

elif pages[selecao] == "anapolis":
    st.header("🩹 Defeitos Anápolis")
    st.write("Recurso auxiliar para situações em que o romaneio de Anápolis ainda não estiver disponível. O fluxo oficial usa o terceiro romaneio.")

    documento = st.text_input("Documento da devolução", placeholder="Ex.: 84630", key="anapolis_documento").strip()
    codigo = st.text_input("Código de barras", placeholder="Bipe ou digite o código", key="anapolis_codigo").strip()

    c1, c2 = st.columns(2)
    with c1:
        if st.button("📦 Registrar bip", type="primary", disabled=not documento or not codigo):
            try:
                bipar(documento, codigo)
                st.success("Bip auxiliar registrado em Anápolis.")
                st.rerun()
            except Exception as exc:
                st.error(f"Não foi possível registrar o bip: {exc}")
    with c2:
        st.info("O bip é apenas um recurso auxiliar. A conferência oficial passa a usar o romaneio de Anápolis.")

    if documento:
        registros_anapolis = resumo_anapolis(documento)
        if registros_anapolis:
            df_a = pd.DataFrame([dict(r) for r in registros_anapolis])
            st.subheader("Bips auxiliares registrados")
            st.dataframe(df_a, use_container_width=True, hide_index=True)
            st.metric("Total de peças bipadas", int(df_a["quantidade"].sum()))
        else:
            st.info("Nenhum bip auxiliar para este documento.")

elif pages[selecao] == "historico":
    st.header("🕘 Histórico de devoluções")
    registros = listar_devolucoes()

    if not registros:
        st.info("Nenhuma devolução foi registrada ainda.")
    else:
        f1, f2, f3, f4 = st.columns(4)
        busca_documento = f1.text_input("Documento", placeholder="Ex.: 84630", key="historico_busca").strip().lower()
        lojas = sorted({str(r["loja"]) for r in registros if r.get("loja")})
        filtro_loja = f2.selectbox("Loja", ["Todas"] + lojas, key="historico_loja")
        status_options = ["Todos"] + sorted({str(r["status"]) for r in registros if r["status"]})
        filtro_status = f3.selectbox("Status", status_options, key="historico_status")

        datas = []
        for r in registros:
            valor = r["data_documento"]
            if valor:
                try:
                    datas.append(valor if isinstance(valor, date) else date.fromisoformat(str(valor)))
                except (TypeError, ValueError):
                    pass
        data_inicial = f4.date_input("Data inicial", value=min(datas) if datas else date.today(), key="historico_inicio")
        data_final = st.date_input("Data final", value=max(datas) if datas else date.today(), key="historico_fim")
        if data_inicial > data_final:
            data_inicial, data_final = data_final, data_inicial

        filtrados = []
        for r in registros:
            if busca_documento and busca_documento not in str(r["numero_documento"] or "").lower():
                continue
            if filtro_loja != "Todas" and str(r["loja"] or "") != filtro_loja:
                continue
            if filtro_status != "Todos" and str(r["status"]) != filtro_status:
                continue
            d = r["data_documento"]
            try:
                d = d if isinstance(d, date) else date.fromisoformat(str(d))
            except (TypeError, ValueError):
                d = None
            if d and not (data_inicial <= d <= data_final):
                continue
            filtrados.append(r)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Devoluções", len(filtrados))
        c2.metric("Peças loja", sum(r["total_pecas_loja"] or 0 for r in filtrados))
        c3.metric("Peças CD", sum(r["total_pecas_entrada"] or 0 for r in filtrados))
        c4.metric("Peças Anápolis", sum(r.get("total_pecas_anapolis") or 0 for r in filtrados))

        if filtrados:
            dados = []
            for r in filtrados:
                data_texto = r["data_documento"].strftime("%d/%m/%Y") if isinstance(r["data_documento"], date) else r["data_documento"]
                dados.append({
                    "ID": r["id"],
                    "Loja": r["loja"] or "—",
                    "Documento": r["numero_documento"],
                    "Data": data_texto,
                    "Status": r["status"],
                    "Peças loja": r["total_pecas_loja"] or 0,
                    "Peças CD": r["total_pecas_entrada"] or 0,
                    "Peças Anápolis": r.get("total_pecas_anapolis") or 0,
                    "Diferença": r["diferenca_total"] or 0,
                    "Itens": r["itens_distintos"] or 0,
                })
            st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)

            opcoes = [f"#{r['id']} — {r['loja'] or 'Loja não informada'} — documento {r['numero_documento']}" for r in filtrados]
            escolha = st.selectbox("Detalhar devolução", opcoes, key="historico_detalhe")
            registro = filtrados[opcoes.index(escolha)]
            registro_id = int(registro["id"])

            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Documento", registro["numero_documento"])
            c2.metric("Loja", registro["loja"] or "—")
            c3.metric("Status", registro["status"])
            c4.metric("Diferença", registro["diferenca_total"] or 0)
            st.write(f"**Romaneio da loja:** {registro['arquivo_loja'] or '—'}")
            st.write(f"**Romaneio da entrada CD:** {registro['arquivo_entrada'] or '—'}")
            st.write(f"**Romaneio da entrada Anápolis:** {registro.get('arquivo_anapolis') or '—'}")

            itens = buscar_itens_devolucao(registro_id)
            if itens:
                st.subheader("Itens da devolução")
                st.dataframe(pd.DataFrame([dict(i) for i in itens]), use_container_width=True, hide_index=True)
            historico_trat = listar_tratamentos(registro_id)
            if historico_trat:
                st.subheader("Tratamentos")
                st.dataframe(pd.DataFrame([dict(x) for x in historico_trat]), use_container_width=True, hide_index=True)
        else:
            st.warning("Nenhuma devolução corresponde aos filtros selecionados.")

elif pages[selecao] == "indicadores":
    st.header("📊 Indicadores")
    registros = listar_devolucoes()
    if registros:
        total_loja = sum(r["total_pecas_loja"] or 0 for r in registros)
        total_cd = sum(r["total_pecas_entrada"] or 0 for r in registros)
        total_anapolis = sum(r.get("total_pecas_anapolis") or 0 for r in registros)
        c1, c2, c3 = st.columns(3)
        c1.metric("Peças da loja", total_loja)
        c2.metric("Peças da entrada CD", total_cd)
        c3.metric("Peças da entrada Anápolis", total_anapolis)
        st.metric("Diferença acumulada", total_cd + total_anapolis - total_loja)
    else:
        st.info("Registre pelo menos uma devolução para gerar indicadores.")

elif pages[selecao] == "configuracoes":
    st.header("⚙️ Configurações")
    st.info("Configurações específicas do laboratório de devoluções.")

st.sidebar.divider()
st.sidebar.caption("🧪 AMBIENTE DE TESTE")
st.sidebar.caption("Projeto independente do app oficial.")
