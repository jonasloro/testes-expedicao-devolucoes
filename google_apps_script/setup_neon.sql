-- Usuário exclusivo para a automação Gmail -> Pedidos de Devolução.
-- Execute este arquivo uma única vez no Neon com um usuário administrador/owner.
-- NÃO use as credenciais da API/usuário de produção do OutLog.

CREATE ROLE outlog_devolucao_bot LOGIN PASSWORD 'COLOQUE_UMA_SENHA_FORTE_AQUI';

GRANT CONNECT ON DATABASE postgres TO outlog_devolucao_bot;
GRANT USAGE ON SCHEMA public TO outlog_devolucao_bot;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.pedidos_devolucao
TO outlog_devolucao_bot;

GRANT SELECT, INSERT, UPDATE
ON TABLE public.pedido_devolucao_lacres
TO outlog_devolucao_bot;

GRANT USAGE, SELECT
ON SEQUENCE public.pedidos_devolucao_id_seq
TO outlog_devolucao_bot;

GRANT USAGE, SELECT
ON SEQUENCE public.pedido_devolucao_lacres_id_seq
TO outlog_devolucao_bot;

-- Depois de criar a role, NÃO deixe a senha neste arquivo do GitHub.
-- Troque a senha diretamente no Neon e use a senha final somente nas
-- Script Properties do Google Apps Script.
