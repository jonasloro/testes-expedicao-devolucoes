/**
 * AUTOMACAO DE PEDIDOS DE DEVOLUCAO
 *
 * Gmail -> Google Apps Script -> Neon Auth (token anonimo) -> Neon Data API -> PostgreSQL -> OutLog
 *
 * Este script fica FORA do OutLog e nao usa a API de producao.
 * Nao usa JDBC/PostgreSQL direto.
 * O Data API exige um JWT valido em toda chamada — mesmo pra role anonymous,
 * o token precisa vir preenchido (GET /token/anonymous no Neon Auth).
 *
 * Script Properties obrigatorias:
 *   DATA_API_URL  = URL do Neon Data API, terminando em /neondb/rest/v1
 *   NEON_AUTH_URL  = URL base do Neon Auth, terminando em /neondb/auth
 *
 * Exemplo:
 *   DATA_API_URL = https://...neon.tech/neondb/rest/v1
 *   NEON_AUTH_URL = https://...neonauth...neon.tech/neondb/auth
 */

const CONFIG = Object.freeze({
  // Essa caixa é dedicada só a devolução — todo e-mail que chega aqui é
  // candidato. Não filtra por palavra-chave (isso já causou e-mail real
  // passar batido por não bater com o texto esperado); pega tudo recente e
  // deixa analisarEmail() decidir se tem nota+loja+lacre reconhecíveis.
  GMAIL_QUERY: 'newer_than:3d in:inbox',
  MAX_THREADS: 50,
  LABEL_PROCESSADO: 'OutLog/Devoluções/Processado',
  LABEL_REVISAO: 'OutLog/Devoluções/Revisar',
  FUNCAO_GATILHO: 'processarEmailsDevolucao',
  INTERVALO_MINUTOS: 5,
  TABELA_PEDIDOS: 'pedidos_devolucao',
  TABELA_LACRES: 'pedido_devolucao_lacres',
  TOKEN_CACHE_SECONDS: 600,
  PASTA_ROMANEIOS_DRIVE: 'OutLog - Romaneios de Devolução (auto)',
});

function obterOuCriarPastaRomaneios_() {
  const pastas = DriveApp.getFoldersByName(CONFIG.PASTA_ROMANEIOS_DRIVE);
  if (pastas.hasNext()) return pastas.next();
  return DriveApp.createFolder(CONFIG.PASTA_ROMANEIOS_DRIVE);
}

/**
 * Se o e-mail veio com um PDF anexado (o romaneio), salva uma cópia numa
 * pasta própria do Drive dessa conta e deixa acessível por link — o OutLog
 * baixa e lê esse PDF automaticamente na tela de inspeção do pedido. Se não
 * tiver PDF anexado, retorna null e o pedido nasce sem romaneio vinculado
 * (segue o fluxo manual de sempre).
 */
function salvarAnexoRomaneio_(message, numeroNota) {
  const anexos = message.getAttachments({ includeInlineImages: false });
  const pdf = anexos.filter(function (a) { return a.getContentType() === 'application/pdf'; })[0];
  if (!pdf) return null;

  const pasta = obterOuCriarPastaRomaneios_();
  const sufixo = (numeroNota || 'sem-nota') + '_' + new Date().getTime();
  const arquivo = pasta.createFile(pdf.copyBlob().setName('Romaneio_NF' + sufixo + '.pdf'));
  arquivo.setSharing(DriveApp.Access.ANYONE_WITH_LINK, DriveApp.Permission.VIEW);

  return {
    url: 'https://drive.google.com/uc?export=download&id=' + arquivo.getId(),
    nome: pdf.getName(),
  };
}

function obterConfiguracaoApi_() {
  const props = PropertiesService.getScriptProperties();
  const dataApiUrl = (props.getProperty('DATA_API_URL') || '').trim().replace(/\/$/, '');
  const authUrl = (props.getProperty('NEON_AUTH_URL') || '').trim().replace(/\/$/, '');

  if (!dataApiUrl) {
    throw new Error('Configure DATA_API_URL nas Script Properties.');
  }

  if (!authUrl) {
    throw new Error('Configure NEON_AUTH_URL nas Script Properties.');
  }

  return { dataApiUrl, authUrl };
}

