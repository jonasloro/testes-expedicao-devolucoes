from datetime import date

from .database import get_connection


def init_pedidos_db() -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS pedidos_devolucao (
                    id BIGSERIAL PRIMARY KEY,
                    numero_nota VARCHAR(100) NOT NULL,
                    loja VARCHAR(255) NOT NULL,
                    data_coleta DATE,
                    transportadora VARCHAR(255),
                    volumes INTEGER NOT NULL DEFAULT 0,
                    status VARCHAR(40) NOT NULL DEFAULT 'PENDENTE',
                    origem_email_id VARCHAR(255),
                    assunto_email VARCHAR(500),
                    observacao TEXT,
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS pedido_devolucao_lacres (
                    id BIGSERIAL PRIMARY KEY,
                    pedido_id BIGINT NOT NULL REFERENCES pedidos_devolucao(id) ON DELETE CASCADE,
                    lacre VARCHAR(100) NOT NULL,
                    descricao VARCHAR(255),
                    criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (pedido_id, lacre)
                );

                CREATE INDEX IF NOT EXISTS idx_pedidos_devolucao_status
                    ON pedidos_devolucao(status);
                CREATE INDEX IF NOT EXISTS idx_pedidos_devolucao_nota
                    ON pedidos_devolucao(numero_nota);

                ALTER TABLE devolucoes
                    ADD COLUMN IF NOT EXISTS pedido_id BIGINT;
                CREATE INDEX IF NOT EXISTS idx_devolucoes_pedido_id
                    ON devolucoes(pedido_id);

                ALTER TABLE pedidos_devolucao
                    ADD COLUMN IF NOT EXISTS arquivo_romaneio_url TEXT;
                ALTER TABLE pedidos_devolucao
                    ADD COLUMN IF NOT EXISTS arquivo_romaneio_nome VARCHAR(255);
                """
            )
        conn.commit()


def criar_pedido(
    numero_nota: str,
    loja: str,
    data_coleta: date | None,
    transportadora: str,
    volumes: int,
    lacres: list[dict],
    observacao: str = "",
    origem_email_id: str = "",
    assunto_email: str = "",
) -> int:
    numero_nota = str(numero_nota or "").strip()
    loja = str(loja or "").strip()
    if not numero_nota:
        raise ValueError("A nota de devolução é obrigatória.")
    if not loja:
        raise ValueError("A loja é obrigatória.")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM pedidos_devolucao
                WHERE numero_nota = %s
                  AND loja = %s
                  AND status <> 'CANCELADO'
                ORDER BY id DESC
                LIMIT 1
                """,
                (numero_nota, loja),
            )
            existente = cur.fetchone()
            if existente:
                return int(existente["id"])

            cur.execute(
                """
                INSERT INTO pedidos_devolucao
                    (numero_nota, loja, data_coleta, transportadora, volumes, status,
                     origem_email_id, assunto_email, observacao)
                VALUES (%s,%s,%s,%s,%s,'PENDENTE',%s,%s,%s)
                RETURNING id
                """,
                (
                    numero_nota,
                    loja,
                    data_coleta,
                    str(transportadora or "").strip(),
                    max(int(volumes or 0), 0),
                    str(origem_email_id or "").strip(),
                    str(assunto_email or "").strip(),
                    str(observacao or "").strip(),
                ),
            )
            pedido_id = int(cur.fetchone()["id"])

            dados_lacres = []
            for lacre in lacres or []:
                codigo = str(lacre.get("lacre", "")).strip()
                if codigo:
                    dados_lacres.append((pedido_id, codigo, str(lacre.get("descricao", "")).strip()))

            if dados_lacres:
                cur.executemany(
                    """
                    INSERT INTO pedido_devolucao_lacres (pedido_id, lacre, descricao)
                    VALUES (%s,%s,%s)
                    ON CONFLICT (pedido_id, lacre) DO UPDATE SET descricao = EXCLUDED.descricao
                    """,
                    dados_lacres,
                )
        conn.commit()
    return pedido_id


def listar_pedidos(status: str | None = None):
    with get_connection() as conn:
        with conn.cursor() as cur:
            if status and status != "Todos":
                cur.execute(
                    """
                    SELECT p.*, COUNT(l.id) AS total_lacres
                    FROM pedidos_devolucao p
                    LEFT JOIN pedido_devolucao_lacres l ON l.pedido_id = p.id
                    WHERE p.status = %s
                    GROUP BY p.id
                    ORDER BY p.id DESC
                    """,
                    (status,),
                )
            else:
                cur.execute(
                    """
                    SELECT p.*, COUNT(l.id) AS total_lacres
                    FROM pedidos_devolucao p
                    LEFT JOIN pedido_devolucao_lacres l ON l.pedido_id = p.id
                    GROUP BY p.id
                    ORDER BY p.id DESC
                    """
                )
            return cur.fetchall()


def buscar_pedido(pedido_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM pedidos_devolucao WHERE id = %s", (pedido_id,))
            pedido = cur.fetchone()
            if not pedido:
                return None
            cur.execute(
                """
                SELECT lacre, descricao
                FROM pedido_devolucao_lacres
                WHERE pedido_id = %s
                ORDER BY id
                """,
                (pedido_id,),
            )
            lacres = cur.fetchall()
            return {**pedido, "lacres": lacres}


def atualizar_status(pedido_id: int, status: str) -> None:
    status = str(status).strip().upper()
    permitidos = {"PENDENTE", "EM RECEBIMENTO", "RECEBIDO", "CONFERIDO", "CONCLUIDO", "CANCELADO"}
    if status not in permitidos:
        raise ValueError("Status de pedido inválido.")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pedidos_devolucao SET status = %s, atualizado_em = NOW() WHERE id = %s",
                (status, pedido_id),
            )
        conn.commit()


def vincular_devolucao(pedido_id: int, devolucao_id: int) -> None:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE devolucoes SET pedido_id = %s WHERE id = %s",
                (pedido_id, devolucao_id),
            )
            cur.execute(
                "UPDATE pedidos_devolucao SET status = 'RECEBIDO', atualizado_em = NOW() WHERE id = %s",
                (pedido_id,),
            )
        conn.commit()
