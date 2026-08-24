/**
 * AUTOMACAO DE PEDIDOS DE DEVOLUCAO
 *
 * Gmail -> Google Apps Script -> Neon Auth -> Neon Data API -> PostgreSQL -> OutLog
 *
 * Este script fica FORA do OutLog e nao usa a API de producao.
 * Nao usa JDBC/PostgreSQL direto.
 * O Data API e acessado por HTTPS com JWT anonimo renovado automaticamente.
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
  GMAIL_QUERY:
    'newer_than:3d (subject:(devolucao OR "devolução" OR "nota de saida" OR "nota de saída" OR "NF") OR lacre)',
  MAX_THREADS: 50,
  LABEL_PROCESSADO: 'OutLog/Devoluções/Processado',
  LABEL_REVISAO: 'OutLog/Devoluções/Revisar',
  FUNCAO_GATILHO: 'processarEmailsDevolucao',
  INTERVALO_MINUTOS: 5,
  TABELA_PEDIDOS: 'pedidos_devolucao',
  TABELA_LACRES: 'pedido_devolucao_lacres',
  TOKEN_CACHE_SECONDS: 3000,
});

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
    method: 'post',
    contentType: 'application/json',
    payload: '{}',
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
    (data.data && (data.data.token || data.data.access_token));

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

  // Se o token expirou, limpa o cache e tenta uma vez com outro token.
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

/** Teste seguro: pede JWT anonimo e consulta a Data API. Nao grava dados. */
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
  console.log('JWT anonimo obtido com sucesso. Tamanho: ' + token.length);
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
        ignorados++;
        continue;
      }

      for (const message of thread.getMessages()) {
        const gmailId = message.getId();

        if (foiProcessado_(gmailId)) {
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

        const resultado = criarPedido_(gmailId, assunto, dados);
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

function criarPedido_(gmailId, assunto, dados) {
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
  const corpo = limparEncaminhamento(bruto);
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
      /^\s*De:\s*(?:Loja\s+)?Ger[eê]ncia\s+(.+?)(?:\s*<[^>]+>)?\s*$/im,
      /^\s*De:\s*(?:Loja\s+)?(.+?)(?:\s*<[^>]+>)?\s*$/im,
    ],
    bruto.split('\n').slice(0, 20).join('\n')
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

  return {
    numeroNota,
    loja,
    dataColeta: dataColeta || null,
    transportadora,
    lacres: extrairBlocosDeLacre(corpo),
    corpo,
  };
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
  const inicioLacre = /^\s*lacres?\s*[:#-]?\s*(\d{4,})\s*(?:[:\-–—]\s*)?(.*)$/i;
  const inicioNumero = /^\s*(\d{5,})\s*[-–—:]\s*(.+)$/i;

  for (const linhaOriginal of linhas) {
    const linha = linhaOriginal.trim();
    if (!linha) continue;

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
      } else {
        atual.partes.push(linha);
      }
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
