import io
import re
from typing import Any


class ParserRomaneio:
    """Leitor robusto de romaneios PDF para o laboratório de devoluções."""

    HEADER_TIPO = "DEVOLUÇÃO"

    # O texto extraído de PDFs pode inserir quebras de linha no meio de um item.
    # Por isso a leitura dos produtos é feita sobre o texto inteiro.
    _ITEM_RE = re.compile(
        r"(?m)^(?P<codigo>\d{10,14})\s+"
        r"(?P<corpo>.+?)\s*"
        r"\[(?P<grade>[^\]]*)\]\s*"
        r"(?P<quantidade>\d+)\s+"
        r"(?P<preco>[\d.,]+)\s+"
        r"(?P<desconto>[\d.,]+)\s+"
        r"(?P<total>[\d.,]+)"
        r"(?:\s|$)",
        flags=re.MULTILINE | re.DOTALL,
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
        texto = self._normalizar_texto(texto)

        for match in self._ITEM_RE.finditer(texto):
            codigo = match.group("codigo").strip()
            corpo = self._limpar_campo(match.group("corpo"))
            grade = self._limpar_campo(match.group("grade"))
            quantidade = int(match.group("quantidade"))
            preco = self._numero(match.group("preco"))

            referencia, descricao = self._separar_referencia_descricao(corpo)

            itens.append(
                {
                    "codigo_barras": codigo,
                    "referencia": referencia,
                    "descricao": descricao,
                    "grade": grade,
                    "quantidade": quantidade,
                    "preco": preco,
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
    def _normalizar_texto(texto: str) -> str:
        linhas = []
        for linha in texto.splitlines():
            linha = re.sub(r"[ \t\f\r]+", " ", linha).strip()
            linhas.append(linha)
        return "\n".join(linhas)

    @staticmethod
    def _limpar_campo(valor: str) -> str:
        return re.sub(r"\s+", " ", valor).strip()

    @staticmethod
    def _separar_referencia_descricao(corpo: str) -> tuple[str, str]:
        match = re.match(r"(?P<ref>[\d.\-]+)(?P<desc>[A-Za-zÀ-ÿ].*)$", corpo)
        if match:
            return match.group("ref"), match.group("desc").strip()
        return "", corpo.strip()

    @staticmethod
    def _numero(valor: str) -> float:
        return float(valor.replace(".", "").replace(",", "."))

    @staticmethod
    def _primeiro(padrao: str, texto: str):
        encontrado = re.search(padrao, texto, flags=re.IGNORECASE)
        return encontrado.group(1).strip() if encontrado else None