function obterTokenAnonimo_() {
  const cache = CacheService.getScriptCache();
  const tokenCacheado = cache.get('NEON_ANON_JWT');
  if (tokenCacheado) return tokenCacheado;

  const cfg = obterConfiguracaoApi_();
  const url = cfg.authUrl + '/token/anonymous';

  const response = UrlFetchApp.fetch(url, {
    method: 'get',
    muteHttpExceptions: true,
    headers: { Accept: 'application/json' },
  });

  const status = response.getResponseCode();
  const text = response.getContentText() || '';

  if (status < 200 || status >= 300) {
    throw new Error(
      'Neon Auth nao conseguiu emitir token anonimo. HTTP ' +
        status + ': ' +
        text.substring(0, 800)
    );
  }

  let data;
  try {
    data = JSON.parse(text);
  } catch (err) {
    throw new Error('Resposta inesperada do Neon Auth: ' + text.substring(0, 800));
  }

  const token =
    data.token ||
    data.access_token ||
    data.jwt ||
    (data.data && (data.data.token || data.data.access_token || data.data.jwt));

  if (!token) {
    throw new Error(
      'Neon Auth respondeu sem JWT. Resposta: ' + JSON.stringify(data).substring(0, 800)
    );
  }

  cache.put('NEON_ANON_JWT', token, CONFIG.TOKEN_CACHE_SECONDS);
  return token;
}

function dataApiRequest_(endpoint, method, body, prefer) {
  const cfg = obterConfiguracaoApi_();
  const token = obterTokenAnonimo_();
  const url = cfg.dataApiUrl + '/' + String(endpoint || '').replace(/^\//, '');

  const headers = {
    Accept: 'application/json',
    'Content-Type': 'application/json',
    Authorization: 'Bearer ' + token,
  };

  if (prefer) headers.Prefer = prefer;

  let response = UrlFetchApp.fetch(url, {
    method: method || 'get',
    headers: headers,
    muteHttpExceptions: true,
    ...(body !== undefined && body !== null
      ? { payload: JSON.stringify(body) }
      : {}),
  });

  let status = response.getResponseCode();

  // Se o token expirou/invalido, limpa o cache e tenta uma vez com outro token.
  if (status === 401 || status === 403) {
    CacheService.getScriptCache().remove('NEON_ANON_JWT');
    const novoToken = obterTokenAnonimo_();
    headers.Authorization = 'Bearer ' + novoToken;
    response = UrlFetchApp.fetch(url, {
      method: method || 'get',
      headers: headers,
      muteHttpExceptions: true,
      ...(body !== undefined && body !== null
        ? { payload: JSON.stringify(body) }
        : {}),
    });
    status = response.getResponseCode();
  }

  const text = response.getContentText() || '';

  if (status < 200 || status >= 300) {
    throw new Error(
      'Neon Data API respondeu HTTP ' + status + ': ' + text.substring(0, 800)
    );
  }

  if (!text.trim()) return null;

  try {
    return JSON.parse(text);
  } catch (err) {
    return text;
  }
}

/** Teste seguro: pede token anonimo e consulta a Data API. Nao grava dados. */
function testarDataApi() {
  const data = dataApiRequest_(
    CONFIG.TABELA_PEDIDOS + '?select=id&limit=1',
    'get'
  );
  console.log('Neon Data API OK. Resposta: ' + JSON.stringify(data));
}

function testarConexaoBanco() {
  testarDataApi();
}

function testarTokenNeonAuth() {
  const token = obterTokenAnonimo_();
  console.log('Token anonimo obtido com sucesso. Tamanho: ' + token.length);
}

function processarEmailsDevolucao() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) {
    console.log('Outra execucao ja esta em andamento. Esta foi ignorada.');
    return;
  }

  try {
    const processado = obterOuCriarLabel_(CONFIG.LABEL_PROCESSADO);
    const revisar = obterOuCriarLabel_(CONFIG.LABEL_REVISAO);
    const threads = GmailApp.search(CONFIG.GMAIL_QUERY, 0, CONFIG.MAX_THREADS);

    let criados = 0;
    let existentes = 0;
    let revisao = 0;
    let ignorados = 0;

    for (const thread of threads) {
      const labels = thread.getLabels().map(label => label.getName());
      if (
        labels.indexOf(CONFIG.LABEL_PROCESSADO) >= 0 ||
        labels.indexOf(CONFIG.LABEL_REVISAO) >= 0
      ) {
        console.log('Ignorado (thread já rotulada Processado/Revisar): ' + thread.getFirstMessageSubject());
        ignorados++;
        continue;
      }

      for (const message of thread.getMessages()) {
        const gmailId = message.getId();

        if (foiProcessado_(gmailId)) {
          console.log('Ignorado (gmailId já registrado no banco): ' + (message.getSubject() || '') + ' | id=' + gmailId);
          processado.addToThread(thread);
          ignorados++;
          continue;
        }

        const assunto = message.getSubject() || '';
        const corpo = message.getPlainBody() || message.getBody() || '';
        const remetente = message.getFrom() || '';
        const dados = analisarEmail(assunto, corpo, remetente);

        if (!dados.numeroNota || !dados.loja || dados.lacres.length === 0) {
          revisar.addToThread(thread);
          registrarEmailPendente_(gmailId, assunto, dados, message.getDate());
          revisao++;
          break;
        }

        const resultado = criarPedido_(gmailId, assunto, dados, obterAnexoComFallback_(message, dados.numeroNota));
        processado.addToThread(thread);

        if (resultado.criado) criados++;
        else existentes++;
      }
    }

    console.log(JSON.stringify({ criados, existentes, revisao, ignorados }));
  } finally {
    lock.releaseLock();
  }
}

