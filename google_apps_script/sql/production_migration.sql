-- Aplicar NO BANCO que sera usado pela automacao.
-- Antes de executar, crie a role exclusiva `outlog_devolucoes_bot`.
-- Este arquivo nao cria nem altera a API de producao do OutLog.

-- Evita o mesmo e-mail do Gmail ser inserido duas vezes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_pedidos_devolucao_origem_email
    ON pedidos_devolucao (origem_email_id)
    WHERE origem_email_id IS NOT NULL
      AND origem_email_id <> '';

-- A role da automacao precisa apenas ler e inserir pedidos/lacres.
GRANT CONNECT ON DATABASE neondb TO outlog_devolucoes_bot;
GRANT USAGE ON SCHEMA public TO outlog_devolucoes_bot;

GRANT SELECT, INSERT
ON TABLE pedidos_devolucao
TO outlog_devolucoes_bot;

GRANT SELECT, INSERT
ON TABLE pedido_devolucao_lacres
TO outlog_devolucoes_bot;

GRANT USAGE, SELECT
ON SEQUENCE pedidos_devolucao_id_seq
TO outlog_devolucoes_bot;

GRANT USAGE, SELECT
ON SEQUENCE pedido_devolucao_lacres_id_seq
TO outlog_devolucoes_bot;

-- Importante: nao conceder acesso as tabelas de producao do CD.
