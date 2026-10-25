/**
 * Classificação de glosas com IA (Claude) dentro do Google Sheets.
 *
 * Abas esperadas na planilha:
 *   - "glosas"   : saida/glosas_para_planilha.csv (glosa_id, convenio, item, codigo_motivo, texto_glosa, valor_glosado)
 *   - "gabarito" : dados/csv/glosas_gabarito.csv  (glosa_id, categoria_real) — só para medir a precisão
 *
 * O script adiciona à aba "glosas" as colunas:
 *   categoria_ia | recorrivel | confianca | justificativa_ia | correcao_humana
 *
 * Ciclo de melhoria: quando alguém do time preenche "correcao_humana" numa linha em que a IA errou,
 * esse exemplo passa a ser enviado no prompt das próximas classificações (few-shot).
 */

const MODELO = 'claude-haiku-5-5';        // modelo mais rápido e barato, bom para classificação
const TAMANHO_LOTE = 25;                  // glosas por chamada à API
const LIMITE_TEMPO_MS = 5 * 60 * 1000;    // Apps Script encerra execuções com 6 min
const MAX_EXEMPLOS_CORRIGIDOS = 15;

const CATEGORIAS = {
  PRECO_DIVERGENTE: 'Valor cobrado diferente do preço do contrato/tabela.',
  SEM_AUTORIZACAO: 'Falta autorização prévia, senha ou guia do convênio.',
  DUPLICIDADE: 'O mesmo item foi cobrado mais de uma vez.',
  PRAZO_EXPIRADO: 'A conta foi enviada depois do prazo contratual.',
  DOCUMENTACAO_INCOMPLETA: 'Falta ou está ilegível algum documento: laudo, relatório, prescrição, assinatura.',
  INCOMPATIBILIDADE_CLINICA: 'O item não é justificado pelo diagnóstico/quadro clínico, ou a quantidade é excessiva.',
};
const COLUNAS_IA = ['categoria_ia', 'recorrivel', 'confianca', 'justificativa_ia', 'correcao_humana'];


// ---------------------------------------------------------------- Menu
function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🤖 IA Glosas')
    .addItem('1. Configurar chave da API', 'configurarChave')
    .addItem('2. Classificar glosas pendentes', 'classificarGlosas')
    .addItem('3. Avaliar com o gabarito', 'avaliarComGabarito')
    .addItem('4. Gerar resumo para a liderança', 'gerarResumo')
    .addToUi();
}

function configurarChave() {
  const ui = SpreadsheetApp.getUi();
  const resp = ui.prompt('Chave da API da Anthropic', 'Cole sua chave (sk-ant-...).', ui.ButtonSet.OK_CANCEL);
  if (resp.getSelectedButton() !== ui.Button.OK) return;
  // A chave fica nas propriedades do script, nunca na planilha nem no código
  PropertiesService.getScriptProperties().setProperty('ANTHROPIC_API_KEY', resp.getResponseText().trim());
  ui.alert('Chave salva.');
}


// ---------------------------------------------------------------- Classificação
function classificarGlosas() {
  const inicio = Date.now();
  const aba = obterAba_('glosas');
  garantirColunas_(aba);
  const { cab, linhas } = lerTabela_(aba);
  const col = nome => cab.indexOf(nome);

  // Só classifica o que ainda não tem categoria
  const pendentes = [];
  linhas.forEach((l, i) => {
    if (!l[col('categoria_ia')]) pendentes.push({ linha: i + 2, dados: l });
  });
  if (!pendentes.length) return avisar_('Nenhuma glosa pendente.');

  const exemplos = exemplosCorrigidos_(cab, linhas);
  let feitas = 0;

  for (let i = 0; i < pendentes.length; i += TAMANHO_LOTE) {
    if (Date.now() - inicio > LIMITE_TEMPO_MS) {
      return avisar_(`${feitas} glosas classificadas. Tempo limite atingido: rode de novo para continuar.`);
    }
    const lote = pendentes.slice(i, i + TAMANHO_LOTE);
    const entrada = lote.map(p => ({
      id: String(p.dados[col('glosa_id')]),
      convenio: p.dados[col('convenio')],
      item: p.dados[col('item')],
      codigo: p.dados[col('codigo_motivo')],
      texto: p.dados[col('texto_glosa')],
    }));

    const respostas = chamarClaude_(promptSistema_(exemplos), JSON.stringify(entrada, null, 1));
    const porId = {};
    respostas.forEach(r => porId[String(r.id)] = r);

    lote.forEach(p => {
      const r = porId[String(p.dados[col('glosa_id')])];
      if (!r) return;  // fica pendente e entra na próxima execução
      const valores = [[r.categoria, r.recorrivel, r.confianca, r.justificativa]];
      aba.getRange(p.linha, col('categoria_ia') + 1, 1, 4).setValues(valores);
      feitas++;
    });
    SpreadsheetApp.flush();
  }
  avisar_(`${feitas} glosas classificadas.`);
}