function obterOuCriarLabel_(nome) {
  return GmailApp.getUserLabelByName(nome) || GmailApp.createLabel(nome);
}

function criarGatilho() {
  for (const trigger of ScriptApp.getProjectTriggers()) {
    if (trigger.getHandlerFunction() === CONFIG.FUNCAO_GATILHO) {
      ScriptApp.deleteTrigger(trigger);
    }
  }

  ScriptApp.newTrigger(CONFIG.FUNCAO_GATILHO)
    .timeBased()
    .everyMinutes(CONFIG.INTERVALO_MINUTOS)
    .create();

  console.log(
    'Gatilho criado para rodar a cada ' + CONFIG.INTERVALO_MINUTOS + ' minutos.'
  );
}

function foiProcessado_(gmailId) {
  const filtro =
    '?select=id&origem_email_id=eq.' + encodeURIComponent(gmailId) + '&limit=1';
  const resultado = dataApiRequest_(CONFIG.TABELA_PEDIDOS + filtro, 'get');
  return Array.isArray(resultado) && resultado.length > 0;
}

function pedidoExistente_(numeroNota, loja) {
  const query =
    '?select=id' +
    '&numero_nota=eq.' + encodeURIComponent(numeroNota) +
    '&loja=eq.' + encodeURIComponent(loja) +
    '&status=neq.CANCELADO' +
    '&order=id.desc&limit=1';

  const resultado = dataApiRequest_(CONFIG.TABELA_PEDIDOS + query, 'get');
  return Array.isArray(resultado) && resultado.length > 0
    ? resultado[0]
    : null;
}

function obterAnexoComFallback_(message, numeroNota) {
  try {
    return salvarAnexoRomaneio_(message, numeroNota);
  } catch (err) {
    console.log('Falha ao salvar anexo do romaneio (pedido segue sem anexo): ' + err);
    return null;
  }
}

function criarPedido_(gmailId, assunto, dados, anexo) {
  if (foiProcessado_(gmailId)) return { id: null, criado: false };

  const existente = pedidoExistente_(dados.numeroNota, dados.loja);
  if (existente) return { id: existente.id, criado: false };

  const pedidoPayload = {
    numero_nota: dados.numeroNota,
    loja: dados.loja,
    data_coleta: dados.dataColeta || null,
    transportadora: dados.transportadora || '',
    volumes: dados.lacres.length,
    status: 'PENDENTE',
    origem_email_id: gmailId,
    assunto_email: assunto || '',
    observacao: montarObservacaoCompacta_(dados),
    arquivo_romaneio_url: anexo ? anexo.url : null,
    arquivo_romaneio_nome: anexo ? anexo.nome : null,
  };

  const pedidoCriado = dataApiRequest_(
    CONFIG.TABELA_PEDIDOS,
    'post',
    pedidoPayload,
    'return=representation'
  );

  const pedido = Array.isArray(pedidoCriado) ? pedidoCriado[0] : pedidoCriado;

  if (!pedido || !pedido.id) {
    throw new Error(
      'A Data API criou o pedido, mas nao devolveu o ID: ' +
        JSON.stringify(pedidoCriado)
    );
  }

  const lacresPayload = dados.lacres.map(lacre => ({
    pedido_id: pedido.id,
    lacre: lacre.lacre,
    descricao: lacre.descricao || '',
  }));

  if (lacresPayload.length > 0) {
    dataApiRequest_(
      CONFIG.TABELA_LACRES,
      'post',
      lacresPayload,
      'resolution=merge-duplicates,return=minimal'
    );
  }

  return { id: pedido.id, criado: true };
}

