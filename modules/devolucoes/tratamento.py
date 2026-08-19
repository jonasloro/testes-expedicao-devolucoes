import psycopg
from psycopg.rows import dict_row

from .database import get_database_url

DESTINOS = [
    "ESTOCAR",
    "ARMAZENAR PORTA-PALETE",
    "ARMAZENAR - RUA 1",
    "AVARIA",
]


def _conn():
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def init_tratamento_db() -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS devolucao_tratamentos (
                    id BIGSERIAL PRIMARY KEY,
                    devolucao_id BIGINT NOT NULL REFERENCES devolucoes(id) ON DELETE CASCADE,
                    devolucao_item_id BIGINT NOT NULL REFERENCES devolucao_itens(id) ON DELETE CASCADE,
                    quantidade INTEGER NOT NULL CHECK (quantidade > 0),
                    destino VARCHAR(40) NOT NULL,
                    observacao TEXT,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
        conn.commit()


def preparar_devolucao(devolucao_id: int) -> None:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE devolucoes SET status = 'AGUARDANDO TRATAMENTO' WHERE id = %s AND status IN ('CONFERIDA', 'DIVERGENTE')",
                (devolucao_id,),
            )
        conn.commit()


def listar_devolucoes_para_tratamento():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT d.*, COALESCE(SUM(t.quantidade), 0) AS pecas_tratadas
                FROM devolucoes d
                LEFT JOIN devolucao_tratamentos t ON t.devolucao_id = d.id
                WHERE d.status IN ('AGUARDANDO TRATAMENTO', 'DIVERGENTE', 'CONFERIDA')
                GROUP BY d.id
                ORDER BY d.id DESC
                """
            )
            return cur.fetchall()


def quantidades_tratadas(devolucao_id: int) -> dict[int, int]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT devolucao_item_id, COALESCE(SUM(quantidade), 0) AS quantidade FROM devolucao_tratamentos WHERE devolucao_id = %s GROUP BY devolucao_item_id",
                (devolucao_id,),
            )
            return {int(r["devolucao_item_id"]): int(r["quantidade"]) for r in cur.fetchall()}


def listar_tratamentos(devolucao_id: int):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.*, i.codigo_barras, i.referencia, i.descricao, i.grade
                FROM devolucao_tratamentos t
                JOIN devolucao_itens i ON i.id = t.devolucao_item_id
                WHERE t.devolucao_id = %s
                ORDER BY t.id DESC
                """,
                (devolucao_id,),
            )
            return cur.fetchall()


def salvar_tratamentos_em_lote(devolucao_id: int, lancamentos: list[dict]) -> None:
    """Grava um lote de tratativas com poucas consultas ao PostgreSQL.

    Antes esta rotina fazia duas consultas para cada item selecionado. Em lotes
    grandes isso gerava centenas de round-trips ao Neon e fazia a tela parecer
    travada. Agora os itens e os tratamentos existentes são carregados em uma
    única rodada, validados em memória e inseridos em massa.
    """
    if not lancamentos:
        raise ValueError("Nenhuma tratativa foi informada.")

    normalizados = []
    for lanc in lancamentos:
        item_id = int(lanc["devolucao_item_id"])
        quantidade = int(lanc["quantidade"])
        destino = str(lanc["destino"]).strip()
        observacao = str(lanc.get("observacao", "")).strip()

        if quantidade <= 0:
            continue
        if destino not in DESTINOS:
            raise ValueError(f"Destino inválido: {destino}")

        normalizados.append(
            {
                "item_id": item_id,
                "quantidade": quantidade,
                "destino": destino,
                "observacao": observacao,
            }
        )

    if not normalizados:
        raise ValueError("Nenhuma quantidade válida foi informada.")

    item_ids = [lanc["item_id"] for lanc in normalizados]

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT total_pecas_entrada FROM devolucoes WHERE id = %s",
                (devolucao_id,),
            )
            devolucao = cur.fetchone()
            if not devolucao:
                raise ValueError("Devolução não encontrada.")

            cur.execute(
                """
                SELECT id, quantidade_entrada
                FROM devolucao_itens
                WHERE devolucao_id = %s
                  AND id = ANY(%s)
                """,
                (devolucao_id, item_ids),
            )
            itens_db = {
                int(row["id"]): int(row["quantidade_entrada"] or 0)
                for row in cur.fetchall()
            }

            faltantes = [item_id for item_id in item_ids if item_id not in itens_db]
            if faltantes:
                raise ValueError(
                    "Itens da devolução não encontrados: "
                    + ", ".join(map(str, faltantes[:10]))
                )

            cur.execute(
                """
                SELECT devolucao_item_id, COALESCE(SUM(quantidade), 0) AS tratada
                FROM devolucao_tratamentos
                WHERE devolucao_id = %s
                  AND devolucao_item_id = ANY(%s)
                GROUP BY devolucao_item_id
                """,
                (devolucao_id, item_ids),
            )
            ja_tratadas = {
                int(row["devolucao_item_id"]): int(row["tratada"] or 0)
                for row in cur.fetchall()
            }

            for lanc in normalizados:
                item_id = lanc["item_id"]
                restante = itens_db[item_id] - ja_tratadas.get(item_id, 0)
                if lanc["quantidade"] > restante:
                    raise ValueError(
                        f"A quantidade do item {item_id} excede o restante ({restante})."
                    )

            cur.executemany(
                """
                INSERT INTO devolucao_tratamentos
                    (devolucao_id, devolucao_item_id, quantidade, destino, observacao)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [
                    (
                        devolucao_id,
                        lanc["item_id"],
                        lanc["quantidade"],
                        lanc["destino"],
                        lanc["observacao"],
                    )
                    for lanc in normalizados
                ],
            )

            cur.execute(
                """
                SELECT COALESCE(SUM(quantidade), 0) AS tratada
                FROM devolucao_tratamentos
                WHERE devolucao_id = %s
                """,
                (devolucao_id,),
            )
            total_tratada = int(cur.fetchone()["tratada"] or 0)
            total_entrada = int(devolucao["total_pecas_entrada"] or 0)
            novo_status = (
                "CONCLUÍDA"
                if total_tratada >= total_entrada
                else "AGUARDANDO TRATAMENTO"
            )

            cur.execute(
                "UPDATE devolucoes SET status = %s WHERE id = %s",
                (novo_status, devolucao_id),
            )

        conn.commit()
