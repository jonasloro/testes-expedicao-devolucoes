import io
import re
from typing import Any


class ParserRomaneio:
    """Leitor de romaneios PDF para o laboratório de devoluções."""

    HEADER_TIPO = "DEVOLUÇÃO"
    _ITEM_RE = re.compile(
        r"(?P<codigo>\d{10,14})\s+"
        r"(?P<corpo>.+?)\s+"
        r"\[(?P<grade>[^\]]*)\]\s+"
        r"(?P<quantidade>\d+)\s+"
        r"(?P<preco>[\d.,]+)\s+"
        r"(?:[\d.,]+)\s+"
        r"(?:[\d.,]+)$"
    )

    def extrair_texto(self, pdf_bytes: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(pdf_bytes))
            texto = "\n".join(page.extract_text() or "" for page in reader.pages)
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
        linhas = [self._normalizar_linha(linha) for linha in texto.splitlines()]
        for linha in linhas:
            if not linha or not linha[0].isdigit():
                continue
            match = self._ITEM_RE.match(linha)
            if not match:
                continue
            corpo = match.group("corpo").strip()
            referencia, descricao = self._separar_referencia_descricao(corpo)
            itens.append(
                {
                    "codigo_barras": match.group("codigo"),
                    "referencia": referencia,
                    "descricao": descricao,
                    "grade": match.group("grade").strip(),
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
        }

    @staticmethod
    def _normalizar_linha(linha: str) -> str:
        return re.sub(r"\s+", " ", linha).strip()

    @staticmethod
    def _separar_referencia_descricao(corpo: str) -> tuple[str, str]:
        match = re.match(r"(?P<ref>[\d.\-]+)(?P<desc>[A-Za-zÀ-ÿ].*)$", corpo)
        if match:
            return match.group("ref"), match.group("desc").strip()
        return "", corpo

    @staticmethod
    def _numero(valor: str) -> float:
        return float(valor.replace(".", "").replace(",", "."))

    @staticmethod
    def _primeiro(padrao: str, texto: str):
        encontrado = re.search(padrao, texto, flags=re.IGNORECASE)
        return encontrado.group(1).strip() if encontrado else None
