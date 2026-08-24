import pandas as pd
import streamlit as st

from ..database import registrar_conferencia
from ..parser import ParserRomaneio
from ..services import comparar_documentos
from ..pedidos_database import listar_pedidos, vincular_devolucao
from .conferencia import formatar_tabela
from .tratamento import render as _render_tratamento


def _tab_recebimento(lojas: list[str], parser: ParserRomaneio) -> None:
    st.write("Selecione um pedido de devolução marcado como RECEBIDO. A conferência oficial considera Entrada CD + Entrada Anápolis.")

    # Regra do fluxo: o pedido só entra no Recebimento depois que seu status
    # operacional for alterado para RECEBIDO na tela de Pedidos de Devolução.
    pedidos = [p for p in listar_pedidos() if str(p["status"]).upper() == "RECEBIDO"]
    opcoes_pedido = ["Nenhum pedido selecionado"] + [
        f"#{p['id']} — Nota {p['numero_nota']} — {p['loja']} — {p['volumes']} vol."
        for p in pedidos
    ]
    pedido_escolha = st.selectbox("Pedido de devolução", opcoes_pedido, key="recebimento_pedido")
    pedido_selecionado = None
    if pedido_escolha != "Nenhum pedido selecionado":
        pedido_selecionado = pedidos[opcoes_pedido.index(pedido_escolha) - 1]
        st.session_state.pedido_recebimento_id = int(pedido_selecionado["id"])
        st.session_state.loja_selecionada = str(pedido_selecionado["loja"])
        st.info(
            f"**Pedido #{pedido_selecionado['id']}** · Nota **{pedido_selecionado['numero_nota']}** · "
            f"{pedido_selecionado['volumes']} volumes · {pedido_selecionado['total_lacres']} lacres. "
            "A carga será conferida dentro desta demanda."
        )
        st.caption(f"Transportadora: {pedido_selecionado['transportadora'] or '—'}")

    if pedido_selecionado:
        loja_selecionada = str(pedido_selecionado["loja"])
        st.text_input("Loja da devolução", value=loja_selecionada, disabled=True)
    else:
        loja_selecionada = st.selectbox(
            "Loja da devolução",
            ["Selecione uma loja"] + lojas,
            index=(lojas.index(st.session_state.loja_selecionada) + 1) if st.session_state.loja_selecionada in lojas else 0,
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

                if pedido_selecionado:
                    st.session_state.pedido_recebimento_id = int(pedido_selecionado["id"])

            st.success("Os três romaneios foram lidos e a conferência foi criada — veja o resultado na aba 🔎 Conferência.")
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
                    pedido_id = st.session_state.get("pedido_recebimento_id")
                    if pedido_id:
                        vincular_devolucao(int(pedido_id), int(st.session_state.registrado_id))
                    st.success(f"Devolução registrada no Neon. ID interno: {st.session_state.registrado_id}")
                except Exception as exc:
                    st.error(f"Não foi possível registrar a devolução: {exc}")
        else:
            st.success(f"Devolução registrada no histórico. ID interno: {st.session_state.registrado_id}")


def _tab_conferencia() -> None:
    if not st.session_state.comparacao:
        st.info("Envie os três romaneios na aba 📥 Recebimento para iniciar a conferência.")
        return

    df = pd.DataFrame(st.session_state.comparacao)
    c1, c2, c3 = st.columns(3)
    c1.metric("✅ OK", int((df["status"] == "OK").sum()))
    c2.metric("🔴 Faltou", int((df["status"] == "FALTOU").sum()))
    c3.metric("🟡 Excesso", int((df["status"] == "EXCESSO").sum()))
    st.caption("Regra: Loja = Entrada CD + Entrada Anápolis. A origem que causou a diferença aparece nas colunas CD e Anápolis.")
    st.dataframe(formatar_tabela(df), use_container_width=True, hide_index=True)


def _tab_pendencias() -> None:
    if not st.session_state.comparacao:
        st.info("Nenhuma conferência foi executada ainda.")
        return

    df = pd.DataFrame(st.session_state.comparacao)
    pendencias = df[df["status"] != "OK"]
    if pendencias.empty:
        st.success("Nenhuma divergência encontrada.")
    else:
        st.dataframe(formatar_tabela(pendencias), use_container_width=True, hide_index=True)


def render(lojas: list[str], parser: ParserRomaneio) -> None:
    st.header("📥 Recebimento, Conferência, Pendências e Tratativa")

    n_pendencias = 0
    if st.session_state.comparacao:
        n_pendencias = int((pd.DataFrame(st.session_state.comparacao)["status"] != "OK").sum())

    aba_recebimento, aba_conferencia, aba_pendencias, aba_tratativa = st.tabs([
        "📥 Recebimento",
        "🔎 Conferência",
        f"⚠️ Pendências ({n_pendencias})" if n_pendencias else "⚠️ Pendências",
        "📋 Tratativa",
    ])
    with aba_recebimento:
        _tab_recebimento(lojas, parser)
    with aba_conferencia:
        _tab_conferencia()
    with aba_pendencias:
        _tab_pendencias()
    with aba_tratativa:
        _render_tratamento()
