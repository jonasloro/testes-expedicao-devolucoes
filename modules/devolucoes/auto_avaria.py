from .database import get_connection


def init_auto_avaria_db() -> None:
    """Cria um gatilho que transforma automaticamente Anápolis em AVARIA."""
    sql = """
    CREATE OR REPLACE FUNCTION registrar_avaria_anapolis()
    RETURNS TRIGGER
    LANGUAGE plpgsql
    AS $$
    BEGIN
        IF NEW.quantidade_anapolis IS NOT NULL AND NEW.quantidade_anapolis > 0 THEN
            INSERT INTO devolucao_tratamentos (
                devolucao_id, devolucao_item_id, quantidade, destino, observacao
            )
            VALUES (
                NEW.devolucao_id,
                NEW.id,
                NEW.quantidade_anapolis,
                'AVARIA',
                'Entrada proveniente do romaneio de Anápolis — avaria automática.'
            );
        END IF;
        RETURN NEW;
    END;
    $$;

    DROP TRIGGER IF EXISTS trg_avaria_anapolis ON devolucao_itens;

    CREATE TRIGGER trg_avaria_anapolis
    AFTER INSERT OR UPDATE OF quantidade_anapolis
    ON devolucao_itens
    FOR EACH ROW
    EXECUTE FUNCTION registrar_avaria_anapolis();
    """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
