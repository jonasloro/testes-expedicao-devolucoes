import re
from datetime import datetime


def _primeiro_grupo(patterns: list[str], texto: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, texto, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


def limpar_email(texto: str) -> str:
    """Retira cabeçalhos típicos de encaminhamento e preserva somente o corpo."""
    linhas = [linha.rstrip() for linha in str(texto or "").splitlines()]
    inicio = 0
    for i, linha in enumerate(linhas):
        if re.match(r"^\s*atenciosamente[,:]?\s*$", linha, re.IGNORECASE):
            break
        if re.match(r"^\s*de:\s*", linha, re.IGNORECASE):
            # Só considera o bloco de cabeçalho quando aparecem os marcadores
            # comuns de encaminhamento logo em seguida.
            bloco = "\n".join(linhas[i : min(i + 6, len(linhas))])
            if re.search(r"Date:\s*|Subject:\s*|To:\s*|Cc:\s*", bloco, re.IGNORECASE):
                for j in range(i, len(linhas)):
                    if linhas[j].strip() == "":
                        inicio = j + 1
                        break
                break
    corpo = "\n".join(linhas[inicio:]).strip()
    corpo = re.sub(r"^-{3,}\s*$", "", corpo, flags=re.MULTILINE).strip()
    return corpo


def analisar_email(texto: str, assunto: str = "") -> dict:
    texto = str(texto or "")
    corpo = limpar_email(texto)
    cabecalhos = "\n".join(texto.splitlines()[:12])

    numero_nota = _primeiro_grupo(
        [
            r"(?:NOTA\s+DE\s+SA[IÍ]DA|NOTA|NF|N[ÚU]MERO\s+DA\s+NOTA)\s*[:#-]?\s*(\d+)",
            r"\b(?:SA[IÍ]DA)\s+(\d+)\b",
        ],
        assunto + "\n" + cabecalhos + "\n" + corpo,
    )

    loja = _primeiro_grupo(
        [
            r"^\s*De:\s*Gerencia\s+(.+?)(?:\s*<.*?>)?\s*$",
            r"^\s*De:\s*(.+?)(?:\s*<.*?>)?\s*$",
        ],
        cabecalhos,
    )
    loja = re.sub(r"\s+", " ", loja).strip()
    loja = re.sub(r"^(Gerencia|Gerência)\s+", "", loja, flags=re.IGNORECASE)

    data_texto = _primeiro_grupo(
        [r"na\s+data\s+(?:de\s+)?(\d{1,2}/\d{1,2}/\d{2,4})"],
        corpo,
    )
    data_coleta = None
    if data_texto:
        for formato in ("%d/%m/%Y", "%d/%m/%y"):
            try:
                data_coleta = datetime.strptime(data_texto, formato).date()
                break
            except ValueError:
                pass

    transportadora = _primeiro_grupo(
        [r"recolhido\s+pela\s+transportadora\s+([^,\n.]+)", r"transportadora\s*[:\-]\s*([^\n.]+)"],
        corpo,
    )

    volumes_texto = _primeiro_grupo([r"com\s+(\d+)\s+volumes?\b", r"(\d+)\s+volumes?\b"], corpo)
    volumes = int(volumes_texto) if volumes_texto else 0

    lacres = []
    for match in re.finditer(r"^\s*(\d{5,})\s*[-–—:]\s*(.+?)\s*$", corpo, flags=re.MULTILINE):
        lacres.append({"lacre": match.group(1), "descricao": match.group(2).strip()})

    return {
        "numero_nota": numero_nota,
        "loja": loja,
        "data_coleta": data_coleta,
        "transportadora": transportadora,
        "volumes": volumes,
        "lacres": lacres,
        "corpo": corpo,
        "assunto": assunto or _primeiro_grupo([r"^\s*Subject:\s*(.+)$"], cabecalhos),
    }
