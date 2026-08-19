from datetime import date

import pandas as pd
import streamlit as st

from modules.devolucoes.database import buscar_itens_devolucao, listar_devolucoes, registrar_conferencia
from modules.devolucoes.parser import ParserRomaneio
from modules.devolucoes.services import comparar_documentos, preparar_banco
from modules.devolucoes.tratamento import (
    DESTINOS,
    init_tratamento_db,
    listar_devolucoes_para_tratamento,
    listar_tratamentos,
    preparar_devolucao,
    quantidades_tratadas,
    resumo_tratamentos,
    salvar_tratamentos,
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

for key, value in {"comparacao": None, "loja": None, "entrada": None, "loja_selecionada": None, "registrado_id": None}.items():
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
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devoluções registradas", len(registros))
    c2.metric("Aguardando tratamento", sum(1 for r in registros if r["status"] in ("AGUARDANDO TRATAMENTO", "DIVERGENTE", "CONFERIDA")))
    c3.metric("Em tratamento", sum(1 for r in registros if r["status"] == "AGUARDANDO TRATAMENTO"))
    c4.metric("Concluídas", sum(1 for r in registros if r["status"] == "CONCLUÍDA"))
    st.info("Fluxo: loja + entrada → conferência → registro → tratamento. Nenhuma etapa de tratamento altera o estoque.")

elif pages[selecao] == "recebimento":
    st.header("📥 Recebimento da devolução")
    st.write("Selecione a loja e envie os dois documentos. Nada é lançado no estoque nesta etapa.")
    loja_selecionada = st.selectbox(
        "Loja da devolução", ["Selecione uma loja"] + LOJAS,
        index=(LOJAS.index(st.session_state.loja_selecionada) + 1) if st.session_state.loja_selecionada in LOJAS else 0,
        key="recebimento_loja",
    )
    if loja_selecionada != "Selecione uma loja":
        st.session_state.loja_selecionada = loja_selecionada

    c1, c2 = st.columns(2)
    with c1:
        pdf_loja = st.file_uploader("1. Romaneio enviado pela loja", type=["pdf"], key="pdf_loja")
    with c2:
        pdf_entrada = st.file_uploader("2. Romaneio da entrada no CD", type=["pdf"], key="pdf_entrada")

    pode_comparar = loja_selecionada != "Selecione uma loja" and pdf_loja and pdf_entrada
    if pode_comparar and st.button("🔎 Ler e comparar os dois romaneios", type="primary"):
        try:
            with st.spinner("Lendo os documentos..."):
                st.session_state.loja = parser.analisar(pdf_loja.getvalue())
                st.session_state.entrada = parser.analisar(pdf_entrada.getvalue())
                st.session_state.comparacao = comparar_documentos(st.session_state.loja, st.session_state.entrada)
                st.session_state.registrado_id = None
            st.success("Documentos lidos e comparação criada.")
        except Exception as exc:
            st.error(f"Não foi possível processar os PDFs: {exc}")

    if st.session_state.loja and st.session_state.entrada:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documento loja", st.session_state.loja["cabecalho"].get("numero_documento") or "—")
        c2.metric("Loja", st.session_state.loja_selecionada or "—")
        c3.metric("Peças loja", st.session_state.loja["total_pecas"])
        c4.metric("Peças entrada", st.session_state.entrada["total_pecas"])
        st.metric("Itens distintos", len(st.session_state.comparacao or []))
        if not st.session_state.registrado_id:
            divergente = any(item.get("status") != "OK" for item in st.session_state.comparacao or [])
            st.warning("A conferência possui divergências." if divergente else "A conferência está 100% OK.")
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
                    preparar_devolucao(st.session_state.registrado_id)
                    st.success(f"Devolução registrada. ID interno: {st.session_state.registrado_id}")
                except Exception as exc:
                    st.error(f"Não foi possível registrar a devolução: {exc}")
        else:
            st.success(f"Devolução registrada no histórico. ID interno: {st.session_state.registrado_id}")

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
        st.success("Nenhuma divergência encontrada.") if pendencias.empty else st.dataframe(pendencias, use_container_width=True, hide_index=True)
    else:
        st.info("Nenhuma conferência foi executada ainda.")

elif pages[selecao] == "decisao":
    st.header("📋 Tratamento da devolução")
    st.caption("Defina o destino das peças sem alterar o estoque. A quantidade pode ser tratada em partes.")
    registros = listar_devolucoes_para_tratamento()
    if not registros:
        st.success("Não há devoluções aguardando tratamento.")
    else:
        opcoes = [f"#{r['id']} — {r['loja'] or 'Loja não informada'} — doc. {r['numero_documento']}" for r in registros]
        escolha = st.selectbox("Devolução", opcoes, key="tratamento_devolucao")
        registro = registros[opcoes.index(escolha)]
        devolucao_id = int(registro["id"])
        if registro["status"] == "CONFERIDA":
            preparar_devolucao(devolucao_id)
        itens = buscar_itens_devolucao(devolucao_id)
        tratadas = quantidades_tratadas(devolucao_id)
        total_entrada = int(registro["total_pecas_entrada"] or 0)
        total_tratada = int(registro["pecas_tratadas"] or 0)
        restantes_total = total_entrada - total_tratada
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Documento", registro["numero_documento"])
        c2.metric("Loja", registro["loja"] or "—")
        c3.metric("Peças entrada", total_entrada)
        c4.metric("Restantes", max(restantes_total, 0))

        pendentes = []
        for item in itens:
            restante = int(item["quantidade_entrada"] or 0) - int(tratadas.get(int(item["id"]), 0))
            if restante > 0:
                pendentes.append((item, restante))

        if pendentes:
            opcoes_item = [f"{item['codigo_barras']} — {item['descricao']} — {item['grade']} — restante: {restante}" for item, restante in pendentes]
            escolha_item = st.selectbox("Item para tratar", opcoes_item, key="tratamento_item")
            item, restante = pendentes[opcoes_item.index(escolha_item)]
            c1, c2 = st.columns(2)
            with c1:
                quantidade = st.number_input("Quantidade", min_value=1, max_value=restante, value=restante, step=1, key=f"trat_qtd_{item['id']}")
            with c2:
                destino = st.selectbox("Destino", DESTINOS, key=f"trat_dest_{item['id']}")
            st.write(f"**Código:** {item['codigo_barras']}  **Produto:** {item['descricao']}  **Grade:** {item['grade']}")
            observacao = st.text_input("Observação", key=f"trat_obs_{item['id']}")
            if st.button("✅ Registrar tratamento", type="primary"):
                try:
                    salvar_tratamentos(devolucao_id, [{"devolucao_item_id": int(item["id"]), "quantidade": int(quantidade), "destino": destino, "observacao": observacao}])
                    st.success("Tratamento registrado. Nenhuma movimentação de estoque foi realizada.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível registrar o tratamento: {exc}")
        else:
            st.success("Todas as peças dessa devolução já foram tratadas.")

        historico_trat = listar_tratamentos(devolucao_id)
        if historico_trat:
            st.subheader("Tratamentos já registrados")
            st.dataframe(pd.DataFrame([dict(x) for x in historico_trat]), use_container_width=True, hide_index=True)
            resumo = resumo_tratamentos(devolucao_id)
            st.write("**Resumo por destino:** " + " · ".join(f"{k}: {v}" for k, v in resumo.items()))

elif pages[selecao] == "historico":
    st.header("🕘 Histórico de devoluções")
    registros = listar_devolucoes()
    if not registros:
        st.info("Nenhuma devolução foi registrada ainda.")
    else:
        f1, f2, f3, f4 = st.columns(4)
        busca = f1.text_input("Documento", placeholder="Ex.: 84630").strip().lower()
        lojas = sorted({str(r["loja"]) for r in registros if r.get("loja")})
        loja_filtro = f2.selectbox("Loja", ["Todas"] + lojas)
        status_filtro = f3.selectbox("Status", ["Todos"] + sorted({str(r["status"]) for r in registros if r["status"]}))
        datas = []
        for r in registros:
            if r["data_documento"]:
                try:
                    datas.append(r["data_documento"] if isinstance(r["data_documento"], date) else date.fromisoformat(str(r["data_documento"])))
                except (TypeError, ValueError):
                    pass
        inicio = f4.date_input("Data inicial", value=min(datas) if datas else date.today())
        fim = st.date_input("Data final", value=max(datas) if datas else date.today())
        if inicio > fim:
            inicio, fim = fim, inicio

        filtrados = []
        for r in registros:
            if busca and busca not in str(r["numero_documento"] or "").lower():
                continue
            if loja_filtro != "Todas" and str(r["loja"] or "") != loja_filtro:
                continue
            if status_filtro != "Todos" and str(r["status"]) != status_filtro:
                continue
            d = r["data_documento"]
            try:
                d = d if isinstance(d, date) else (date.fromisoformat(str(d)) if d else None)
            except (TypeError, ValueError):
                d = None
            if d and not (inicio <= d <= fim):
                continue
            filtrados.append(r)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Devoluções", len(filtrados))
        c2.metric("Peças loja", sum(r["total_pecas_loja"] or 0 for r in filtrados))
        c3.metric("Peças entrada", sum(r["total_pecas_entrada"] or 0 for r in filtrados))
        c4.metric("Concluídas", sum(r["status"] == "CONCLUÍDA" for r in filtrados))
        if filtrados:
            dados = [{"ID": r["id"], "Loja": r["loja"] or "—", "Documento": r["numero_documento"], "Data": r["data_documento"].strftime("%d/%m/%Y") if isinstance(r["data_documento"], date) else r["data_documento"], "Status": r["status"], "Peças loja": r["total_pecas_loja"] or 0, "Peças entrada": r["total_pecas_entrada"] or 0, "Diferença": r["diferenca_total"] or 0} for r in filtrados]
            st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)
            opcoes = [f"#{r['id']} — {r['loja'] or '—'} — doc. {r['numero_documento']}" for r in filtrados]
            escolha = st.selectbox("Detalhar devolução", opcoes)
            registro = filtrados[opcoes.index(escolha)]
            itens = buscar_itens_devolucao(int(registro["id"]))
            st.write(f"**Romaneio loja:** {registro['arquivo_loja'] or '—'}")
            st.write(f"**Romaneio entrada:** {registro['arquivo_entrada'] or '—'}")
            if itens:
                st.dataframe(pd.DataFrame([dict(x) for x in itens]), use_container_width=True, hide_index=True)
        else:
            st.warning("Nenhuma devolução corresponde aos filtros.")

elif pages[selecao] == "indicadores":
    st.header("📊 Indicadores")
    registros = listar_devolucoes()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devoluções", len(registros))
    c2.metric("Peças loja", sum(r["total_pecas_loja"] or 0 for r in registros))
    c3.metric("Peças entrada", sum(r["total_pecas_entrada"] or 0 for r in registros))
    c4.metric("Concluídas", sum(r["status"] == "CONCLUÍDA" for r in registros))

elif pages[selecao] == "configuracoes":
    st.header("⚙️ Configurações")
    st.info("Configurações específicas do laboratório de devoluções.")

st.sidebar.divider()
st.sidebar.caption("🧪 AMBIENTE DE TESTE")
st.sidebar.caption("Projeto independente do app oficial.")
