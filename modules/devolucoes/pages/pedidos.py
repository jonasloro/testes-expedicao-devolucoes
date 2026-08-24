import pandas as pd
import streamlit as st

from ..pedido_email import analisar_email
from ..pedidos_database import atualizar_status, buscar_pedido, criar_pedido, listar_pedidos


STATUS = ["Todos", "PENDENTE", "EM RECEBIMENTO", "RECEBIDO", "CONFERIDO", "CONCLUIDO", "CANCELADO"]


def _mostrar_pedido(pedido: dict) -> None:
    st.subheader(f"Pedido de devolução #{pedido['id']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Nota", pedido["numero_nota"])
    c2.metric("Loja", pedido["loja"] or "—")
    c3.metric("Volumes", int(pedido["volumes"] or 0))
    c4.metric("Lacres", len(pedido.get("lacres", [])))

    c1, c2 = st.columns(2)
    c1.write(f"**Data da coleta:** {pedido['data_coleta'].strftime('%d/%m/%Y') if pedido.get('data_coleta') else '—'}")
    c2.write(f"**Transportadora:** {pedido.get('transportadora') or '—'}")
    st.write(f"**Status:** `{pedido['status']}`")

    lacres = pedido.get("lacres", [])
    if lacres:
        st.subheader("Lacres")
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
        st.subheader("Observação")
        st.write(pedido["observacao"])

    novo_status = st.selectbox(
        "Alterar status",
        STATUS[1:],
        index=STATUS[1:].index(pedido["status"]) if pedido["status"] in STATUS[1:] else 0,
        key=f"pedido_status_{pedido['id']}",
    )
    if st.button("Salvar status", key=f"pedido_salvar_{pedido['id']}"):
        atualizar_status(int(pedido["id"]), novo_status)
        st.success("Status atualizado.")
        st.rerun()


def render(lojas: list[str]) -> None:
    st.header("📦 Pedidos de Devolução")
    st.caption("A demanda nasce aqui. O recebimento físico acontece depois, usando este pedido como referência.")

    tab_lista, tab_email = st.tabs(["📋 Pedidos", "📨 Importar e-mail"])

    with tab_email:
        st.write("Cole o conteúdo do e-mail recebido. O sistema ignora o bloco de encaminhamento e transforma apenas as informações úteis em um pedido.")
        assunto = st.text_input("Assunto do e-mail", placeholder="NOTA DE SAÍDA 352", key="pedido_assunto")
        email = st.text_area("Conteúdo do e-mail", height=300, key="pedido_email")
        if st.button("⚙️ Interpretar e criar pedido", type="primary"):
            if not email.strip():
                st.warning("Cole o conteúdo do e-mail primeiro.")
            else:
                try:
                    dados = analisar_email(email, assunto)
                    if not dados["numero_nota"]:
                        st.error("Não consegui identificar o número da nota no e-mail.")
                    elif not dados["loja"]:
                        st.error("Não consegui identificar a loja no remetente do e-mail.")
                    else:
                        st.subheader("Prévia do pedido")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Nota", dados["numero_nota"])
                        c2.metric("Loja", dados["loja"])
                        c3.metric("Volumes", dados["volumes"])
                        c4.metric("Lacres", len(dados["lacres"]))
                        st.write(f"**Data da coleta:** {dados['data_coleta'].strftime('%d/%m/%Y') if dados['data_coleta'] else '—'}")
                        st.write(f"**Transportadora:** {dados['transportadora'] or '—'}")
                        if dados["lacres"]:
                            st.dataframe(pd.DataFrame(dados["lacres"]), use_container_width=True, hide_index=True)

                        if st.button("✅ Confirmar criação do pedido", key="pedido_confirmar"):
                            pedido_id = criar_pedido(
                                numero_nota=dados["numero_nota"],
                                loja=dados["loja"],
                                data_coleta=dados["data_coleta"],
                                transportadora=dados["transportadora"],
                                volumes=dados["volumes"],
                                lacres=dados["lacres"],
                                observacao=dados["corpo"],
                                assunto_email=dados["assunto"],
                            )
                            st.success(f"Pedido de devolução #{pedido_id} criado.")
                except Exception as exc:
                    st.error(f"Não foi possível interpretar o e-mail: {exc}")

    with tab_lista:
        filtro_status = st.selectbox("Status", STATUS, key="pedido_filtro_status")
        registros = listar_pedidos(filtro_status)
        if not registros:
            st.info("Nenhum pedido encontrado.")
            return

        dados = [
            {
                "Pedido": r["id"],
                "Nota": r["numero_nota"],
                "Loja": r["loja"],
                "Data coleta": r["data_coleta"].strftime("%d/%m/%Y") if r.get("data_coleta") else "—",
                "Transportadora": r["transportadora"] or "—",
                "Volumes": r["volumes"],
                "Lacres": r["total_lacres"],
                "Status": r["status"],
            }
            for r in registros
        ]
        st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)

        opcoes = [f"#{r['id']} — Nota {r['numero_nota']} — {r['loja']}" for r in registros]
        escolha = st.selectbox("Abrir pedido", opcoes, key="pedido_detalhe")
        pedido_id = int(registros[opcoes.index(escolha)]["id"])
        pedido = buscar_pedido(pedido_id)
        if pedido:
            _mostrar_pedido(pedido)
