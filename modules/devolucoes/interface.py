import streamlit as st

from .parser import ParserRomaneio


def render_recebimento() -> None:
    st.header("📥 Recebimento de devolução")
    st.write("Importe o romaneio e confira os dados identificados antes de gravar.")

    arquivo = st.file_uploader("Romaneio da devolução", type=["pdf"], key="romaneio_pdf")
    if arquivo is None:
        st.caption("Nenhum arquivo carregado.")
        return

    if st.button("🔍 Ler romaneio", type="primary"):
        parser = ParserRomaneio()
        try:
            texto = parser.extrair_texto(arquivo.getvalue())
            cabecalho = parser.extrair_cabecalho(texto)
        except ValueError as exc:
            st.error(str(exc))
            return

        st.success("PDF lido com sucesso. Confira os dados antes de qualquer gravação.")
        st.subheader("Identificação encontrada")
        c1, c2, c3 = st.columns(3)
        c1.text_input("Documento", cabecalho["numero_documento"], disabled=True)
        c2.text_input("Emissão", cabecalho["data_documento"], disabled=True)
        c3.text_input("Tipo", cabecalho["tipo"], disabled=True)

        st.text_area("Entrada registrada no romaneio", cabecalho["entrada"], disabled=True)
        with st.expander("Ver texto bruto extraído"):
            st.code(texto[:20000], language="text")
