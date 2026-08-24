-- Infraestrutura da automacao de pedidos de devolucao.
-- Nao altera a API de producao do OutLog.
--
-- A automacao atual usa Neon Data API por HTTPS, portanto estas GRANTs
-- de uma role PostgreSQL nao sao usadas pelo Google Apps Script diretamente.
-- Mantenha-as apenas como infraestrutura administrativa, se desejado.

-- Evita o mesmo e-mail do Gmail ser inserido duas vezes.
CREATE UNIQUE INDEX IF NOT EXISTS ux_pedidos_devolucao_origem_email
    ON pedidos_devolucao (origem_email_id)
    WHERE origem_email_id IS NOT NULL
      AND origem_email_id <> '';

-- Opcional: role administrativa exclusiva para consultas/manutencao SQL.
-- A chamada do Apps Script ocorre via Data API, nao via JDBC.
GRANT CONNECT ON DATABASE neondb TO outlog_devolucoes_bot;
GRANT USAGE ON SCHEMA public TO outlog_devolucoes_bot;
GRANT SELECT, INSERT, UPDATE ON TABLE pedidos_devolucao TO outlog_devolucoes_bot;
GRANT SELECT, INSERT, UPDATE ON TABLE pedido_devolucao_lacres TO outlog_devolucoes_bot;
GRANT USAGE, SELECT ON SEQUENCE pedidos_devolucao_id_seq TO outlog_devolucoes_bot;
GRANT USAGE, SELECT ON SEQUENCE pedido_devolucao_lacres_id_seq TO outlog_devolucoes_bot;

-- Nao conceder acesso as tabelas de producao do CD.
