import os
from datetime import date, datetime

import psycopg
from psycopg.rows import dict_row


def normalizar_data(valor):
    """Converte datas brasileiras ou ISO para date do Python."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor

    texto = str(valor).strip()
    for formato in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue

    raise ValueError(f"Data inválida: {valor!r}. Use DD/MM/YYYY ou YYYY-MM-DD.")


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        try:
            import streamlit as st
            url = str(st.secrets.get("DATABASE_URL", "")).strip()
        except Exception:
            url = ""
    if not url:
        raise RuntimeError("DATABASE_URL não configurada. Adicione a connection string do Neon nos Secrets do Streamlit.")
    return url


def get_connection():
    return psycopg.connect(get_database_url(), row_factory=dict_row)


def init_db() -> None:
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
        arquivo_anapolis VARCHAR(500),
        total_pecas_loja INTEGER NOT NULL DEFAULT 0,
        total_pecas_entrada INTEGER NOT NULL DEFAULT 0,
        total_pecas_anapolis INTEGER NOT NULL DEFAULT 0,
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
        quantidade_anapolis INTEGER NOT NULL DEFAULT 0,
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
        total_pecas_anapolis INTEGER NOT NULL DEFAULT 0,
        diferenca_total INTEGER NOT NULL DEFAULT 0,
        observacao TEXT,
        conferido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS devolucao_tratamentos (
        id BIGSERIAL PRIMARY KEY,
        devolucao_id BIGINT NOT NULL REFERENCES devolucoes(id) ON DELETE CASCADE,
        devolucao_item_id BIGINT NOT NULL REFERENCES devolucao_itens(id) ON DELETE CASCADE,
        quantidade INTEGER NOT NULL CHECK (quantidade > 0),
        destino VARCHAR(30) NOT NULL,
        observacao TEXT,
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS defeitos_anapolis (
        id BIGSERIAL PRIMARY KEY,
        numero_documento VARCHAR(100) NOT NULL,
        codigo_barras VARCHAR(50) NOT NULL,
        quantidade INTEGER NOT NULL DEFAULT 1 CHECK (quantidade > 0),
        usuario VARCHAR(255),
        criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
            cur.execute("ALTER TABLE devolucoes ADD COLUMN IF NOT EXISTS loja VARCHAR(255)")
            cur.execute("ALTER TABLE devolucoes ADD COLUMN IF NOT EXISTS arquivo_anapolis VARCHAR(500)")
            cur.execute("ALTER TABLE devolucoes ADD COLUMN IF NOT EXISTS total_pecas_anapolis INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE devolucao_itens ADD COLUMN IF NOT EXISTS quantidade_anapolis INTEGER NOT NULL DEFAULT 0")
            cur.execute("ALTER TABLE devolucao_conferencias ADD COLUMN IF NOT EXISTS total_pecas_anapolis INTEGER NOT NULL DEFAULT 0")
        conn.commit()


def registrar_conferencia(
    numero_documento,
    data_documento,
    arquivo_loja,
    arquivo_entrada,
    arquivo_anapolis,
    resultado,
    total_pecas_loja,
    total_pecas_entrada,
    total_pecas_anapolis,
    cliente="",
    loja="",
) -> int:
    data_documento = normalizar_data(data_documento)
    total_anapolis = int(total_pecas_anapolis or 0)
    diferenca_total = int(total_pecas_entrada or 0) + total_anapolis - int(total_pecas_loja or 0)
    itens_distintos = len(resultado)
    tem_divergencia = any(item.get("status") != "OK" for item in resultado)
    status = "DIVERGENTE" if tem_divergencia else "AGUARDANDO TRATAMENTO"
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
                  AND COALESCE(arquivo_anapolis, '') = %s
                ORDER BY id DESC
                LIMIT 1
                """,
                (numero_documento, arquivo_loja, arquivo_entrada, arquivo_anapolis),
            )
            existente = cur.fetchone()
            if existente:
                return int(existente["id"])

            cur.execute(
                """
                INSERT INTO devolucoes (
                    numero_documento, data_documento, cliente, loja, tipo, status, criado_em,
                    arquivo_loja, arquivo_entrada, arquivo_anapolis,
                    total_pecas_loja, total_pecas_entrada, total_pecas_anapolis,
                    diferenca_total, itens_distintos, resultado_conferencia, registrado_em
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING id
                """,
                (
                    numero_documento,
                    data_documento,
                    cliente,
                    loja,
                    "DEVOLUÇÃO",
                    status,
                    agora,
                    arquivo_loja,
                    arquivo_entrada,
                    arquivo_anapolis,
                    total_pecas_loja,
                    total_pecas_entrada,
                    total_anapolis,
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
                        quantidade_loja, quantidade_entrada, quantidade_anapolis,
                        diferenca, status, observacao
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                            int(item.get("qtd_anapolis", 0)),
                            int(item.get("diferenca", 0)),
                            item.get("status", ""),
                            item.get("observacao", ""),
                        )
                        for item in resultado
                    ],
                )

                # Regra operacional: toda peça que aparece no romaneio oficial
                # de Anápolis entra automaticamente como AVARIA. Isso elimina
                # a necessidade de selecionar manualmente essas peças na tratativa.
                cur.execute(
                    """
                    INSERT INTO devolucao_tratamentos (
                        devolucao_id, devolucao_item_id, quantidade, destino, observacao
                    )
                    SELECT
                        devolucao_id,
                        id,
                        quantidade_anapolis,
                        'AVARIA',
                        'Entrada proveniente do romaneio de Anápolis — avaria automática.'
                    FROM devolucao_itens
                    WHERE devolucao_id = %s
                      AND quantidade_anapolis > 0
                    """,
                    (devolucao_id,),
                )

            itens_ok = sum(item.get("status") == "OK" for item in resultado)
            itens_faltou = sum(item.get("status") == "FALTOU" for item in resultado)
            itens_excesso = sum(item.get("status") == "EXCESSO" for item in resultado)
            cur.execute(
                """
                INSERT INTO devolucao_conferencias (
                    devolucao_id, usuario, status, total_itens, itens_ok, itens_faltou,
                    itens_excesso, total_pecas_loja, total_pecas_entrada,
                    total_pecas_anapolis, diferenca_total, observacao, conferido_em
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
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
                    total_anapolis,
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
            cur.execute("SELECT * FROM devolucao_itens WHERE devolucao_id = %s ORDER BY id", (devolucao_id,))
            return cur.fetchall()


def listar_defeitos_anapolis(numero_documento: str):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT codigo_barras, SUM(quantidade) AS quantidade
                FROM defeitos_anapolis
                WHERE numero_documento = %s
                GROUP BY codigo_barras
                ORDER BY codigo_barras
                """,
                (str(numero_documento).strip(),),
            )
            return cur.fetchall()


def registrar_bip_anapolis(numero_documento: str, codigo_barras: str, usuario: str = ""):
    codigo = "".join(ch for ch in str(codigo_barras) if ch.isdigit())
    if not codigo:
        raise ValueError("Código de barras inválido.")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO defeitos_anapolis (numero_documento, codigo_barras, quantidade, usuario) VALUES (%s,%s,1,%s)",
                (str(numero_documento).strip(), codigo, usuario),
            )
        conn.commit()


def remover_ultimo_bip_anapolis(numero_documento: str, codigo_barras: str):
    codigo = "".join(ch for ch in str(codigo_barras) if ch.isdigit())
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM defeitos_anapolis WHERE numero_documento = %s AND codigo_barras = %s ORDER BY id DESC LIMIT 1",
                (str(numero_documento).strip(), codigo),
            )
            row = cur.fetchone()
            if row:
                cur.execute("DELETE FROM defeitos_anapolis WHERE id = %s", (row["id"],))
        conn.commit()
