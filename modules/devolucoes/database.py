import os
from datetime import datetime

import psycopg
from psycopg.rows import dict_row



def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        try:
            import streamlit as st

            url = str(st.secrets.get("DATABASE_URL", "")).strip()
        except Exception:
            url = ""

    if not url:
        raise RuntimeError(
            "DATABASE_URL não configurada. Adicione a connection string do Neon "
            "nos Secrets do Streamlit."
        )

    return url



def get_connection():
    return psycopg.connect(get_database_url(), row_factory=dict_row)



def init_db() -> None:
    """Confere e prepara o schema essencial do Neon."""
    sql = """
    CREATE TABLE IF NOT EXISTS devolucoes (
        id BIGSERIAL PRIMARY KEY,
        numero_documento VARCHAR(100) NOT NULL,
        data_documento DATE,
        cliente VARCHAR(255),
        loja VARCHAR(255),
        tipo VARCHAR(100) NOT NULL DEFAULT 'DEVOLUÇÃO',
        status VARCHAR(50) NOT NULL DEFAULT 'RECEBIDA',
        arquivo_loja VARCHAR(500),
        arquivo_entrada VARCHAR(500),
        total_pecas_loja INTEGER NOT NULL DEFAULT 0,
        total_pecas_entrada INTEGER NOT NULL DEFAULT 0,
        diferenca_total INTEGER NOT NULL DEFAULT 0,
        itens_distintos INTEGER NOT NULL DEFAULT 0,
        resultado_conferencia VARCHAR(50),
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        registrado_em TIMESTAMPTZ
    );

    CREATE TABLE IF NOT EXISTS devolucao_itens (
        id BIGSERIAL PRIMARY KEY,
        devolucao_id BIGINT NOT NULL REFERENCES devolucoes(id) ON DELETE CASCADE,
        codigo_barras VARCHAR(50) NOT NULL,
        referencia VARCHAR(255),
        descricao TEXT,
        grade VARCHAR(255),
        quantidade_loja INTEGER NOT NULL DEFAULT 0,
        quantidade_entrada INTEGER NOT NULL DEFAULT 0,
        diferenca INTEGER NOT NULL DEFAULT 0,
        status VARCHAR(30) NOT NULL DEFAULT 'OK',
        observacao TEXT,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS devolucao_conferencias (
        id BIGSERIAL PRIMARY KEY,
        devolucao_id BIGINT NOT NULL REFERENCES devolucoes(id) ON DELETE CASCADE,
        usuario VARCHAR(255),
        status VARCHAR(50) NOT NULL,
        total_itens INTEGER NOT NULL DEFAULT 0,
        itens_ok INTEGER NOT NULL DEFAULT 0,
        itens_faltou INTEGER NOT NULL DEFAULT 0,
        itens_excesso INTEGER NOT NULL DEFAULT 0,
        total_pecas_loja INTEGER NOT NULL DEFAULT 0,
        total_pecas_entrada INTEGER NOT NULL DEFAULT 0,
        diferenca_total INTEGER NOT NULL DEFAULT 0,
        observacao TEXT,
        conferido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute(
                """
                ALTER TABLE devolucoes
                ADD COLUMN IF NOT EXISTS loja VARCHAR(255)
                """
            )
        conn.commit()



def criar_devolucao(devolucao, loja: str = ""):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO devolucoes
                    (numero_documento, data_documento, cliente, loja, tipo, status, criado_em)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    devolucao.numero_documento,
                    devolucao.data_documento or None,
                    devolucao.cliente,
                    loja,
                    devolucao.tipo,
                    devolucao.status,
                    devolucao.criado_em,
                ),
            )
            devolucao_id = int(cur.fetchone()["id"])

            if devolucao.itens:
                cur.executemany(
                    """
                    INSERT INTO devolucao_itens
                        (devolucao_id, codigo_barras, descricao, referencia, grade,
                         quantidade_loja, quantidade_entrada, diferenca, status, observacao)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            devolucao_id,
                            item.codigo_barras,
                            item.descricao,
                            item.referencia,
                            item.grade,
                            item.quantidade_romaneio,
                            item.quantidade_recebida or 0,
                            (item.quantidade_recebida or 0) - item.quantidade_romaneio,
                            "OK",
                            item.observacao,
                        )
                        for item in devolucao.itens
                    ],
                )

        conn.commit()

    return devolucao_id



