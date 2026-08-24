-- Executar APENAS no branch que sera usado pela automacao.
-- Nao altera o OutLog-Distribox nem a API de producao.
-- O role `anonymous` e usado pelo JWT anonimo emitido pelo Neon Auth.

GRANT CONNECT ON DATABASE neondb TO anonymous;
GRANT USAGE ON SCHEMA public TO anonymous;

GRANT SELECT, INSERT, UPDATE
ON TABLE pedidos_devolucao
TO anonymous;

GRANT SELECT, INSERT, UPDATE
ON TABLE pedido_devolucao_lacres
TO anonymous;

GRANT USAGE, SELECT
ON SEQUENCE pedidos_devolucao_id_seq
TO anonymous;

GRANT USAGE, SELECT
ON SEQUENCE pedido_devolucao_lacres_id_seq
TO anonymous;
