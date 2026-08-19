from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "devolucoes.db"


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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


def listar_devolucoes():
    with get_connection() as conn:
        return conn.execute(
            "SELECT * FROM devolucoes ORDER BY id DESC"
        ).fetchall()
