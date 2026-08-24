/**
 * AUTOMACAO DE PEDIDOS DE DEVOLUCAO
 *
 * Arquitetura:
 *   Gmail -> Google Apps Script -> PostgreSQL -> OutLog
 *
 * Este script fica FORA do OutLog e nao usa a API de producao.
 * O destino do banco e definido apenas por Script Properties.
 *
 * Propriedades obrigatorias:
 *   DB_URL
 *   DB_USER
 *   DB_PASS
 *
 * O script:
 * - procura e-mails de devolucao;
 * - interpreta NF, loja, data, transportadora e lacres;
 * - considera volumes = quantidade de lacres;
 * - cria o pedido com status PENDENTE;
 * - evita duplicidade pelo ID da mensagem + nota/loja;
 * - nao grava o corpo completo do e-mail no banco;
 * - marca no Gmail o que foi processado ou precisa de revisao;
 * - executa no maximo uma instancia por vez.
 */

const CONFIG = Object.freeze({
  GMAIL_QUERY:
    'newer_than:3d (subject:(devolucao OR "devolução" OR "nota de saida" OR "nota de saída" OR "NF") OR lacre)',
  MAX_THREADS: 50,
  LABEL_PROCESSADO: 'OutLog/Devoluções/Processado',
  LABEL_REVISAO: 'OutLog/Devoluções/Revisar',
  FUNCAO_GATILHO: 'processarEmailsDevolucao',
  INTERVALO_MINUTOS: 5,
});

function obterConfiguracaoBanco_() {
  const props = PropertiesService.getScriptProperties();
  const cfg = {
    dbUrl: (props.getProperty('DB_URL') || '').trim(),
    dbUser: (props.getProperty('DB_USER') || '').trim(),
    dbPass: props.getProperty('DB_PASS') || '',
  };

  if (!cfg.dbUrl || !cfg.dbUser || !cfg.dbPass) {
    throw new Error(
      'Configure DB_URL, DB_USER e DB_PASS em Project Settings > Script properties.'
    );
  }

  return cfg;
}

function abrirConexaoBanco_() {
  const cfg = obterConfiguracaoBanco_();
  return Jdbc.getConnection(cfg.dbUrl, cfg.dbUser, cfg.dbPass);
}

/**
 * Teste seguro: abre a conexao e executa SELECT 1.
 * Nao grava nem altera dados.
 */
function testarConexaoBanco() {
  const conn = abrirConexaoBanco_();
  try {
    const stmt = conn.createStatement();
    const rs = stmt.executeQuery('SELECT 1');
    if (!rs.next()) throw new Error('O banco nao retornou resposta.');
    console.log('Conexao com PostgreSQL OK.');
    rs.close();
    stmt.close();
  } finally {
    conn.close();
  }
}

/**
 * Processa os e-mails automaticamente.
 * Use manualmente uma vez para autorizar o projeto e validar o fluxo.
 */
function processarEmailsDevolucao() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(1000)) {
    console.log('Outra execucao ja esta em andamento. Esta foi ignorada.');
    return;
  }

  let conn = null;
  try {
    const processado = obterOuCriarLabel_(CONFIG.LABEL_PROCESSADO);
    const revisar = obterOuCriarLabel_(CONFIG.LABEL_REVISAO);
    const threads = GmailApp.search(CONFIG.GMAIL_QUERY, 0, CONFIG.MAX_THREADS);

    let criados = 0;
    let existentes = 0;
    let revisao = 0;
    let ignorados = 0;

    conn = abrirConexaoBanco_();

    for (const thread of threads) {
      const labels = thread.getLabels().map(label => label.getName());
      const jaEmRevisao = labels.indexOf(CONFIG.LABEL_REVISAO) >= 0;
      const jaProcessado = labels.indexOf(CONFIG.LABEL_PROCESSADO) >= 0;

      if (jaEmRevisao || jaProcessado) {
        ignorados++;
        continue;
      }

      for (const message of thread.getMessages()) {
        const gmailId = message.getId();

        if (foiProcessado(conn, gmailId)) {
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

        const resultado = criarPedido(conn, gmailId, assunto, dados);
        processado.addToThread(thread);

        if (resultado.criado) criados++;
        else existentes++;
      }
    }

    console.log(JSON.stringify({ criados, existentes, revisao, ignorados }));
  } finally {
    if (conn) conn.close();
    lock.releaseLock();
  }
}

