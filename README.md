# Centro de Tratamento de Devoluções

Laboratório independente para criar, testar e validar melhorias da Expedição antes de levá-las para o aplicativo oficial.

## Regra principal

Este repositório não deve alterar nem depender da lógica do sistema oficial durante os testes.

## Fluxo previsto

1. Recebimento do romaneio
2. Leitura e identificação da devolução
3. Conferência do que foi recebido
4. Registro de divergências e pendências
5. Decisão sobre o destino da mercadoria
6. Histórico do processo
7. Indicadores

## Estrutura

- `app.py` — interface principal do laboratório.
- `modules/devolucoes/models.py` — modelos de dados.
- `modules/devolucoes/parser.py` — leitura inicial de PDF.
- `modules/devolucoes/database.py` — banco local SQLite para testes.
- `modules/devolucoes/services.py` — regras/serviços do módulo.
- `data/` — dados locais gerados durante os testes.

## Observação sobre persistência

O banco SQLite é propositalmente local nesta primeira fase. Antes de usar o laboratório como sistema operacional, a persistência deverá ser transferida para uma solução adequada ao ambiente de produção.
