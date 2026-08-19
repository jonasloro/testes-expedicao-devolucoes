from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class DevolucaoItem:
    codigo_barras: str
    descricao: str
    referencia: str = ""
    grade: str = ""
    quantidade_romaneio: int = 0
    quantidade_recebida: Optional[int] = None
    observacao: str = ""


@dataclass
class Devolucao:
    numero_documento: str
    data_documento: str = ""
    cliente: str = ""
    tipo: str = "DEVOLUÇÃO"
    status: str = "RECEBIDA"
    criado_em: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    itens: list[DevolucaoItem] = field(default_factory=list)

    @property
    def total_romaneio(self) -> int:
        return sum(item.quantidade_romaneio for item in self.itens)

    @property
    def total_recebido(self) -> int:
        return sum((item.quantidade_recebida or 0) for item in self.itens)
