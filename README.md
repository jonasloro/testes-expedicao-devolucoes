# Centro de Tratamento de Devoluções

Laboratório independente para criar, testar e validar melhorias da Expedição/Devoluções antes de levá-las para o aplicativo oficial.

## Regra principal

Este repositório não deve alterar nem depender da lógica do sistema oficial durante os testes. O sistema deve continuar modular e isolado do aplicativo oficial: novas funções não podem quebrar as já existentes.

## Fluxo oficial

Romaneio da Loja + Romaneio Entrada CD + Romaneio Entrada Anápolis → Conferência → Registro → Tratamento → Histórico → Indicadores

Regra da conferência: **Loja = Entrada CD + Entrada Anápolis**. O romaneio de Anápolis é documento oficial da conferência (a bipagem de defeitos em Anápolis é apenas um recurso auxiliar, usado quando o romaneio ainda não está disponível).

## Estrutura

```
app.py                              # roteador principal (sidebar + chamada da página selecionada)
modules/devolucoes/
    parser.py                       # leitura de PDF dos romaneios (robusta a linhas quebradas)
    database.py                     # persistência em Neon PostgreSQL
    services.py                     # comparação Loja x CD x Anápolis
    tratamento.py                   # tratativa em lote (4 destinos), sem mexer em estoque
    anapolis.py                     # bipagem auxiliar de defeitos em Anápolis
    models.py                       # dataclasses de apoio
    pages/                          # uma página Streamlit por arquivo (só UI, sem regra de negócio)
        dashboard.py
        recebimento.py
        conferencia.py
        pendencias.py
        tratamento.py
        anapolis.py
        historico.py
        indicadores.py
        configuracoes.py
```

## Persistência

O banco é o Neon PostgreSQL, configurado via `DATABASE_URL` (variável de ambiente ou `st.secrets`). Não há mais SQLite neste projeto — a migração já foi concluída.

## Parser de romaneios

O PDF real nem sempre mantém código de barras, referência, descrição, grade e quantidade/preço na mesma linha — qualquer um desses campos pode quebrar entre linhas. Por isso o parser junta o bloco inteiro do item (do código de barras até o próximo item) antes de procurar a grade e os números, em vez de procurar linha a linha. Isso evita dois problemas:

- Grades numéricas (ex.: `[38 40 42]`) sendo confundidas com quantidade/preço quando o colchete de fechamento cai em outra linha.
- Itens perdidos silenciosamente quando `[` e `]` ficam em linhas diferentes.

## Tratamento

A tratativa é feita em lote (não peça por peça) e considera o **total encontrado** de cada item (Entrada CD + Entrada Anápolis) — inclusive itens que só apareceram no romaneio de Anápolis. A tratativa apenas registra a decisão (AVARIA, ESTOCAR, ARMAZENAR PORTA-PALETE, ARMAZENAR - RUA 1); ela não altera estoque. A integração com estoque é um passo futuro.