function montarObservacaoCompacta_(dados) {
  const partes = [
    'Importado automaticamente do Gmail.',
    'Lacres: ' + dados.lacres.length + '.',
  ];
  if (dados.notaGerada) {
    partes.push('⚠️ Sem número de nota no e-mail — identificador gerado a partir do lacre.');
  }
  if (dados.transportadora) partes.push('Transportadora: ' + dados.transportadora + '.');
  if (dados.dataColeta) partes.push('Data da coleta: ' + dados.dataColeta + '.');
  return partes.join(' ');
}

function registrarEmailPendente_(gmailId, assunto, dados, dataMensagem) {
  console.log(
    JSON.stringify({
      tipo: 'REVISAO',
      gmailId,
      assunto,
      numeroNota: dados.numeroNota,
      loja: dados.loja,
      lacres: dados.lacres.length,
      dataMensagem: dataMensagem ? dataMensagem.toISOString() : null,
    })
  );
}

function analisarEmail(assunto, texto, remetente) {
  const bruto = String(texto || '');
  const assuntoTexto = String(assunto || '');
  const remetenteTexto = String(remetente || '');
  // E-mails podem chegar com VÁRIAS camadas de encaminhamento empilhadas
  // (loja -> pessoa A -> pessoa B -> Trello -> pessoa C -> aqui). O corpo
  // de verdade e o remetente de verdade (a loja) estão sempre na camada
  // MAIS INTERNA — a última, não a primeira.
  const corpo = extrairCorpoOriginal_(bruto);
  const fonte = assuntoTexto + '\n' + bruto + '\n' + corpo;

  const numeroNota = primeiroGrupo(
    [
      /(?:NOTA\s+DE\s+SA[IÍ]DA|NOTA|NF|N[ÚU]MERO\s+DA\s+NOTA)\s*[:#-]?\s*(\d+)\b/i,
      /\bDEVOLU(?:C|Ç)[AÃ]O\s+NF\s*(\d+)\b/i,
      /\bSA[IÍ]DA\s+(\d+)\b/i,
    ],
    fonte
  );

  let loja = primeiroGrupo(
    [
      /^\s*(?:De|From):\s*(?:Loja\s+)?Ger[eê]ncia\s+(.+?)(?:\s*<[^>]+>)?\s*$/im,
      /^\s*(?:De|From):\s*(?:Loja\s+)?(.+?)(?:\s*<[^>]+>)?\s*$/im,
    ],
    extrairNucleoParaLoja_(bruto)
  );

  if (!loja) loja = extrairNomeRemetente_(remetenteTexto);
  loja = limparNomeLoja_(loja);

  let dataColeta = primeiroGrupo(
    [
      /(?:na|em)\s+data\s+(?:de\s+)?(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
      /(?:saiu|coleta|recolhimento|retirada)[^\n]{0,80}(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
    ],
    corpo
  );
  if (dataColeta) dataColeta = normalizarData(dataColeta);

  const transportadora = limparTexto(
    primeiroGrupo(
      [
        /recolhido\s+pela\s+transportadora\s+([^,\n.]+)/i,
        /transportadora\s*[:\-]\s*([^\n.]+)/i,
        /pela\s+transportadora\s+([^,\n.]+)/i,
      ],
      corpo
    )
  );

  const lacres = extrairBlocosDeLacre(corpo);

  // Nem toda loja manda um número de nota/NF reconhecível — às vezes é só
  // uma "nota de transferência" sem número, ou vem num formato totalmente
  // fora do padrão. Nesse caso, em vez de travar em revisão manual (loja e
  // lacre são as informações realmente confiáveis, isso a gente tem), gera
  // um identificador próprio a partir do primeiro lacre — determinístico
  // (mesmo e-mail sempre gera o mesmo código, não duplica) e claramente
  // marcado como não sendo um NF oficial.
  let numeroNotaFinal = numeroNota;
  let notaGerada = false;
  if (!numeroNotaFinal && loja && lacres.length > 0) {
    numeroNotaFinal = 'TRANSF-' + lacres[0].lacre;
    notaGerada = true;
  }

  return {
    numeroNota: numeroNotaFinal,
    notaGerada,
    loja,
    dataColeta: dataColeta || null,
    transportadora,
    lacres,
    corpo,
  };
}

/** Marca genérica de "início de uma camada de encaminhamento" — cobre tanto
 * o Gmail em português ("Mensagem encaminhada") quanto em inglês
 * ("Forwarded message"), já que numa mesma cadeia de encaminhamentos reais
 * observamos as duas formas misturadas. */
var DELIMITADOR_ENCAMINHAMENTO_RE = /^-{3,}\s*(?:Forwarded message|Mensagem encaminhada)\s*-{3,}\s*$/im;

/** Acha a última (mais interna) camada de encaminhamento e devolve os
 * primeiros ~20 linhas a partir dali — é onde fica o cabeçalho "De:"/"From:"
 * de quem realmente mandou o e-mail original (a loja), não de quem
 * encaminhou por último.*/
function extrairNucleoParaLoja_(bruto) {
  const linhas = String(bruto || '').replace(/\r/g, '').split('\n');
  let ultimoIndice = -1;
  for (let i = 0; i < linhas.length; i++) {
    if (DELIMITADOR_ENCAMINHAMENTO_RE.test(linhas[i])) ultimoIndice = i;
  }
  const inicio = ultimoIndice === -1 ? 0 : ultimoIndice + 1;
  return linhas.slice(inicio, inicio + 20).join('\n');
}

/** Volta o corpo de verdade da mensagem original: pula todas as camadas de
 * encaminhamento (não só a primeira) e o bloco de cabeçalho (De/From, Date,
 * Subject, To, Cc...) da última camada, até a primeira linha em branco. */
function extrairCorpoOriginal_(bruto) {
  const texto = String(bruto || '').replace(/\r/g, '');
  const linhas = texto.split('\n');
  let ultimoIndice = -1;
  for (let i = 0; i < linhas.length; i++) {
    if (DELIMITADOR_ENCAMINHAMENTO_RE.test(linhas[i])) ultimoIndice = i;
  }
  if (ultimoIndice === -1) {
    // Sem nenhuma camada de encaminhamento detectada: mantém o
    // comportamento antigo (compatibilidade com e-mails simples).
    return limparEncaminhamento(texto);
  }
  for (let j = ultimoIndice + 1; j < linhas.length; j++) {
    if (!linhas[j].trim()) {
      return linhas.slice(j + 1).join('\n').trim();
    }
  }
  return linhas.slice(ultimoIndice + 1).join('\n').trim();
}

function extrairNomeRemetente_(remetente) {
  const texto = String(remetente || '').trim();
  const match = texto.match(/^\s*(.*?)\s*<[^>]+>\s*$/);
  if (match) return match[1].trim();
  return texto.replace(/<[^>]+>/g, '').trim();
}

function limparNomeLoja_(loja) {
  return limparTexto(loja)
    .replace(/^(Loja\s+)?(Gerencia|Gerência)\s+/i, '')
    .trim();
}

function extrairBlocosDeLacre(corpo) {
  const linhas = String(corpo || '').replace(/\r/g, '').split('\n');
  const resultados = [];
  const vistos = {};
  let atual = null;
  // "Lacres: 14413 e 14414" (ou "14413, 14414 e 14415") — vários números na
  // mesma linha, sem descrição individual pra cada um. Diferente do formato
  // "lacre 19152: infraestrutura" (um por linha, com descrição), que é
  // tratado pelo inicioLacre logo abaixo.
  const listaLacres = /^\s*lacres?\s*[:#-]?\s*(\d{4,}(?:\s*(?:,|\be\b)\s*\d{4,})+)\s*\.?\s*$/i;
  // Lista de números "solta", numa linha própria, sem a palavra "lacre"
  // do lado — normalmente vem depois de uma linha de texto tipo "Lacres
  // contendo bags de bags:" que não bate com o padrão acima.
  const listaNumerosPura = /^\s*\d{4,}(?:\s*,\s*\d{4,})+\s*\.?\s*$/;
  const inicioLacre = /^\s*lacres?\s*[:#-]?\s*(\d{4,})\s*(?:[:\-–—]\s*)?(.*)$/i;
  const inicioNumero = /^\s*(\d{5,})\s*[-–—:]\s*(.+)$/i;
  const padraoSaudacao = /^(boa tarde|boa noite|bom dia|ol[aá]|prezad[oa]s?)[.,!]?\s*$/i;

  // Quando os lacres vêm numa lista solta (sem descrição individual), a
  // frase de texto livre logo ANTES da lista costuma descrever o conteúdo
  // geral (ex.: "Saindo da loja duas bags com devolução de defeitos...").
  // Guarda a última linha "de contexto" (não é lacre, não é continuação de
  // lacre, não é saudação) pra usar como descrição compartilhada nesse caso.
  let contexto = '';

  for (const linhaOriginal of linhas) {
    const linha = linhaOriginal.trim();
    if (!linha) continue;

    const matchLista = linha.match(listaLacres);
    if (matchLista) {
      if (atual) { finalizarLacre_(atual, resultados, vistos); atual = null; }
      const descricaoContexto = padraoSaudacao.test(contexto) ? '' : contexto;
      const numeros = matchLista[1].split(/,|\be\b/i).map(n => n.trim()).filter(Boolean);
      for (const num of numeros) {
        const codigo = limparTexto(num);
        if (codigo && !vistos[codigo]) {
          vistos[codigo] = true;
          resultados.push({ lacre: codigo, descricao: descricaoContexto });
        }
      }
      continue;
    }

    if (listaNumerosPura.test(linha)) {
      if (atual) { finalizarLacre_(atual, resultados, vistos); atual = null; }
      const descricaoContexto = padraoSaudacao.test(contexto) ? '' : contexto;
      const numeros = linha.replace(/\.\s*$/, '').split(',').map(n => n.trim()).filter(Boolean);
      for (const num of numeros) {
        const codigo = limparTexto(num);
        if (codigo && !vistos[codigo]) {
          vistos[codigo] = true;
          resultados.push({ lacre: codigo, descricao: descricaoContexto });
        }
      }
      continue;
    }

    let match = linha.match(inicioLacre);
    if (!match) match = linha.match(inicioNumero);

    if (match) {
      if (atual) finalizarLacre_(atual, resultados, vistos);
      atual = { lacre: match[1], partes: [] };
      if (match[2]) atual.partes.push(match[2]);
    } else if (atual) {
      if (/^(A devolu[cç][aã]o|A entrega|O recolhimento|Att\.?$|Atenciosamente|Abra[cç]os|Fico à disposi[cç][aã]o)/i.test(linha)) {
        finalizarLacre_(atual, resultados, vistos);
        atual = null;
        contexto = '';
      } else {
        atual.partes.push(linha);
      }
    } else {
      // Linha de texto livre, fora de qualquer bloco de lacre — vira o
      // contexto candidato pra descrição de uma próxima lista solta.
      contexto = linha;
    }
  }

  if (atual) finalizarLacre_(atual, resultados, vistos);
  return resultados;
}

function finalizarLacre_(atual, resultados, vistos) {
  const codigo = limparTexto(atual.lacre);
  if (!codigo || vistos[codigo]) return;
  vistos[codigo] = true;
  resultados.push({ lacre: codigo, descricao: limparTexto(atual.partes.join(' ')) });
}

function limparEncaminhamento(texto) {
  const linhas = String(texto || '').replace(/\r/g, '').split('\n');
  for (let i = 0; i < linhas.length; i++) {
    if (/^\s*De:\s*/i.test(linhas[i])) {
      const bloco = linhas.slice(i, i + 10).join('\n');
      if (/Date:\s*|Subject:\s*|To:\s*|Cc:\s*/i.test(bloco)) {
        for (let j = i; j < linhas.length; j++) {
          if (!linhas[j].trim()) return linhas.slice(j + 1).join('\n').trim();
        }
      }
    }
  }
  return String(texto || '').trim();
}

function primeiroGrupo(padroes, texto) {
  for (const regex of padroes) {
    const match = String(texto || '').match(regex);
    if (match) return (match[1] || '').trim();
  }
  return '';
}

function limparTexto(texto) {
  return String(texto || '').replace(/\s+/g, ' ').trim().replace(/[;,\.]+$/, '').trim();
}

function normalizarData(texto) {
  const partes = String(texto).split('/');
  if (partes.length !== 3) return '';
  let ano = partes[2];
  if (ano.length === 2) ano = '20' + ano;
  return ano + '-' + partes[1].padStart(2, '0') + '-' + partes[0].padStart(2, '0');
}