function promptSistema_(exemplos) {
  const lista = Object.entries(CATEGORIAS).map(([k, v]) => `- ${k}: ${v}`).join('\n');
  let texto =
`Você é analista de faturamento hospitalar e classifica glosas (valores que o convênio se recusou a pagar).

Categorias possíveis:
${lista}

Para cada glosa, responda:
- categoria: exatamente uma das categorias acima
- recorrivel: "SIM" se o hospital provavelmente consegue reverter com recurso (ex.: enviar documento faltante),
  "NAO" se o erro foi do hospital e não há o que contestar (ex.: duplicidade real, prazo perdido),
  "VERIFICAR" se depende de conferir algo (contrato, prontuário, autorização de urgência)
- confianca: número de 0 a 1
- justificativa: até 15 palavras, em português

O campo "codigo" é o código de motivo da operadora; "G99" significa "outros" e o motivo está só no texto.
Responda APENAS com um array JSON: [{"id": "...", "categoria": "...", "recorrivel": "...", "confianca": 0.9, "justificativa": "..."}]`;

  if (exemplos.length) {
    texto += '\n\nExemplos corrigidos pelo time de faturamento (siga este critério):\n' +
      exemplos.map(e => `- "${e.texto}" => ${e.categoria}`).join('\n');
  }
  return texto;
}

function exemplosCorrigidos_(cab, linhas) {
  const ia = cab.indexOf('categoria_ia'), cor = cab.indexOf('correcao_humana'), txt = cab.indexOf('texto_glosa');
  return linhas
    .filter(l => l[cor] && l[cor] !== l[ia])
    .slice(-MAX_EXEMPLOS_CORRIGIDOS)
    .map(l => ({ texto: l[txt], categoria: l[cor] }));
}


// ---------------------------------------------------------------- Avaliação
function avaliarComGabarito() {
  const glosas = lerTabela_(obterAba_('glosas'));
  const gab = lerTabela_(obterAba_('gabarito'));
  const real = {};
  gab.linhas.forEach(l => real[String(l[0])] = l[1]);

  const cId = glosas.cab.indexOf('glosa_id'), cIa = glosas.cab.indexOf('categoria_ia');
  const cTxt = glosas.cab.indexOf('texto_glosa'), cCod = glosas.cab.indexOf('codigo_motivo');
  const stats = {};
  Object.keys(CATEGORIAS).forEach(k => stats[k] = { real: 0, previsto: 0, acertos: 0 });
  const erros = [];
  let total = 0, acertos = 0, acertosG99 = 0, totalG99 = 0;

  glosas.linhas.forEach(l => {
    const prev = l[cIa], verd = real[String(l[cId])];
    if (!prev || !verd) return;
    total++;
    const ok = prev === verd;
    if (ok) acertos++;
    if (l[cCod] === 'G99') { totalG99++; if (ok) acertosG99++; }
    if (stats[verd]) { stats[verd].real++; if (ok) stats[verd].acertos++; }
    if (stats[prev]) stats[prev].previsto++;
    if (!ok) erros.push([l[cId], l[cTxt], prev, verd]);
  });
  if (!total) return avisar_('Classifique as glosas antes de avaliar.');

  const saida = obterAba_('avaliacao', true);
  saida.clear();
  const pct = (a, b) => b ? a / b : '';
  const resumo = [
    ['Métrica', 'Valor'],
    ['Glosas avaliadas', total],
    ['Acurácia geral', pct(acertos, total)],
    ['Acurácia nas glosas G99 (só texto livre)', pct(acertosG99, totalG99)],
  ];
  saida.getRange(1, 1, resumo.length, 2).setValues(resumo);
  saida.getRange(3, 2, 2, 1).setNumberFormat('0.0%');

  const porCat = [['Categoria', 'Glosas reais', 'Precisão', 'Recall']];
  Object.entries(stats).forEach(([k, s]) =>
    porCat.push([k, s.real, pct(s.acertos, s.previsto), pct(s.acertos, s.real)]));
  saida.getRange(7, 1, porCat.length, 4).setValues(porCat);
  saida.getRange(8, 3, porCat.length - 1, 2).setNumberFormat('0.0%');

  const linhaErros = 9 + porCat.length;
  saida.getRange(linhaErros, 1).setValue('Erros da IA (preencha "correcao_humana" na aba glosas para ensinar o modelo)');
  if (erros.length) {
    saida.getRange(linhaErros + 1, 1, erros.length + 1, 4)
      .setValues([['glosa_id', 'texto', 'IA disse', 'Correto']].concat(erros));
  }
  [1, 7, linhaErros + 1].forEach(r => saida.getRange(r, 1, 1, 4).setFontWeight('bold'));
  avisar_(`Acurácia: ${(100 * acertos / total).toFixed(1)}% em ${total} glosas.`);
}


