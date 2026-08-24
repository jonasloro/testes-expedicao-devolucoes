# Automação Gmail -> Pedidos de Devolução

Esta automação foi desenhada para ficar **fora do OutLog**. Ela não usa nem altera a API de produção do aplicativo.

## Arquitetura

`Gmail -> Google Apps Script -> JDBC -> PostgreSQL -> OutLog`

O Google Apps Script lê mensagens de devolução e grava diretamente nas tabelas `pedidos_devolucao` e `pedido_devolucao_lacres`. O OutLog continua apenas lendo os pedidos.

O serviço JDBC do Google Apps Script suporta PostgreSQL externo. Para bancos externos, é necessário permitir os IPs de origem do Apps Script no banco e usar TLS. Consulte a documentação oficial do Google antes de abrir a conexão.  

## Antes de ativar

1. Criar um projeto em `script.google.com`.
2. Copiar o conteúdo de `Code.gs` para o projeto.
3. Em **Project Settings > Script properties**, configurar:
   - `DB_URL`: `jdbc:postgresql://HOST:5432/BANCO?sslmode=require`
   - `DB_USER`: usuário exclusivo da automação
   - `DB_PASS`: senha desse usuário
4. No Neon/PostgreSQL, permitir os IPs de origem do Apps Script conforme a documentação do Google.
5. Executar `processarEmailsDevolucao()` manualmente uma primeira vez para autorizar Gmail e JDBC e testar a conexão.
6. Executar `criarGatilho()` uma única vez. Ele cria a rotina automática de verificação.

## Segurança

- Nunca colocar usuário, senha ou connection string diretamente no `Code.gs`.
- Usar um usuário PostgreSQL exclusivo para essa automação.
- Esse usuário deve ter acesso somente às tabelas necessárias para pedidos de devolução.
- Não reutilizar credenciais da API de produção do OutLog.
- A deduplicação usa o ID da mensagem do Gmail em `origem_email_id`.

## Comportamento

O script cria automaticamente apenas pedidos que tenham:

- número da nota;
- loja identificada;
- pelo menos um lacre.

Data e transportadora são opcionais.

Volumes são calculados como **quantidade de lacres**, independentemente do número de volumes escrito no e-mail.

E-mails que não puderem ser interpretados com segurança não viram pedidos incompletos; são marcados para revisão.

## Importante

A conexão JDBC é direta com o PostgreSQL e portanto não passa pela API de produção do OutLog. Isso mantém a automação de devoluções isolada do fluxo operacional existente.
