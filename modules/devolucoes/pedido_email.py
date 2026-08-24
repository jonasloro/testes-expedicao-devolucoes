import re
from datetime import datetime


def _primeiro_grupo(patterns: list[str], texto: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, texto, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


def limpar_email(texto: str) -> str:
    linhas = [linha.rstrip() for linha in str(texto or "").splitlines()]
    inicio = 0
    for i, linha in enumerate(linhas):
        if re.match(r"^\s*de:\s*", linha, re.IGNORECASE):
            bloco = "\n".join(linhas[i : min(i + 10, len(linhas))])
            if re.search(r"\bDate:\s*|\bSubject:\s*|\bTo:\s*|\bCc:\s*", bloco, re.IGNORECASE):
                for j in range(i, len(linhas)):
                    if not linhas[j].strip():
                        inicio = j + 1
                        break
                break
    corpo = "\n".join(linhas[inicio:]).strip()
    return re.sub(r"^-{3,}\s*$", "", corpo, flags=re.MULTILINE).strip()


def analisar_email(texto: str, assunto: str = "") -> dict:
    texto = str(texto or "")
    corpo = limpar_email(texto)
    cabecalhos = "\n".join(texto.splitlines()[:15])
    fonte_nota = assunto + "\n" + cabecalhos + "\n" + corpo

    numero_nota = _primeiro_grupo(
        [
            r"(?:NOTA\s+DE\s+SA[IÍ]DA|NOTA|NF|N[ÚU]MERO\s+DA\s+NOTA)\s*[:#-]?\s*(\d+)\b",
            r"\bSA[IÍ]DA\s+(\d+)\b",
        ],
        fonte_nota,
    )

    loja = _primeiro_grupo(
        [
            r"^\s*De:\s*Ger[eê]ncia\s+(.+?)(?:\s*<[^>]+>)?\s*$",
            r"^\s*De:\s*(.+?)(?:\s*<[^>]+>)?\s*$",
        ],
        cabecalhos,
    )
    loja = re.sub(r"\s+", " ", loja).strip()
    loja = re.sub(r"^(Gerencia|Gerência)\s+", "", loja, flags=re.IGNORECASE).strip()

    data_texto = _primeiro_grupo(
        [
            r"(?:na|em)\s+data\s+(?:de\s+)?(\d{1,2}/\d{1,2}/\d{2,4})",
            r"\b(\d{1,2}/\d{1,2}/\d{2,4})\b",
        ],
        corpo,
    )
    data_coleta = None
    if data_texto:
        for formato in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                data_coleta = datetime.strptime(data_texto, formato).date()
                break
            except ValueError:
                continue

    transportadora = _primeiro_grupo(
        [
            r"recolhido\s+pela\s+transportadora\s+([^,\n.]+)",
            r"transportadora\s*[:\-]\s*([^\n.]+)",
            r"pela\s+transportadora\s+([^,\n.]+)",
        ],
        corpo,
    ).rstrip(" ,;.")

    # Regra operacional: cada lacre representa um volume.
    # O texto "3 volumes" é apenas informativo e não é a fonte do total.
    lacres = []
    vistos = set()
    padrao_lacre = re.compile(r"^\s*(\d{5,})\s*[-–—:]\s*(.+?)\s*$", flags=re.MULTILINE)
    for match in padrao_lacre.finditer(corpo):
        codigo = match.group(1).strip()
        if codigo in vistos:
            continue
        vistos.add(codigo)
        lacres.append({"lacre": codigo, "descricao": match.group(2).strip().rstrip(";.").strip()})

    return {
        "numero_nota": numero_nota,
        "loja": loja,
        "data_coleta": data_coleta,
        "transportadora": transportadora,
        "volumes": len(lacres),
        "lacres": lacres,
        "corpo": corpo,
        "assunto": assunto or _primeiro_grupo([r"^\s*Subject:\s*(.+)$"], cabecalhos),
    }
