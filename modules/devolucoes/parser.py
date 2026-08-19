import io
import re
from typing import Any


class ParserRomaneio:
    """Leitor de romaneios PDF para o laboratório de devoluções.

    O leiaute real do romaneio coloca código, descrição, grade, quantidade e
    preço na mesma linha; depois do preço aparecem outros campos financeiros
    e/ou a referência, que não devem contaminar a descrição do produto.
    """

    HEADER_TIPO = "DEVOLUÇÃO"

    # Exemplo real do PDF extraído:
    # 010447004002 BERMUDA MASCULINA [4.G,AZUL.] 1 40,75 40,750,0033.309...
    # O trecho depois do preço é ignorado de propósito.
    _ITEM_RE = re.compile(
        r"^(?P<codigo>\d{10,14})\s+"
        r"(?P<descricao>.*?)\s+"
        r"\[(?P<grade>[^\]]*)\]\s+"
        r"(?P<quantidade>\d+)\s+"
        r"(?P<preco>[\d.,]+)\s+.*$"
    )

    def extrair_texto(self, pdf_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(pdf_bytes))
            paginas = [page.extract_text() or "" for page in reader.pages]
            texto = "\n".join(paginas)
            if not texto.strip():
                raise ValueError("O PDF não possui texto extraível.")
            return texto
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError(f"Não foi possível ler o PDF: {exc}") from exc

    def extrair_cabecalho(self, texto: str) -> dict[str, str]:
        documento = self._primeiro(r"Documento:\s*([\w-]+)", texto)
        data = self._primeiro(r"Emissão:\s*(\d{2}/\d{2}/\d{4})", texto)
        entrada = self._primeiro(r"Entrada:\s*([^\n]+)", texto)
        tipo = self._primeiro(r"(DEVOLUÇÃO[^\n]*)", texto) or self.HEADER_TIPO

        return {
            "numero_documento": documento or "",
            "data_documento": data or "",
            "tipo": tipo.strip(),
            "entrada": entrada.strip() if entrada else "",
        }

    def extrair_itens(self, texto: str) -> list[dict[str, Any]]:
        itens: list[dict[str, Any]] = []

        for linha in self._normalizar_linhas(texto):
            match = self._ITEM_RE.match(linha)
            if not match:
                continue

            itens.append(
                {
                    "codigo_barras": match.group("codigo").strip(),
                    "referencia": "",
                    "descricao": self._limpar_campo(match.group("descricao")),
                    "grade": self._limpar_campo(match.group("grade")),
                    "quantidade": int(match.group("quantidade")),
                    "preco": self._numero(match.group("preco")),
                }
            )

        return itens

    def analisar(self, pdf_bytes: bytes) -> dict[str, Any]:
        texto = self.extrair_texto(pdf_bytes)
        cabecalho = self.extrair_cabecalho(texto)
        itens = self.extrair_itens(texto)

        return {
            "cabecalho": cabecalho,
            "itens": itens,
            "total_itens": len(itens),
            "total_pecas": sum(item["quantidade"] for item in itens),
            "texto_extraido": texto,
        }

    @staticmethod
    def _normalizar_linhas(texto: str) -> list[str]:
        linhas: list[str] = []
        for linha in texto.splitlines():
            linha = re.sub(r"[\t\f\r]+", " ", linha)
            linha = re.sub(r" {2,}", " ", linha).strip()
            if linha:
                linhas.append(linha)
        return linhas

    @staticmethod
    def _limpar_campo(valor: str) -> str:
        return re.sub(r"\s+", " ", valor).strip()

    @staticmethod
    def _numero(valor: str) -> float:
        return float(valor.replace(".", "").replace(",", "."))

    @staticmethod
    def _primeiro(padrao: str, texto: str):
        encontrado = re.search(padrao, texto, flags=re.IGNORECASE)
        return encontrado.group(1).strip() if encontrado else None
