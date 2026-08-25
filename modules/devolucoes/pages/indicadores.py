from collections import Counter, defaultdict

import pandas as pd
import streamlit as st

from ..database import listar_devolucoes
from ..tratamento import indicadores_avarias_por_loja, listar_avarias

MESES_PT = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
    7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}


def render() -> None:
    st.header("📊 Indicadores")

    registros = listar_devolucoes()
    if not registros:
        st.info("Registre pelo menos uma devolução (Conferência) para começar a ver indicadores aqui.")
        return

    df = pd.DataFrame(registros)
    avarias = listar_avarias() or []
    total_pecas_avaria = sum(r["quantidade"] for r in avarias)

    # -------------------------------------------------------------- KPIs
    total_devolucoes = len(df)
    total_recebido = int((df["total_pecas_entrada"].fillna(0) + df["total_pecas_anapolis"].fillna(0)).sum())
    total_loja = int(df["total_pecas_loja"].fillna(0).sum())
    taxa_avaria = (total_pecas_avaria / total_recebido * 100) if total_recebido else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devoluções registradas", total_devolucoes)
    c2.metric("Peças recebidas no CD", total_recebido)
    c3.metric("Peças em avaria", total_pecas_avaria)
    c4.metric("Taxa de avaria", f"{taxa_avaria:.1f}%")

    st.caption(
        f"Peças informadas pela loja: {total_loja} · "
        f"Diferença acumulada (recebido − loja): {total_recebido - total_loja:+d}"
    )

    st.markdown("---")

    # ------------------------------------------------------- Status geral
    col_status, col_origem = st.columns(2)

    with col_status:
        st.subheader("Status das devoluções")
        contagem_status = df["status"].fillna("—").value_counts()
        st.bar_chart(contagem_status)

    with col_origem:
        st.subheader("Origem das peças recebidas")
        total_entrada_cd = int(df["total_pecas_entrada"].fillna(0).sum())
        total_anapolis = int(df["total_pecas_anapolis"].fillna(0).sum())
        df_origem = pd.DataFrame(
            {"Peças": [total_entrada_cd, total_anapolis]},
            index=["Entrada CD", "Anápolis (avaria automática)"],
        )
        st.bar_chart(df_origem)
        if total_recebido:
            pct_anapolis = total_anapolis / total_recebido * 100
            st.caption(f"{pct_anapolis:.0f}% do recebido já chega classificado como avaria (via Anápolis).")

    st.markdown("---")

    # ------------------------------------------------------ Evolução mensal
    st.subheader("Evolução mensal")
    df_data = df.dropna(subset=["data_documento"]).copy()
    if df_data.empty:
        st.caption("Nenhuma devolução com data de documento preenchida ainda.")
    else:
        df_data["data_documento"] = pd.to_datetime(df_data["data_documento"])
        df_data["mes"] = df_data["data_documento"].dt.to_period("M")
        evolucao = df_data.groupby("mes").agg(
            devolucoes=("id", "count"),
            pecas_recebidas=("total_pecas_entrada", lambda s: int(s.fillna(0).sum())),
        )
        evolucao.index = evolucao.index.astype(str)
        col_m1, col_m2 = st.columns(2)
        with col_m1:
            st.caption("Devoluções por mês")
            st.bar_chart(evolucao["devolucoes"])
        with col_m2:
            st.caption("Peças recebidas por mês")
            st.line_chart(evolucao["pecas_recebidas"])

    st.markdown("---")

    # --------------------------------------------------------- Por loja
    st.subheader("Por loja")
    df_loja = df.copy()
    df_loja["loja"] = df_loja["loja"].fillna("Não informada")
    volume_lojas = df_loja.groupby("loja").agg(
        pecas_recebidas=("total_pecas_entrada", lambda s: int(s.fillna(0).sum())),
        devolucoes=("id", "count"),
    ).sort_values("pecas_recebidas", ascending=False)

    col_vol, col_taxa = st.columns(2)

    with col_vol:
        st.caption("Top 10 lojas por volume recebido (peças)")
        top_volume = volume_lojas.head(10)
        if top_volume.empty:
            st.caption("Sem dados suficientes ainda.")
        else:
            st.bar_chart(top_volume["pecas_recebidas"])

    with col_taxa:
        st.caption("Top 10 lojas por taxa de avaria (%)")
        avarias_por_loja = {r["loja"] or "Não informada": r["total_avaria"] for r in (indicadores_avarias_por_loja() or [])}
        if not avarias_por_loja:
            st.caption("Sem avarias registradas ainda.")
        else:
            taxa_por_loja = {}
            for loja, avaria in avarias_por_loja.items():
                recebido_loja = int(volume_lojas.loc[loja, "pecas_recebidas"]) if loja in volume_lojas.index else 0
                if recebido_loja > 0:
                    taxa_por_loja[loja] = round(avaria / recebido_loja * 100, 1)
            if not taxa_por_loja:
                st.caption("Sem base de comparação suficiente (peças recebidas) ainda.")
            else:
                serie_taxa = pd.Series(taxa_por_loja).sort_values(ascending=False).head(10)
                st.bar_chart(serie_taxa)

    st.markdown("---")

    # ----------------------------------------------------------- Tabela
    with st.expander("📋 Ver tabela completa por loja"):
        tabela_lojas = volume_lojas.copy()
        tabela_lojas["avaria"] = [avarias_por_loja.get(loja, 0) for loja in tabela_lojas.index]
        tabela_lojas["taxa_avaria (%)"] = tabela_lojas.apply(
            lambda r: round(r["avaria"] / r["pecas_recebidas"] * 100, 1) if r["pecas_recebidas"] else 0,
            axis=1,
        )
        tabela_lojas.columns = ["Peças recebidas", "Devoluções", "Peças em avaria", "Taxa de avaria (%)"]
        st.dataframe(tabela_lojas.sort_values("Peças recebidas", ascending=False), use_container_width=True)
