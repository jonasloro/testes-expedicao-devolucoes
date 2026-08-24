import pandas as pd
import streamlit as st

from ..pedido_email import analisar_email
from ..pedidos_database import atualizar_status, buscar_pedido, criar_pedido, listar_pedidos


STATUS = ["Todos", "PENDENTE", "EM RECEBIMENTO", "RECEBIDO", "CONFERIDO", "CONCLUIDO", "CANCELADO"]


def _formatar_status(status: str) -> str:
    mapa = {
        "PENDENTE": "🔵 Pendente",
        "EM RECEBIMENTO": "🟡 Em recebimento",
        "RECEBIDO": "🟢 Recebido",
        "CONFERIDO": "🟢 Conferido",
        "CONCLUIDO": "✅ Concluído",
        "CANCELADO": "🔴 Cancelado",
    }
    return mapa.get(str(status).upper(), str(status))


def _mostrar_pedido(pedido: dict) -> None:
    st.subheader(f"🔎 Inspeção da devolução #{pedido['id']}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Documento", pedido["numero_nota"])
    c2.metric("Loja", pedido["loja"] or "—")
    c3.metric("Volumes", int(pedido["volumes"] or 0))
    c4.metric("Lacres", len(pedido.get("lacres", [])))

    c1, c2 = st.columns(2)
    c1.write(
        f"**Data da coleta:** "
        f"{pedido['data_coleta'].strftime('%d/%m/%Y') if pedido.get('data_coleta') else 'Não informada'}"
    )
    c2.write(f"**Transportadora:** {pedido.get('transportadora') or 'Não informada'}")
    st.write(f"**Status:** {_formatar_status(pedido['status'])}")

    lacres = pedido.get("lacres", [])
    if lacres:
        with st.expander(f"🔒 Lacres ({len(lacres)})", expanded=True):
            st.dataframe(
                pd.DataFrame(
                    [{"Lacre": x["lacre"], "Conteúdo": x["descricao"] or "—"} for x in lacres]
                ),
                use_container_width=True,
                hide_index=True,
            )
    else:
        st.info("Nenhum lacre foi identificado neste pedido.")

    if pedido.get("observacao"):
        with st.expander("📨 Conteúdo original da solicitação", expanded=False):
            st.write(pedido["observacao"])

    with st.expander("⚙️ Alterar status", expanded=False):
        novo_status = st.selectbox(
            "Novo status",
            STATUS[1:],
            index=STATUS[1:].index(pedido["status"]) if pedido["status"] in STATUS[1:] else 0,
            key=f"pedido_status_{pedido['id']}",
        )
        if st.button("Salvar status", key=f"pedido_salvar_{pedido['id']}"):
            atualizar_status(int(pedido["id"]), novo_status)
            st.success("Status atualizado.")
            st.rerun()


def _mostrar_previa(dados: dict) -> None:
    st.subheader("Prévia do pedido")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nota", dados["numero_nota"])
    c2.metric("Loja", dados["loja"])
    c3.metric("Volumes", len(dados["lacres"]))
    c4.metric("Lacres", len(dados["lacres"]))

    st.write(
        f"**Data da coleta:** "
        f"{dados['data_coleta'].strftime('%d/%m/%Y') if dados['data_coleta'] else 'Não informada'}"
    )
    st.write(f"**Transportadora:** {dados['transportadora'] or 'Não informada'}")

    if not dados["lacres"]:
        st.warning("Nenhum lacre foi identificado. Não crie o pedido até verificar o texto.")
    else:
        tabela_lacres = pd.DataFrame(dados["lacres"])
        tabela_lacres.columns = ["Lacre", "Conteúdo"]
        st.dataframe(tabela_lacres, use_container_width=True, hide_index=True)


