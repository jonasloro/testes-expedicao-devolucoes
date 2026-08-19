import re
from pathlib import Path


class ParserRomaneio:
    """Parser inicial para PDFs de devolução.

    A leitura completa do leiaute será refinada usando os romaneios reais.
    """

    HEADER_TIPO = "DEVOLUÇÃO"

    def extrair_texto(self, pdf_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader
            import io

            reader = PdfReader(io.BytesIO(pdf_bytes))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except Exception as exc:
            raise ValueError(f"Não foi possível ler o PDF: {exc}") from exc

    def extrair_cabecalho(self, texto: str) -> dict:
        documento = self._primeiro(r"Documento:\s*([\w-]+)", texto)
        data = self._primeiro(r"Emissão:\s*(\d{2}/\d{2}/\d{4})", texto)
        tipo = self._primeiro(r"(DEVOLUÇÃO[^\n]*)", texto) or self.HEADER_TIPO
        entrada = self._primeiro(r"Entrada:\s*([^\n]+)", texto)

        return {
            "numero_documento": documento or "",
            "data_documento": data or "",
            "tipo": tipo.strip(),
            "entrada": entrada.strip() if entrada else "",
        }

    @staticmethod
    def _primeiro(padrao: str, texto: str):
        encontrado = re.search(padrao, texto, flags=re.IGNORECASE)
        return encontrado.group(1).strip() if encontrado else None
