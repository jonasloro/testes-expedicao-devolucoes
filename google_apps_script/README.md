# Automação Gmail -> Pedidos de Devolução

Esta automação fica **fora do OutLog** e não usa nem altera a API de produção do aplicativo.

## Arquitetura

`Gmail -> Google Apps Script -> HTTPS -> Neon Data API -> PostgreSQL -> OutLog`

O Google Apps Script lê as mensagens do Gmail e grava os pedidos diretamente pelas rotas REST do Neon Data API. O OutLog continua consumindo as tabelas de pedidos.

O Data API é uma interface REST compatível com PostgREST e cada branch do Neon possui seu próprio endpoint. Para o branch de testes, a própria tela do Neon informa quando as tabelas estão disponíveis sem RLS. Em produção, a recomendação é usar autenticação + PostgreSQL RLS no Data API.

## Configuração do Apps Script

1. Criar um projeto em `script.google.com`.
2. Copiar o conteúdo de `Code.gs` para o projeto.
3. Em **Project Settings > Script properties**, configurar:
   - `DATA_API_URL`: a URL exibida em **Neon > branch > Data API > API URL**, terminando em `/rest/v1`.
   - `DATA_API_TOKEN`: opcional no branch de testes quando a Data API estiver configurada sem RLS/autenticação; em produção deve ser usado o mecanismo de autenticação configurado no Data API.
4. Salvar as propriedades.
5. Executar `testarConexaoBanco()` uma vez. Essa função apenas faz um `GET` de teste e não grava dados.
6. Executar `processarEmailsDevolucao()` manualmente uma vez para autorizar o Gmail e validar o fluxo completo.
7. Executar `criarGatilho()` uma única vez. Ele remove gatilhos anteriores da mesma função e cria um gatilho de 5 minutos.

## O que não deve ser colocado no código

- Senha de banco.
- Connection string PostgreSQL.
- Credenciais da API de produção do OutLog.
- Tokens em arquivo versionado no GitHub.

As credenciais/configurações ficam apenas nas Script Properties do Google Apps Script.

## Segurança e produção

A Data API expõe tabelas diretamente por HTTPS. O Neon recomenda autenticação e RLS para controlar o acesso aos dados. O branch de produção não deve ser colocado em operação pública com RLS desativado.

A role `outlog_devolucoes_bot` continua útil para administração/migração do banco, mas a chamada efetiva desta automação é HTTP contra a Data API, não JDBC.

## Comportamento

O script cria automaticamente apenas pedidos que tenham:

- número da nota;
- loja identificada;
- pelo menos um lacre.

Data e transportadora são opcionais.

Volumes são calculados como **quantidade de lacres**, independentemente do número de volumes escrito no e-mail.

O parser aceita, entre outros formatos:

- `NOTA DE SAÍDA 352`;
- `Devolução NF 170`;
- `lacre 19152: infraestrutura`;
- `19118: RH, financeiro...`;
- descrições quebradas em várias linhas.

E-mails que não puderem ser interpretados com segurança não viram pedidos incompletos; recebem a etiqueta de revisão.

A deduplicação usa o ID da mensagem do Gmail e também verifica NF + loja.

O banco recebe somente os dados estruturados do pedido. O corpo completo do e-mail não é armazenado pela automação.
