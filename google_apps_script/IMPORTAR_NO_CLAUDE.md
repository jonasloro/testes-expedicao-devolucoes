# Importar a automacao Gmail -> Pedidos de Devolucao

## Regra obrigatoria

Nunca alterar a API de producao do OutLog para implementar esta automacao.

A automacao roda fora do Streamlit:

`Gmail -> Google Apps Script -> PostgreSQL -> OutLog`

O OutLog apenas consome os pedidos gravados em `pedidos_devolucao` e `pedido_devolucao_lacres`.

## O que o Claude deve importar

Copiar para o ambiente principal estes arquivos:

- `google_apps_script/Code.gs`
- `google_apps_script/appsscript.json`
- `google_apps_script/sql/production_migration.sql`

Nao importar como codigo Python do Streamlit. O `Code.gs` deve ser colado em um projeto do Google Apps Script.

## Configuracao do banco

Criar no banco de destino uma role exclusiva chamada `outlog_devolucoes_bot`.

Executar o arquivo `sql/production_migration.sql` no mesmo banco. O script concede somente:

- CONNECT no banco;
- USAGE no schema public;
- SELECT e INSERT em `pedidos_devolucao`;
- SELECT e INSERT em `pedido_devolucao_lacres`;
- uso das sequences dessas duas tabelas.

Nao conceder permissao para as tabelas da API de producao do CD.

## Script Properties

No Google Apps Script, em Project Settings -> Script properties:

- `DB_URL` = URL JDBC do banco de destino, com TLS.
- `DB_USER` = `outlog_devolucoes_bot`.
- `DB_PASS` = senha da role.

Nao colocar essas credenciais no GitHub nem no `Code.gs`.

## Primeira ativacao

1. Criar o projeto do Google Apps Script.
2. Colar `Code.gs`.
3. Importar/configurar `appsscript.json`.
4. Configurar as Script Properties.
5. Executar `testarConexaoBanco()` uma vez.
6. Executar `processarEmailsDevolucao()` uma vez para autorizar Gmail e validar o primeiro processamento.
7. Executar `criarGatilho()` uma vez.

Depois disso, o script roda automaticamente a cada 5 minutos.

## Regras de negocio implementadas

- Status inicial do pedido: `PENDENTE`.
- So cria pedido se identificar numero da nota, loja e pelo menos um lacre.
- Data da coleta e transportadora sao opcionais.
- Volumes = quantidade de lacres encontrados.
- Entende formatos como `NOTA DE SAIDA 352`, `Devolucao NF 170`, `lacre 19152: infraestrutura`, `19118: RH...`.
- Descricoes de lacre podem continuar em varias linhas ate o proximo lacre.
- Tenta identificar a loja pelo cabecalho `De:`; se nao conseguir, usa o nome do remetente do Gmail.
- O corpo completo do e-mail nao e salvo no banco, reduzindo armazenamento.
- O ID da mensagem do Gmail fica em `origem_email_id` para auditoria e deduplicacao.
- O mesmo Gmail message ID nunca deve gerar dois pedidos.
- Uma mesma NF para a mesma loja tambem nao gera novo pedido enquanto o anterior nao estiver `CANCELADO`.
- E-mails incompletos recebem o label `OutLog/Devolucoes/Revisar` e nao criam pedido incompleto.
- E-mails processados recebem `OutLog/Devolucoes/Processado`.

## Integracao com o OutLog

O OutLog nao precisa de uma nova API para essa automacao.

A tela `Pedidos de Devolucao` consulta as duas tabelas do PostgreSQL. Quando o pedido estiver `RECEBIDO`, o fluxo operacional de Recebimento pode ser executado.

## Seguranca

- Nao usar `neondb_owner` no Apps Script.
- Nao usar credenciais da API de producao.
- Nao colocar senha em codigo, commit ou arquivo do repositorio.
- Nao alterar endpoints ou autenticacao da API existente do OutLog.
