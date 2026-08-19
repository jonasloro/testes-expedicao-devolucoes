from pathlib import Path
import sqlite3
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "devolucoes.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS devolucoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                numero_documento TEXT NOT NULL,
                data_documento TEXT,
                cliente TEXT,
                tipo TEXT NOT NULL,
                status TEXT NOT NULL,
                criado_em TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS devolucao_itens (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                devolucao_id INTEGER NOT NULL,
                codigo_barras TEXT NOT NULL,
                descricao TEXT NOT NULL,
                referencia TEXT,
                grade TEXT,
                quantidade_romaneio INTEGER NOT NULL DEFAULT 0,
                quantidade_recebida INTEGER,
                observacao TEXT,
                FOREIGN KEY (devolucao_id) REFERENCES devolucoes(id)
            );
            """
        )

        for column, definition in [
            ("arquivo_loja", "TEXT"),
            ("arquivo_entrada", "TEXT"),
            ("total_pecas_loja", "INTEGER DEFAULT 0"),
            ("total_pecas_entrada", "INTEGER DEFAULT 0"),
            ("diferenca_total", "INTEGER DEFAULT 0"),
            ("itens_distintos", "INTEGER DEFAULT 0"),
            ("resultado_conferencia", "TEXT"),
            ("registrado_em", "TEXT"),
        ]:
            _ensure_column(conn, "devolucoes", column, definition)


def criar_devolucao(devolucao):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO devolucoes
                (numero_documento, data_documento, cliente, tipo, status, criado_em)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                devolucao.numero_documento,
                devolucao.data_documento,
                devolucao.cliente,
                devolucao.tipo,
                devolucao.status,
                devolucao.criado_em,
            ),
        )
        devolucao_id = cursor.lastrowid

        conn.executemany(
            """
            INSERT INTO devolucao_itens
                (devolucao_id, codigo_barras, descricao, referencia, grade,
                 quantidade_romaneio, quantidade_recebida, observacao)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    devolucao_id,
                    item.codigo_barras,
                    item.descricao,
                    item.referencia,
                    item.grade,
                    item.quantidade_romaneio,
                    item.quantidade_recebida,
                    item.observacao,
                )
                for item in devolucao.itens
            ],
        )

    return devolucao_id


def registrar_conferencia(
    numero_documento: str,
    data_documento: str,
    arquivo_loja: str,
    arquivo_entrada: str,
    resultado: list[dict],
    total_pecas_loja: int,
    total_pecas_entrada: int,
) -> int:
    diferenca_total = total_pecas_entrada - total_pecas_loja
    itens_distintos = len(resultado)
    tem_divergencia = any(item.get("status") != "OK" for item in resultado)
    status = "DIVERGENTE" if tem_divergencia else "CONFERIDA"
    agora = datetime.now().isoformat(timespec="seconds")

    with get_connection() as conn:
        existente = conn.execute(
            "SELECT id FROM devolucoes WHERE numero_documento = ? AND arquivo_loja = ? AND arquivo_entrada = ?",
            (numero_documento, arquivo_loja, arquivo_entrada),
        ).fetchone()
        if existente:
            return int(existente["id"])

        cursor = conn.execute(
            """
            INSERT INTO devolucoes (
                numero_documento, data_documento, cliente, tipo, status, criado_em,
                arquivo_loja, arquivo_entrada, total_pecas_loja, total_pecas_entrada,
                diferenca_total, itens_distintos, resultado_conferencia, registrado_em
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                numero_documento,
                data_documento,
                "",
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
        devolucao_id = int(cursor.lastrowid)

        conn.executemany(
            """
            INSERT INTO devolucao_itens (
                devolucao_id, codigo_barras, descricao, referencia, grade,
                quantidade_romaneio, quantidade_recebida, observacao
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                    item.get("status", ""),
                )
                for item in resultado
            ],
        )

        return devolucao_id


def listar_devolucoes():
    with get_connection() as conn:
        return conn.execute("SELECT * FROM devolucoes ORDER BY id DESC").fetchall()


def buscar_itens_devolucao(devolucao_id: int):
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM devolucao_itens WHERE devolucao_id = ? ORDER BY id",
            (devolucao_id,),
        ).fetchall()
