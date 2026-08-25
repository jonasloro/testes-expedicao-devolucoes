# Automação Gmail -> Pedidos de Devolução

Arquitetura final:

`Gmail -> Google Apps Script -> Neon Auth (token anônimo) -> Neon Data API -> PostgreSQL -> OutLog`

A automação fica fora do OutLog e não usa nem altera a API de produção.

## Configuração do Apps Script

Em **Project Settings -> Script Properties**, configure:

- `DATA_API_URL`: a URL do Data API do branch, terminando em `/neondb/rest/v1`.
- `NEON_AUTH_URL`: a URL base do Neon Auth, terminando em `/neondb/auth`.

O script pede automaticamente um token anônimo em `GET /token/anonymous`
(não é `POST`, e não é `/sign-in/anonymous` — confirme o endpoint certo em
`{NEON_AUTH_URL}/reference`, buscando por "anonymous", caso a API do Neon
mude de novo no futuro), guarda o token em cache por 10 minutos e renova
sozinho quando expira ou é rejeitado.

Não é necessário copiar ou guardar token manualmente.

Para este projeto, a URL base do Neon Auth é formada removendo
`/.well-known/jwks.json` da URL JWKS fornecida pelo Neon.

O Data API do Neon **exige token válido em toda chamada**, mesmo pra dados
públicos — não existe modo "sem autenticação nenhuma". O papel do token
anônimo é justamente autenticar como o role `anonymous` do Postgres.

## Configuração do banco

No branch usado pela automação, execute:

`google_apps_script/sql/neon_auth_anonymous.sql`

Esse SQL concede ao role `anonymous` acesso somente a `pedidos_devolucao`,
`pedido_devolucao_lacres` e respectivas sequências.

## Teste

1. Execute `testarTokenNeonAuth()`.
2. Execute `testarConexaoBanco()`.
3. Execute `processarEmailsDevolucao()` manualmente uma vez.
4. Confirme o pedido no OutLog.
5. Execute `criarGatilho()` apenas depois que os testes manuais passarem.

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