// ---------------------------------------------------------------- Resumo executivo
function gerarResumo() {
  const { cab, linhas } = lerTabela_(obterAba_('glosas'));
  const c = n => cab.indexOf(n);
  const agg = {};
  let total = 0;
  linhas.forEach(l => {
    const cat = l[c('correcao_humana')] || l[c('categoria_ia')];
    if (!cat) return;
    const v = Number(l[c('valor_glosado')]) || 0;
    agg[cat] = agg[cat] || { qtd: 0, valor: 0, recorrivel: 0 };
    agg[cat].qtd++; agg[cat].valor += v; total += v;
    if (l[c('recorrivel')] === 'SIM') agg[cat].recorrivel += v;
  });
  if (!total) return avisar_('Classifique as glosas antes de gerar o resumo.');

  const numeros = Object.entries(agg)
    .sort((a, b) => b[1].valor - a[1].valor)
    .map(([k, a]) => `${k}: ${a.qtd} glosas, R$ ${a.valor.toFixed(2)}, recorrível R$ ${a.recorrivel.toFixed(2)}`)
    .join('\n');

  const sistema = 'Você escreve para a diretoria financeira de um hospital. Seja direto, use números e ' +
    'português claro, sem jargão técnico de TI.';
  const pedido = `Glosas do período (total R$ ${total.toFixed(2)}), por categoria:\n${numeros}\n\n` +
    'Escreva um resumo executivo com: (1) uma frase com o tamanho do problema, (2) as 2 causas principais, ' +
    '(3) quanto dá para recuperar com recurso, (4) 3 ações recomendadas. Máximo de 8 linhas. Texto puro, sem JSON.';
  const texto = chamarClaude_(sistema, pedido, false);

  const aba = obterAba_('resumo', true);
  aba.clear();
  aba.getRange('A1').setValue('Resumo executivo gerado por IA em ' + new Date().toLocaleString('pt-BR')).setFontWeight('bold');
  aba.getRange('A3').setValue(texto).setWrap(true);
  aba.setColumnWidth(1, 700);
  avisar_('Resumo criado na aba "resumo".');
}


// ---------------------------------------------------------------- Utilitários
function chamarClaude_(sistema, conteudo, esperaJson = true) {
  const chave = PropertiesService.getScriptProperties().getProperty('ANTHROPIC_API_KEY');
  if (!chave) throw new Error('Configure a chave da API no menu "🤖 IA Glosas".');

  const opcoes = {
    method: 'post',
    contentType: 'application/json',
    headers: { 'x-api-key': chave, 'anthropic-version': '2023-06-01' },
    payload: JSON.stringify({
      model: MODELO,
      max_tokens: 16000,                  // o raciocínio interno do modelo também conta neste limite
      output_config: { effort: 'low' },   // classificação é tarefa simples: menos raciocínio, mais rápido
      system: sistema,
      messages: [{ role: 'user', content: conteudo }],
    }),
    muteHttpExceptions: true,
  };

  for (let tentativa = 1; tentativa <= 4; tentativa++) {
    const resp = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', opcoes);
    const status = resp.getResponseCode();
    if (status === 200) {
      // A resposta pode trazer blocos de raciocínio ("thinking") antes do texto: juntamos só os de texto
      const corpo = JSON.parse(resp.getContentText());
      const texto = (corpo.content || [])
        .filter(b => b.type === 'text')
        .map(b => b.text)
        .join('')
        .trim();
      if (!texto) {
        throw new Error(`Resposta sem texto (stop_reason: ${corpo.stop_reason}). Tente de novo.`);
      }
      if (!esperaJson) return texto;
      const json = texto.slice(texto.indexOf('['), texto.lastIndexOf(']') + 1);  // ignora texto extra
      return JSON.parse(json);
    }
    if (status === 429 || status >= 500) {          // limite de taxa ou sobrecarga: espera e tenta de novo
      Utilities.sleep(2000 * tentativa);
      continue;
    }
    throw new Error(`Erro ${status} da API: ${resp.getContentText()}`);
  }
  throw new Error('A API não respondeu após 4 tentativas.');
}

function obterAba_(nome, criar = false) {
  const planilha = SpreadsheetApp.getActive();
  let aba = planilha.getSheetByName(nome);
  if (!aba && criar) aba = planilha.insertSheet(nome);
  if (!aba) throw new Error(`Aba "${nome}" não encontrada.`);
  return aba;
}

function lerTabela_(aba) {
  const valores = aba.getDataRange().getValues();
  return { cab: valores[0].map(String), linhas: valores.slice(1) };
}

function garantirColunas_(aba) {
  const cab = aba.getRange(1, 1, 1, aba.getLastColumn()).getValues()[0];
  const faltando = COLUNAS_IA.filter(c => cab.indexOf(c) === -1);
  if (faltando.length) {
    aba.getRange(1, cab.length + 1, 1, faltando.length).setValues([faltando]).setFontWeight('bold');
  }
}

function avisar_(msg) {
  SpreadsheetApp.getActive().toast(msg, 'IA Glosas', 8);
}
