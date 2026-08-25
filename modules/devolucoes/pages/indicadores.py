import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from ..database import listar_devolucoes
from ..tratamento import indicadores_avarias_por_loja, listar_avarias

CORES_STATUS = {
    "AGUARDANDO TRATAMENTO": "#f2c744",
    "DIVERGENTE": "#e05c5c",
    "CONCLUÍDA": "#4caf7d",
}
COR_PRIMARIA = "#4a90d9"
COR_SECUNDARIA = "#e0a030"


def _layout_padrao(fig, titulo, altura=360):
    fig.update_layout(
        title=dict(text=titulo, font=dict(size=16)),
        template="plotly_white",
        height=altura,
        margin=dict(t=50, b=30, l=10, r=10),
        showlegend=False,
    )
    return fig


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
    taxa_avaria_geral = (total_pecas_avaria / total_recebido * 100) if total_recebido else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Devoluções registradas", total_devolucoes)
    c2.metric("Peças recebidas no CD", total_recebido)
    c3.metric("Peças em avaria", total_pecas_avaria)
    c4.metric("Taxa de avaria geral", f"{taxa_avaria_geral:.1f}%")

    st.caption(
        f"Peças informadas pela loja: {total_loja} · "
        f"Diferença acumulada (recebido − loja): {total_recebido - total_loja:+d}"
    )

    st.markdown("---")

    # ------------------------------------------------------- Status geral
    col_status, col_origem = st.columns(2)

    with col_status:
        contagem_status = df["status"].fillna("—").value_counts()
        fig_status = px.bar(
            x=contagem_status.index,
            y=contagem_status.values,
            text=contagem_status.values,
            color=contagem_status.index,
            color_discrete_map=CORES_STATUS,
            labels={"x": "", "y": "Devoluções"},
        )
        fig_status.update_traces(textposition="outside")
        _layout_padrao(fig_status, "Status das devoluções")
        st.plotly_chart(fig_status, use_container_width=True)

    with col_origem:
        total_entrada_cd = int(df["total_pecas_entrada"].fillna(0).sum())
        total_anapolis = int(df["total_pecas_anapolis"].fillna(0).sum())
        fig_origem = go.Figure(
            data=[
                go.Pie(
                    labels=["Entrada CD", "Anápolis (avaria automática)"],
                    values=[total_entrada_cd, total_anapolis],
                    hole=0.55,
                    marker=dict(colors=[COR_PRIMARIA, "#e05c5c"]),
                    textinfo="percent",
                    textfont=dict(size=14),
                )
            ]
        )
        _layout_padrao(fig_origem, "Origem das peças recebidas")
        fig_origem.update_layout(showlegend=True, legend=dict(orientation="h", yanchor="bottom", y=-0.15))
        st.plotly_chart(fig_origem, use_container_width=True)

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

        fig_evol = go.Figure()
        fig_evol.add_trace(
            go.Bar(
                x=evolucao.index, y=evolucao["devolucoes"], name="Devoluções",
                marker_color=COR_PRIMARIA, yaxis="y1",
                text=evolucao["devolucoes"], textposition="outside",
            )
        )
        fig_evol.add_trace(
            go.Scatter(
                x=evolucao.index, y=evolucao["pecas_recebidas"], name="Peças recebidas",
                mode="lines+markers", line=dict(color=COR_SECUNDARIA, width=3),
                marker=dict(size=8), yaxis="y2",
            )
        )
        fig_evol.update_layout(
            template="plotly_white",
            height=380,
            margin=dict(t=30, b=30, l=10, r=10),
            yaxis=dict(title="Devoluções"),
            yaxis2=dict(title="Peças recebidas", overlaying="y", side="right", showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig_evol, use_container_width=True)

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
        top_volume = volume_lojas.head(10)
        if top_volume.empty:
            st.caption("Sem dados suficientes ainda.")
        else:
            fig_vol = px.bar(
                top_volume,
                x="pecas_recebidas",
                y=top_volume.index,
                orientation="h",
                text="pecas_recebidas",
                labels={"pecas_recebidas": "Peças recebidas", "y": ""},
                color_discrete_sequence=[COR_PRIMARIA],
            )
            fig_vol.update_traces(textposition="outside")
            fig_vol.update_layout(yaxis=dict(categoryorder="total ascending"))
            _layout_padrao(fig_vol, "Top 10 lojas por volume recebido", altura=380)
            st.plotly_chart(fig_vol, use_container_width=True)

    avarias_por_loja = {r["loja"] or "Não informada": r["total_avaria"] for r in (indicadores_avarias_por_loja() or [])}

    with col_taxa:
        taxa_por_loja = {}
        for loja, avaria in avarias_por_loja.items():
            recebido_loja = int(volume_lojas.loc[loja, "pecas_recebidas"]) if loja in volume_lojas.index else 0
            if recebido_loja > 0:
                taxa_por_loja[loja] = round(avaria / recebido_loja * 100, 1)

        if not taxa_por_loja:
            st.caption("Sem base de comparação suficiente (avaria x recebido) ainda.")
        else:
            serie_taxa = pd.Series(taxa_por_loja).sort_values(ascending=False).head(10)
            fig_taxa = px.bar(
                x=serie_taxa.values,
                y=serie_taxa.index,
                orientation="h",
                text=[f"{v:.1f}%" for v in serie_taxa.values],
                labels={"x": "Taxa de avaria (%)", "y": ""},
                color=serie_taxa.values,
                color_continuous_scale=["#4caf7d", "#f2c744", "#e05c5c"],
            )
            fig_taxa.add_vline(
                x=taxa_avaria_geral,
                line_dash="dash",
                line_color="#e05c5c",
                annotation_text=f"Média geral: {taxa_avaria_geral:.1f}%",
                annotation_position="top",
            )
            fig_taxa.update_traces(textposition="outside")
            fig_taxa.update_layout(yaxis=dict(categoryorder="total ascending"), coloraxis_showscale=False)
            _layout_padrao(fig_taxa, "Top 10 lojas por taxa de avaria", altura=380)
            st.plotly_chart(fig_taxa, use_container_width=True)

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
