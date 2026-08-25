# Automação Gmail -> Pedidos de Devolução

Arquitetura final:

`Gmail -> Google Apps Script -> Neon Data API (role anonymous) -> PostgreSQL -> OutLog`

A automação fica fora do OutLog e não usa nem altera a API de produção.

## Configuração do Apps Script

Em **Project Settings -> Script Properties**, configure:

- `DATA_API_URL`: a URL do Data API do branch, terminando em `/neondb/rest/v1`.

Não usa Neon Auth nem JWT. O Data API do Neon já tem um mecanismo próprio pra
requisições sem autenticação: toda chamada sem cabeçalho `Authorization` é
executada automaticamente com o role do Postgres configurado em **Data API ->
Settings -> Anonymous role** (por padrão, `anonymous`). O script só precisa
chamar a URL do Data API direto — sem pedir nem guardar token nenhum.

## Configuração do banco

No branch usado pela automação, execute:

`google_apps_script/sql/neon_auth_anonymous.sql`

Esse SQL concede ao role `anonymous` acesso somente a `pedidos_devolucao`,
`pedido_devolucao_lacres` e respectivas sequências — é esse mesmo role que o
Data API usa quando a chamada não tem `Authorization`.

## Teste

1. Execute `testarConexaoBanco()`.
2. Execute `processarEmailsDevolucao()` manualmente uma vez.
3. Confirme o pedido no OutLog.
4. Execute `criarGatilho()` apenas depois que os testes manuais passarem.

## Regras do parser

- Nota pode vir no assunto ou no corpo (`NF 170`, `Devolução NF 170`, `NOTA DE SAÍDA 352`, etc.).
- Loja pode vir do `De:` ou do nome do remetente.
- Data e transportadora são opcionais.
- Cada lacre inicia um bloco e o texto continua até o próximo lacre.
- `volumes = quantidade de lacres`.
- Mensagens sem nota, loja ou lacre não criam pedido incompleto; recebem a etiqueta de revisão.
- Duplicidade é evitada pelo ID da mensagem do Gmail e por nota + loja.

## Segurança

- Nenhuma senha ou token é armazenado no repositório.
- O `OutLog-Distribox` principal não é modificado.
- O role `anonymous` só tem permissão nas duas tabelas de pedidos — nada além disso.
- Para produção, vale revisitar se esse nível de acesso (leitura/escrita sem autenticação nenhuma) é aceitável, ou se compensa reativar o Neon Auth com JWT mais pra frente.
