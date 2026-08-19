import io
import re
from typing import Any


class ParserRomaneio:
    """Leitor de romaneios PDF para o laboratório de devoluções.

    O PDF real nem sempre mantém código, descrição, grade e quantidade na
    mesma linha. O parser trabalha por blocos de item, iniciados pelo código
    de barras, e procura a grade/quantidade dentro do bloco.
    """

    HEADER_TIPO = "DEVOLUÇÃO"

    _ITEM_START_RE = re.compile(r"^\d{10,14}(?:\s|$)")

    # Regra principal: exige o "]" de fechamento da grade. Isso é
    # fundamental quando a grade é numérica (ex.: "[38 40 42]", grades de
    # calça/sapato) — com o "]" opcional, o regex parava de ler a grade no
    # primeiro número seguido de espaço e confundia números da própria
    # grade com a quantidade e o preço do item, gerando falsas divergências.
    # Como o bloco inteiro do item é unido em uma única string antes da
    # busca (ver extrair_itens), o "[" e o "]" podem estar em linhas
    # diferentes do PDF original sem prejudicar o casamento.
    _ITEM_DATA_RE = re.compile(
        r"\[(?P<grade>[^\]]*)\]\s*"
        r"(?P<quantidade>\d+)\s+"
        r"(?P<preco>[\d.,]+)"
    )

    # Reserva para romaneios em que o "]" de fechamento realmente não existe
    # no texto extraído do PDF. Só é usado se a regra principal não casar.
    _ITEM_DATA_FALLBACK_RE = re.compile(
        r"\[(?P<grade>[^\]]*)"
        r"(?P<quantidade>\d+)\s+"
        r"(?P<preco>[\d.,]+)\s*$"
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
        linhas = self._normalizar_linhas(texto)
        inicios = [i for i, linha in enumerate(linhas) if self._ITEM_START_RE.match(linha)]
        itens: list[dict[str, Any]] = []

        for pos, inicio in enumerate(inicios):
            fim = inicios[pos + 1] if pos + 1 < len(inicios) else len(linhas)
            bloco = linhas[inicio:fim]
            if not bloco:
                continue

            primeira = bloco[0]
            codigo_match = re.match(r"^(\d{10,14})", primeira)
            if not codigo_match:
                continue

            codigo = codigo_match.group(1)

            # O layout real pode quebrar código de barras, referência,
            # descrição e grade em linhas diferentes. Por isso o bloco
            # inteiro do item é unido numa única string antes de procurar
            # a grade/quantidade/preço — não basta procurar linha a linha,
            # senão um "[" numa linha e o "]" na linha seguinte nunca
            # seriam encontrados juntos.
            bloco_unido = self._limpar_campo(" ".join(bloco))

            dados = self._ITEM_DATA_RE.search(bloco_unido)
            if dados is None:
                dados = self._ITEM_DATA_FALLBACK_RE.search(bloco_unido)
            if dados is None:
                continue

            trecho_descricao = " ".join(bloco).split("[", 1)[0]
            trecho_descricao = re.sub(rf"^\s*{re.escape(codigo)}\s*", "", trecho_descricao)
            descricao = self._limpar_descricao(trecho_descricao)

            itens.append(
                {
                    "codigo_barras": codigo,
                    "referencia": "",
                    "descricao": descricao,
                    "grade": self._limpar_campo(dados.group("grade")),
                    "quantidade": int(dados.group("quantidade")),
                    "preco": self._numero(dados.group("preco")),
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
    def _limpar_descricao(valor: str) -> str:
        valor = re.sub(r"\s+", " ", valor).strip()
        return valor

    @staticmethod
    def _numero(valor: str) -> float:
        return float(valor.replace(".", "").replace(",", "."))

    @staticmethod
    def _primeiro(padrao: str, texto: str):
        encontrado = re.search(padrao, texto, flags=re.IGNORECASE)
        return encontrado.group(1).strip() if encontrado else None