def registrar_conferencia(
    numero_documento: str,
    data_documento: str,
    arquivo_loja: str,
    arquivo_entrada: str,
    resultado: list[dict],
    total_pecas_loja: int,
    total_pecas_entrada: int,
    cliente: str = "",
    loja: str = "",
) -> int:
    diferenca_total = total_pecas_entrada - total_pecas_loja
    itens_distintos = len(resultado)
    tem_divergencia = any(item.get("status") != "OK" for item in resultado)
    status = "DIVERGENTE" if tem_divergencia else "CONFERIDA"
    agora = datetime.now().astimezone()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM devolucoes
                WHERE numero_documento = %s
                  AND COALESCE(arquivo_loja, '') = %s
                  AND COALESCE(arquivo_entrada, '') = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (numero_documento, arquivo_loja, arquivo_entrada),
            )
            existente = cur.fetchone()
            if existente:
                return int(existente["id"])

            cur.execute(
                """
                INSERT INTO devolucoes (
                    numero_documento, data_documento, cliente, loja, tipo, status, criado_em,
                    arquivo_loja, arquivo_entrada, total_pecas_loja, total_pecas_entrada,
                    diferenca_total, itens_distintos, resultado_conferencia, registrado_em
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    numero_documento,
                    data_documento or None,
                    cliente,
                    loja,
                    "DEVOLUÇÃO",
                    status,
                    agora,
                    arquivo_loja,
                    arquivo_entrada,
                    total_pecas_loja,
                    total_pecas_entrada,
                    diferenca_total,
                    itens_distintos,
                    "DIVERGENTE" if tem_divergencia else "OK",
                    agora,
                ),
            )
            devolucao_id = int(cur.fetchone()["id"])

            if resultado:
                cur.executemany(
                    """
                    INSERT INTO devolucao_itens (
                        devolucao_id, codigo_barras, referencia, descricao, grade,
                        quantidade_loja, quantidade_entrada, diferenca, status, observacao
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            devolucao_id,
                            item.get("codigo_barras", ""),
                            item.get("referencia", ""),
                            item.get("descricao", ""),
                            item.get("grade", ""),
                            int(item.get("qtd_loja", 0)),
                            int(item.get("qtd_entrada", 0)),
                            int(item.get("diferenca", 0)),
                            item.get("status", ""),
                            item.get("observacao", ""),
                        )
                        for item in resultado
                    ],
                )

            itens_ok = sum(item.get("status") == "OK" for item in resultado)
            itens_faltou = sum(item.get("status") == "FALTOU" for item in resultado)
            itens_excesso = sum(item.get("status") == "EXCESSO" for item in resultado)

            cur.execute(
                """
                INSERT INTO devolucao_conferencias (
                    devolucao_id, usuario, status, total_itens, itens_ok,
                    itens_faltou, itens_excesso, total_pecas_loja,
                    total_pecas_entrada, diferenca_total, observacao, conferido_em
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    devolucao_id,
                    "",
                    status,
                    itens_distintos,
                    itens_ok,
                    itens_faltou,
                    itens_excesso,
                    total_pecas_loja,
                    total_pecas_entrada,
                    diferenca_total,
                    "",
                    agora,
                ),
            )

        conn.commit()

    return devolucao_id



def listar_devolucoes():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM devolucoes ORDER BY id DESC")
            return cur.fetchall()



def buscar_itens_devolucao(devolucao_id: int):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM devolucao_itens WHERE devolucao_id = %s ORDER BY id",
                (devolucao_id,),
            )
            return cur.fetchall()