function obterOuCriarLabel_(nome) {
  return GmailApp.getUserLabelByName(nome) || GmailApp.createLabel(nome);
}

/**
 * Remove gatilhos antigos desta mesma funcao e cria apenas um novo.
 */
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

  console.log('Gatilho criado para rodar a cada ' + CONFIG.INTERVALO_MINUTOS + ' minutos.');
}

function foiProcessado(conn, gmailId) {
  const stmt = conn.prepareStatement(
    'SELECT id FROM pedidos_devolucao WHERE origem_email_id = ? LIMIT 1'
  );
  stmt.setString(1, gmailId);
  const rs = stmt.executeQuery();
  const encontrado = rs.next();
  rs.close();
  stmt.close();
  return encontrado;
}

function registrarEmailPendente_(gmailId, assunto, dados, dataMensagem) {
  console.log(JSON.stringify({
    tipo: 'REVISAO',
    gmailId: gmailId,
    assunto: assunto,
    numeroNota: dados.numeroNota,
    loja: dados.loja,
    lacres: dados.lacres.length,
    dataMensagem: dataMensagem ? dataMensagem.toISOString() : null,
  }));
}

function criarPedido(conn, gmailId, assunto, dados) {
  conn.setAutoCommit(false);
  try {
    // Primeira trava contra duplicidade: mesma mensagem do Gmail.
    const porMensagem = conn.prepareStatement(
      'SELECT id FROM pedidos_devolucao WHERE origem_email_id = ? LIMIT 1'
    );
    porMensagem.setString(1, gmailId);
    const rsMensagem = porMensagem.executeQuery();
    if (rsMensagem.next()) {
      const idExistente = rsMensagem.getLong(1);
      rsMensagem.close();
      porMensagem.close();
      conn.commit();
      return { id: idExistente, criado: false };
    }
    rsMensagem.close();
    porMensagem.close();

    // Segunda trava: mesma NF na mesma loja, desde que nao esteja cancelada.
    const existente = conn.prepareStatement(
      `SELECT id FROM pedidos_devolucao
        WHERE numero_nota = ? AND loja = ? AND status <> ?
        ORDER BY id DESC LIMIT 1`
    );
    existente.setString(1, dados.numeroNota);
    existente.setString(2, dados.loja);
    existente.setString(3, 'CANCELADO');
    const rs = existente.executeQuery();

    if (rs.next()) {
      const pedidoIdExistente = rs.getLong(1);
      rs.close();
      existente.close();
      conn.commit();
      return { id: pedidoIdExistente, criado: false };
    }

    rs.close();
    existente.close();

    const insert = conn.prepareStatement(
      `INSERT INTO pedidos_devolucao
       (numero_nota, loja, data_coleta, transportadora, volumes, status,
        origem_email_id, assunto_email, observacao)
       VALUES (?, ?, ?, ?, ?, 'PENDENTE', ?, ?, ?)
       RETURNING id`
    );

    insert.setString(1, dados.numeroNota);
    insert.setString(2, dados.loja);
    if (dados.dataColeta) insert.setString(3, dados.dataColeta);
    else insert.setNull(3, 91); // java.sql.Types.DATE
    insert.setString(4, dados.transportadora || '');
    insert.setInt(5, dados.lacres.length);
    insert.setString(6, gmailId);
    insert.setString(7, assunto || '');
    insert.setString(8, montarObservacaoCompacta_(dados));

    const created = insert.executeQuery();
    if (!created.next()) {
      throw new Error('Nao foi possivel obter o ID do pedido criado.');
    }

    const pedidoId = created.getLong(1);
    created.close();
    insert.close();

    const lacreStmt = conn.prepareStatement(
      `INSERT INTO pedido_devolucao_lacres (pedido_id, lacre, descricao)
       VALUES (?, ?, ?)
       ON CONFLICT (pedido_id, lacre) DO NOTHING`
    );

    for (const lacre of dados.lacres) {
      lacreStmt.setLong(1, pedidoId);
      lacreStmt.setString(2, lacre.lacre);
      lacreStmt.setString(3, lacre.descricao || '');
      lacreStmt.addBatch();
    }

    lacreStmt.executeBatch();
    lacreStmt.close();

    conn.commit();
    console.log('Pedido criado: ' + pedidoId);
    return { id: pedidoId, criado: true };
  } catch (err) {
    conn.rollback();
    throw err;
  } finally {
    conn.setAutoCommit(true);
  }
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

function analisarEmail(assunto, texto, remetente) {
  const bruto = String(texto || '');
  const assuntoTexto = String(assunto || '');
  const remetenteTexto = String(remetente || '');
  const corpo = limparEncaminhamento(bruto);
  const fonte = assuntoTexto + '\n' + bruto + '\n' + corpo;

  const numeroNota = primeiroGrupo([
    /(?:NOTA\s+DE\s+SA[IÍ]DA|NOTA|NF|N[ÚU]MERO\s+DA\s+NOTA)\s*[:#-]?\s*(\d+)\b/i,
    /\bDEVOLU(?:C|Ç)[AÃ]O\s+NF\s*(\d+)\b/i,
    /\bSA[IÍ]DA\s+(\d+)\b/i,
  ], fonte);

  let loja = primeiroGrupo([
    /^\s*De:\s*(?:Loja\s+)?Ger[eê]ncia\s+(.+?)(?:\s*<[^>]+>)?\s*$/im,
    /^\s*De:\s*(?:Loja\s+)?(.+?)(?:\s*<[^>]+>)?\s*$/im,
  ], bruto.split('\n').slice(0, 20).join('\n'));

  if (!loja) loja = extrairNomeRemetente_(remetenteTexto);
  loja = limparNomeLoja_(loja);

  let dataColeta = primeiroGrupo([
    /(?:na|em)\s+data\s+(?:de\s+)?(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
    /(?:saiu|coleta|recolhimento|retirada)[^\n]{0,80}(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
  ], corpo);
  if (dataColeta) dataColeta = normalizarData(dataColeta);

  const transportadora = limparTexto(
    primeiroGrupo([
      /recolhido\s+pela\s+transportadora\s+([^,\n.]+)/i,
      /transportadora\s*[:\-]\s*([^\n.]+)/i,
      /pela\s+transportadora\s+([^,\n.]+)/i,
    ], corpo)
  );

  return {
    numeroNota: numeroNota,
    loja: loja,
    dataColeta: dataColeta || null,
    transportadora: transportadora,
    lacres: extrairBlocosDeLacre(corpo),
    corpo: corpo,
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
  resultados.push({
    lacre: codigo,
    descricao: limparTexto(atual.partes.join(' ')),
  });
}

function limparEncaminhamento(texto) {
  const linhas = String(texto || '').replace(/\r/g, '').split('\n');

  for (let i = 0; i < linhas.length; i++) {
    if (!/^\s*De:\s*/i.test(linhas[i])) continue;

    const bloco = linhas.slice(i, i + 12).join('\n');
    if (!/Date:\s*|Subject:\s*|To:\s*|Cc:\s*/i.test(bloco)) continue;

    for (let j = i; j < linhas.length; j++) {
      if (!linhas[j].trim()) {
        return linhas.slice(j + 1).join('\n').trim();
      }
    }
  }

  return String(texto || '').trim();
}

function primeiroGrupo(padroes, texto) {
  for (const regex of padroes) {
    const m = String(texto || '').match(regex);
    if (m) return (m[1] || '').trim();
  }
  return '';
}

function limparTexto(texto) {
  return String(texto || '')
    .replace(/\s+/g, ' ')
    .trim()
    .replace(/[;,\.]+$/, '')
    .trim();
}

function normalizarData(texto) {
  const partes = String(texto).split('/');
  if (partes.length !== 3) return '';

  let ano = partes[2];
  if (ano.length === 2) ano = '20' + ano;

  return (
    ano +
    '-' +
    partes[1].padStart(2, '0') +
    '-' +
    partes[0].padStart(2, '0')
  );
}
