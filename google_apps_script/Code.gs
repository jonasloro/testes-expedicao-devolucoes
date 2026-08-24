/**
 * Automação de pedidos de devolução via Gmail -> PostgreSQL.
 *
 * IMPORTANTE:
 * - Não fala com a API de produção do OutLog.
 * - Não deve ficar com credenciais no código.
 * - Usa o JDBC do Google Apps Script para gravar diretamente no PostgreSQL.
 * - As credenciais devem ficar em Script Properties.
 *
 * Script Properties necessárias:
 *   DB_URL   = jdbc:postgresql://HOST:5432/BANCO?sslmode=require
 *   DB_USER  = usuário do PostgreSQL
 *   DB_PASS  = senha do PostgreSQL
 *
 * O script procura mensagens novas/recorrentes do Gmail, evita duplicidade pelo
 * ID da mensagem e cria o pedido diretamente nas tabelas:
 *   pedidos_devolucao
 *   pedido_devolucao_lacres
 */

const CONFIG = {
  GMAIL_QUERY: 'newer_than:2d (subject:(devolução OR devolucao OR "nota de saída" OR "nota de saida") OR lacre)',
  MAX_THREADS: 50,
  LABEL_PROCESSADO: 'OutLog/Devoluções/Processado',
  LABEL_REVISAO: 'OutLog/Devoluções/Revisar',
};

function processarEmailsDevolucao() {
  const props = PropertiesService.getScriptProperties();
  const dbUrl = props.getProperty('DB_URL');
  const dbUser = props.getProperty('DB_USER');
  const dbPass = props.getProperty('DB_PASS');

  if (!dbUrl || !dbUser || !dbPass) {
    throw new Error('Configure DB_URL, DB_USER e DB_PASS nas Script Properties.');
  }

  const processado = GmailApp.getUserLabelByName(CONFIG.LABEL_PROCESSADO)
    || GmailApp.createLabel(CONFIG.LABEL_PROCESSADO);
  const revisar = GmailApp.getUserLabelByName(CONFIG.LABEL_REVISAO)
    || GmailApp.createLabel(CONFIG.LABEL_REVISAO);

  const threads = GmailApp.search(CONFIG.GMAIL_QUERY, 0, CONFIG.MAX_THREADS);
  let criados = 0;
  let ignorados = 0;
  let revisao = 0;

  const conn = Jdbc.getConnection(dbUrl, {
    user: dbUser,
    password: dbPass,
    useJDBCCompliantTimeZoneShift: false,
  });

  try {
    for (const thread of threads) {
      const messages = thread.getMessages();
      for (const message of messages) {
        const gmailId = message.getId();

        if (foiProcessado(conn, gmailId)) {
          ignorados++;
          processado.addToThread(thread);
          continue;
        }

        const assunto = message.getSubject() || '';
        const corpo = message.getPlainBody() || message.getBody() || '';
        const dados = analisarEmail(assunto, corpo);

        if (!dados.numeroNota || !dados.loja || dados.lacres.length === 0) {
          registrarEmailPendente(conn, gmailId, assunto, dados, message.getDate());
          revisar.addToThread(thread);
          revisao++;
          continue;
        }

        criarPedido(conn, gmailId, assunto, dados);
        processado.addToThread(thread);
        criados++;
      }
    }
  } finally {
    conn.close();
  }

  console.log(JSON.stringify({ criados, ignorados, revisao }));
}