def render(lojas: list[str]) -> None:
    st.header("📦 Pedidos de Devolução")
    st.caption("A demanda nasce aqui. O recebimento físico acontece depois, usando este pedido como referência.")

    if "pedido_email_preview" not in st.session_state:
        st.session_state["pedido_email_preview"] = None
    if "pedido_criado_id" not in st.session_state:
        st.session_state["pedido_criado_id"] = None

    tab_lista, tab_email = st.tabs(["📋 Pedidos", "📨 Importar e-mail"])

    with tab_email:
        st.write(
            "Cole o conteúdo do e-mail recebido. O sistema ignora o bloco de encaminhamento "
            "e transforma apenas as informações úteis em um pedido."
        )
        assunto = st.text_input(
            "Assunto do e-mail",
            placeholder="NOTA DE SAÍDA 352 ou Devolução NF 170",
            key="pedido_assunto",
        )
        email = st.text_area("Conteúdo do e-mail", height=300, key="pedido_email")

        if st.button("⚙️ Interpretar e-mail", type="primary", key="pedido_interpretar"):
            if not email.strip():
                st.warning("Cole o conteúdo do e-mail primeiro.")
            else:
                try:
                    dados = analisar_email(email, assunto)
                    st.session_state["pedido_email_preview"] = dados
                    st.session_state["pedido_email_raw"] = email
                    st.session_state["pedido_email_assunto"] = assunto
                    st.rerun()
                except Exception as exc:
                    st.error(f"Não foi possível interpretar o e-mail: {exc}")

        dados = st.session_state.get("pedido_email_preview")
        if dados:
            if not dados["numero_nota"]:
                st.error("Não consegui identificar o número da nota no e-mail.")
            elif not dados["loja"]:
                st.error("Não consegui identificar a loja no remetente do e-mail.")
            else:
                _mostrar_previa(dados)
                if dados["lacres"]:
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button(
                            "✅ Confirmar criação do pedido",
                            type="primary",
                            key="pedido_confirmar",
                        ):
                            try:
                                pedido_id = criar_pedido(
                                    numero_nota=dados["numero_nota"],
                                    loja=dados["loja"],
                                    data_coleta=dados["data_coleta"],
                                    transportadora=dados["transportadora"],
                                    volumes=len(dados["lacres"]),
                                    lacres=dados["lacres"],
                                    observacao=dados["corpo"],
                                    assunto_email=dados["assunto"],
                                )
                                st.session_state["pedido_criado_id"] = pedido_id
                                st.session_state["pedido_email_preview"] = None
                                st.session_state["pedido_email_raw"] = ""
                                st.success(f"Pedido de devolução #{pedido_id} criado.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Não foi possível criar o pedido: {exc}")
                    with c2:
                        if st.button("🧹 Limpar prévia", key="pedido_limpar"):
                            st.session_state["pedido_email_preview"] = None
                            st.rerun()

    with tab_lista:
        filtro_status = st.selectbox("Status", STATUS, key="pedido_filtro_status")
        registros = listar_pedidos(filtro_status)

        pedido_criado_id = st.session_state.get("pedido_criado_id")
        if pedido_criado_id:
            st.success(f"Pedido de devolução #{pedido_criado_id} criado e já disponível na lista abaixo.")
            st.session_state["pedido_criado_id"] = None

        if not registros:
            st.info("Nenhum pedido encontrado.")
            return

        dados_lista = []
        for r in registros:
            criado_em = r.get("criado_em")
            dados_lista.append(
                {
                    "Emissão": criado_em.strftime("%d/%m/%Y") if criado_em else "—",
                    "Documento": r["numero_nota"],
                    "Loja": r["loja"],
                    "Volumes": int(r["volumes"] or 0),
                    "Status": _formatar_status(r["status"]),
                }
            )

        st.dataframe(
            pd.DataFrame(dados_lista),
            use_container_width=True,
            hide_index=True,
        )

        opcoes = [f"#{r['id']} — NF {r['numero_nota']} — {r['loja']}" for r in registros]
        escolha = st.selectbox(
            "🔎 Inspecionar devolução",
            opcoes,
            key="pedido_detalhe",
        )
        pedido_id = int(registros[opcoes.index(escolha)]["id"])
        pedido = buscar_pedido(pedido_id)
        if pedido:
            _mostrar_pedido(pedido)
