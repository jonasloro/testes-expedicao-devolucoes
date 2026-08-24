import pandas as pd
import streamlit as st

from ..database import buscar_itens_devolucao
from ..tratamento import (
    DESTINOS,
    listar_devolucoes_para_tratamento,
    listar_tratamentos,
    quantidades_tratadas,
    salvar_tratamentos_em_lote,
)

# AVARIA não é mais uma escolha manual: tudo que vem no romaneio oficial de
# Anápolis já é registrado automaticamente como avaria pelo banco.
DESTINOS_MANUAIS = [destino for destino in DESTINOS if destino != "AVARIA"]


def render() -> None:
    st.header("📋 Tratamento da devolução")
    st.caption(
        "Tratativa em lote. Peças vindas do romaneio de Anápolis são AVARIA automaticamente; "
        "aqui você decide apenas o destino das peças recebidas no CD."
    )

    registros = listar_devolucoes_para_tratamento()
    if not registros:
        st.success("Não há devoluções aguardando tratamento.")
        return

    opcoes = [f"#{r['id']} — {r['loja'] or 'Loja não informada'} — doc. {r['numero_documento']}" for r in registros]
    escolha = st.selectbox("Devolução", opcoes, key="tratamento_devolucao")
    registro = registros[opcoes.index(escolha)]
    devolucao_id = int(registro["id"])

    itens = buscar_itens_devolucao(devolucao_id)
    tratadas = quantidades_tratadas(devolucao_id)

    total_entrada = int(registro["total_pecas_entrada"] or 0)
    total_anapolis = int(registro.get("total_pecas_anapolis") or 0)
    total_encontrado = total_entrada + total_anapolis
    total_tratada = int(registro["pecas_tratadas"] or 0)
    restante_total = max(total_encontrado - total_tratada, 0)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Documento", registro["numero_documento"])
    c2.metric("Loja", registro["loja"] or "—")
    c3.metric("Entrada CD", total_entrada)
    c4.metric("Avarias automáticas", total_anapolis)
    c5.metric("Restantes para decisão", restante_total)

    pendentes = []
    for item in itens:
        disponivel_item = int(item["quantidade_entrada"] or 0) + int(item["quantidade_anapolis"] or 0)
        restante = disponivel_item - int(tratadas.get(int(item["id"]), 0))
        if restante > 0:
            pendentes.append((item, restante))

    if pendentes:
        opcoes_item = [
            f"{item['codigo_barras']} — {item['descricao']} — {item['grade']} — restante: {restante}"
            for item, restante in pendentes
        ]
        selecionados = st.multiselect(
            "Itens que receberão a mesma tratativa",
            opcoes_item,
            key="trat_itens_lote",
        )
        destino = st.selectbox("Destino do lote", DESTINOS_MANUAIS, key="trat_destino_lote")
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
                quantidade_parcial = st.number_input(
                    "Quantidade total do lote",
                    min_value=1,
                    max_value=total_selecionado,
                    value=min(total_selecionado, 1),
                    step=1,
                    key="trat_qtd_lote",
                )

            if st.button("✅ Aplicar tratativa ao lote", type="primary"):
                try:
                    lancamentos = []
                    restante_para_distribuir = (
                        int(quantidade_parcial or total_selecionado)
                        if not tratar_total
                        else None
                    )
                    for item, restante in escolhidos:
                        qtd = restante if tratar_total else min(restante, restante_para_distribuir or 0)
                        if qtd > 0:
                            lancamentos.append(
                                {
                                    "devolucao_item_id": int(item["id"]),
                                    "quantidade": qtd,
                                    "destino": destino,
                                    "observacao": observacao,
                                }
                            )
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