function criarGatilho() {
  ScriptApp.newTrigger('processarEmailsDevolucao')
    .timeBased()
    .everyMinutes(5)
    .create();
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

function registrarEmailPendente(conn, gmailId, assunto, dados, dataMensagem) {
  // Não cria pedido incompleto. Apenas registra nos logs para o próximo ajuste.
  console.log(JSON.stringify({
    tipo: 'REVISAO',
    gmailId,
    assunto,
    numeroNota: dados.numeroNota,
    loja: dados.loja,
    lacres: dados.lacres.length,
    dataMensagem: dataMensagem ? dataMensagem.toISOString() : null,
  }));
}

function criarPedido(conn, gmailId, assunto, dados) {
  conn.setAutoCommit(false);
  try {
    const existente = conn.prepareStatement(
      'SELECT id FROM pedidos_devolucao WHERE numero_nota = ? AND loja = ? AND status <> ? ORDER BY id DESC LIMIT 1'
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
      console.log('Pedido já existente: ' + pedidoIdExistente);
      return pedidoIdExistente;
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
    else insert.setNull(3, Jdbc.JDBC_NULL);
    insert.setString(4, dados.transportadora || '');
    insert.setInt(5, dados.lacres.length);
    insert.setString(6, gmailId);
    insert.setString(7, assunto || '');
    insert.setString(8, dados.corpo || '');

    const created = insert.executeQuery();
    if (!created.next()) throw new Error('Não foi possível obter o ID do pedido criado.');
    const pedidoId = created.getLong(1);
    created.close();
    insert.close();

    const lacreStmt = conn.prepareStatement(
      `INSERT INTO pedido_devolucao_lacres (pedido_id, lacre, descricao)
       VALUES (?, ?, ?)
       ON CONFLICT (pedido_id, lacre) DO UPDATE SET descricao = EXCLUDED.descricao`
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
    return pedidoId;
  } catch (err) {
    conn.rollback();
    throw err;
  } finally {
    conn.setAutoCommit(true);
  }
}

function analisarEmail(assunto, texto) {
  const bruto = String(texto || '');
  const assuntoTexto = String(assunto || '');
  const corpo = limparEncaminhamento(bruto);
  const fonte = assuntoTexto + '\n' + bruto + '\n' + corpo;

  const numeroNota = primeiroGrupo([
    /(?:NOTA\s+DE\s+SA[IÍ]DA|NOTA|NF|N[ÚU]MERO\s+DA\s+NOTA)\s*[:#-]?\s*(\d+)\b/i,
    /\bSA[IÍ]DA\s+(\d+)\b/i,
  ], fonte);

  let loja = primeiroGrupo([
    /^\s*De:\s*(?:Loja\s+)?Ger[eê]ncia\s+(.+?)(?:\s*<[^>]+>)?\s*$/im,
    /^\s*De:\s*(?:Loja\s+)?(.+?)(?:\s*<[^>]+>)?\s*$/im,
  ], bruto.split('\n').slice(0, 18).join('\n'));
  loja = limparTexto(loja).replace(/^(Gerencia|Gerência)\s+/i, '').trim();

  let dataColeta = primeiroGrupo([
    /(?:na|em)\s+data\s+(?:de\s+)?(\d{1,2}\/\d{1,2}\/\d{2,4})/i,
    /\b(\d{1,2}\/\d{1,2}\/\d{2,4})\b/,
  ], corpo);
  if (dataColeta) dataColeta = normalizarData(dataColeta);

  const transportadora = limparTexto(primeiroGrupo([
    /recolhido\s+pela\s+transportadora\s+([^,\n.]+)/i,
    /transportadora\s*[:\-]\s*([^\n.]+)/i,
    /pela\s+transportadora\s+([^,\n.]+)/i,
  ], corpo));

  const lacres = extrairBlocosDeLacre(corpo);

  return {
    numeroNota,
    loja,
    dataColeta: dataColeta || null,
    transportadora,
    lacres,
    corpo,
  };
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
      if (atual) finalizarLacre(atual, resultados, vistos);
      atual = { lacre: match[1], partes: [] };
      if (match[2]) atual.partes.push(match[2]);
    } else if (atual) {
      // Frases de encerramento não pertencem ao último lacre.
      if (/^(A devolu[cç][aã]o|A entrega|O recolhimento|Att\.?$|Atenciosamente|Abra[cç]os|Fico à disposi[cç][aã]o)/i.test(linha)) {
        finalizarLacre(atual, resultados, vistos);
        atual = null;
      } else {
        atual.partes.push(linha);
      }
    }
  }

  if (atual) finalizarLacre(atual, resultados, vistos);
  return resultados;
}

function finalizarLacre(atual, resultados, vistos) {
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
    const m = String(texto || '').match(regex);
    if (m) return (m[1] || '').trim();
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
