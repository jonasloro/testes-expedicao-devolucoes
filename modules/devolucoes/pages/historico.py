from datetime import date

import pandas as pd
import streamlit as st

from ..database import buscar_itens_devolucao, listar_devolucoes
from ..tratamento import listar_tratamentos


def render() -> None:
    st.header("🕘 Histórico de devoluções")
    registros = listar_devolucoes()

    if not registros:
        st.info("Nenhuma devolução foi registrada ainda.")
        return

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

    if not filtrados:
        st.warning("Nenhuma devolução corresponde aos filtros selecionados.")
        return

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
