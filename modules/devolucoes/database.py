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
    """Confere se as tabelas essenciais existem no banco Neon.

    O schema principal é criado no SQL Editor do Neon. Mantemos aqui uma
    checagem simples para produzir um erro amigável caso o banco errado seja
    configurado no Streamlit.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS total
                FROM information_schema.tables
                WHERE table_schema = 'public'
                  AND table_name IN ('devolucoes', 'devolucao_itens', 'devolucao_conferencias')
                """
            )
            total = int(cur.fetchone()["total"])
            if total < 3:
                raise RuntimeError(
                    "O banco Neon ainda não possui todas as tabelas de devoluções. "
                    "Execute o SQL de criação do banco no Neon."
                )


def criar_devolucao(devolucao):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO devolucoes
                    (numero_documento, data_documento, cliente, tipo, status, criado_em)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    devolucao.numero_documento,
                    devolucao.data_documento or None,
                    devolucao.cliente,
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
                    numero_documento, data_documento, cliente, tipo, status, criado_em,
                    arquivo_loja, arquivo_entrada, total_pecas_loja, total_pecas_entrada,
                    diferenca_total, itens_distintos, resultado_conferencia, registrado_em
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    numero_documento,
                    data_documento or None,
                    cliente,
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
                        devolucao_id, codigo_barras, descricao, referencia, grade,
                        quantidade_loja, quantidade_entrada, diferenca, status, observacao
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        (
                            devolucao_id,
                            item.get("codigo_barras", ""),
                            item.get("descricao", ""),
                            item.get("referencia", ""),
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
