"""
Gera um dashboard HTML interativo (Plotly) com os indicadores de glosa.

Uso:
    python scripts/dashboard.py        # cria saida/dashboard.html (abra no navegador)
"""

import json

import alertas as mod_alertas
import db


def tabela_html(df, colunas, formatos=None, limite=12):
    formatos = formatos or {}
    cab = "".join(f"<th>{titulo}</th>" for titulo in colunas.values())
    corpo = []
    for _, linha in df.head(limite).iterrows():
        celulas = []
        for col in colunas:
            v = linha[col]
            fmt = formatos.get(col)
            texto = fmt(v) if fmt else v
            classe = ' class="num"' if fmt else ""
            celulas.append(f"<td{classe}>{texto}</td>")
        corpo.append("<tr>" + "".join(celulas) + "</tr>")
    return f"<table><thead><tr>{cab}</tr></thead><tbody>{''.join(corpo)}</tbody></table>"


def main():
    brl, pct = mod_alertas.brl, mod_alertas.pct
    kpis = db.consultar("kpis").iloc[0]
    funil = db.consultar("funil")
    evitavel = db.consultar("glosa_evitavel")
    convenio = db.consultar("glosa_por_convenio")
    mensal = db.consultar("evolucao_mensal")
    prazo = db.consultar("prazo_por_convenio")
    pend = db.consultar("pendencias_pre_envio")
    pend_det = db.consultar("pendencias_pre_envio_detalhe")
    paradas = db.consultar("contas_paradas")
    alertas = mod_alertas.gerar_alertas()

    pct_evitavel = 100 - float(
        evitavel.loc[evitavel.causa == "NAO_DETECTAVEL_POR_REGRA", "pct_valor"].sum())
    nomes_causa = {
        "SEM_AUTORIZACAO": "Sem autorização", "DUPLICIDADE": "Duplicidade",
        "PRECO_DIVERGENTE": "Preço fora do contrato", "PRAZO_EXPIRADO": "Prazo expirado",
        "NAO_DETECTAVEL_POR_REGRA": "Não detectável por regra",
    }

    dados = {
        "funil": {"etapa": funil.etapa.tolist(), "qtd": funil.qtd.astype(int).tolist()},
        "evitavel": {"causa": [nomes_causa.get(c, c) for c in evitavel.causa],
                     "valor": evitavel.valor.tolist(),
                     "evitavel": [c != "NAO_DETECTAVEL_POR_REGRA" for c in evitavel.causa]},
        "convenio": {"nome": convenio.convenio.tolist(), "taxa": convenio.taxa_glosa_pct.tolist(),
                     "media": float(kpis.taxa_glosa_pct)},
        "mensal": {"mes": mensal.mes.tolist(), "faturado": mensal.faturado.tolist(),
                   "glosado": mensal.glosado.tolist(), "taxa": mensal.taxa_glosa_pct.tolist()},
        "prazo": {"nome": prazo.convenio.tolist(), "pct": prazo.pct_fora_do_prazo.tolist()},
    }

    tiles = [
        ("Faturado (contas pagas)", brl(kpis.faturado), f"{int(kpis.contas_pagas)} contas"),
        ("Glosado", brl(kpis.glosado), f"taxa de glosa {pct(kpis.taxa_glosa_pct)}"),
        ("Glosa evitável", f"{pct_evitavel:.0f}%", "do valor glosado era detectável antes do envio"),
        ("Em risco agora", brl(pend.valor_em_risco.sum()),
         f"{pend_det.conta_id.nunique()} contas não enviadas com erro"),
    ]
    tiles_html = "".join(
        f'<div class="card tile"><div class="tile-label">{t}</div><div class="tile-value">{v}</div>'
        f'<div class="tile-sub">{s}</div></div>' for t, v, s in tiles)

    icones = {"CRÍTICO": "⛔", "ALTO": "⚠️", "MÉDIO": "●", "INFO": "ℹ️"}
    alertas_html = "".join(
        f'<li class="alerta nivel-{a["nivel"].lower().replace("í", "i").replace("é", "e")}">'
        f'<span class="badge">{icones[a["nivel"]]} {a["nivel"]}</span>'
        f'<div><strong>{a["titulo"]}</strong><br><span class="muted">{a["detalhe"]}</span></div></li>'
        for a in alertas)

    nomes_erro = {k: v for k, v in nomes_causa.items()}
    pend_det = pend_det.assign(tipo_erro=pend_det.tipo_erro.map(nomes_erro))
    tabela_pend = tabela_html(
        pend_det,
        {"conta_id": "Conta", "convenio": "Convênio", "tipo_erro": "Erro", "item": "Item",
         "valor_em_risco": "Em risco"},
        {"valor_em_risco": brl})
    tabela_paradas = tabela_html(
        paradas,
        {"conta_id": "Conta", "convenio": "Convênio", "tipo": "Tipo", "dias_parada": "Dias parada",
         "dias_restantes_prazo": "Dias até o prazo", "valor_cobrado": "Valor"},
        {"valor_cobrado": brl, "dias_parada": lambda v: int(v),
         "dias_restantes_prazo": lambda v: int(v)})

    html = MODELO.replace("{{DATA}}", db.DATA_REFERENCIA) \
        .replace("{{TILES}}", tiles_html) \
        .replace("{{ALERTAS}}", alertas_html or '<li class="muted">Nenhum alerta.</li>') \
        .replace("{{TABELA_PEND}}", tabela_pend) \
        .replace("{{TABELA_PARADAS}}", tabela_paradas) \
        .replace("{{DADOS}}", json.dumps(dados, ensure_ascii=False))

    saida = db.RAIZ / "saida"
    saida.mkdir(exist_ok=True)
    (saida / "dashboard.html").write_text(html, encoding="utf-8")
    print(f"Dashboard salvo em {saida / 'dashboard.html'}")


MODELO = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Auditoria de Glosas</title>
<!-- Plotly vem da internet (CDN). Se o primeiro endereço falhar, tenta o segundo. -->
<script src="https://cdn.jsdelivr.net/npm/plotly.js-dist-min@2.35.2/plotly.min.js"></script>
<script>window.Plotly || document.write('<script src="https://cdnjs.cloudflare.com/ajax/libs/plotly.js/2.35.2/plotly.min.js"><\/script>')</script>
<style>
  :root {
    --page: #f9f9f7; --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
    --s1: #2a78d6; --s2: #eb6834; --neutral: #c3c2b7;
    --critical: #d03b3b; --serious: #ec835a; --warning: #fab219; --info: #2a78d6;
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7;
      --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
      --s1: #3987e5; --s2: #d95926; --neutral: #52514e;
    }
  }
  :root[data-theme="dark"] {
    --page: #0d0d0d; --surface: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --neutral: #52514e;
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--page); color: var(--ink);
         font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
  main { max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }
  h1 { font-size: 22px; margin: 0 0 4px; }
  h2 { font-size: 15px; margin: 0 0 8px; }
  .muted { color: var(--ink-2); }
  .grid { display: grid; gap: 16px; }
  .tiles { grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); margin: 20px 0; }
  .cols { grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px;
          padding: 16px; min-width: 0; }
  .tile-label { color: var(--ink-2); font-size: 13px; }
  .tile-value { font-size: 28px; font-weight: 650; margin: 2px 0; }
  .tile-sub { color: var(--muted); font-size: 12.5px; }
  .chart { height: 300px; }
  ul.alertas { list-style: none; padding: 0; margin: 0; display: grid; gap: 8px; }
  .alerta { display: flex; gap: 12px; align-items: flex-start; padding: 10px 12px;
            border-radius: 8px; border: 1px solid var(--border); border-left: 4px solid var(--info); }
  .nivel-critico { border-left-color: var(--critical); }
  .nivel-alto { border-left-color: var(--serious); }
  .nivel-medio { border-left-color: var(--warning); }
  .badge { font-size: 12px; font-weight: 600; white-space: nowrap; min-width: 92px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th { text-align: left; color: var(--ink-2); font-weight: 600; border-bottom: 1px solid var(--axis);
       padding: 6px 8px; }
  td { padding: 6px 8px; border-bottom: 1px solid var(--grid); }
  td.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
  .scroll { overflow-x: auto; }
  footer { margin-top: 24px; color: var(--muted); font-size: 12px; }
  @media (max-width: 520px) { .cols { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<main>
  <h1>Auditoria de Glosas | Ciclo da Receita</h1>
  <div class="muted">Hospital fictício · atendimentos de abr–out/2026 · referência {{DATA}}</div>

  <div class="grid tiles">{{TILES}}</div>

  <section class="card" style="margin-bottom:16px">
    <h2>Alertas para hoje</h2>
    <ul class="alertas">{{ALERTAS}}</ul>
  </section>

  <div class="grid cols">
    <section class="card"><h2>Quanto da glosa era evitável?</h2>
      <div class="muted">Valor glosado por causa (R$). Azul = detectável por regra antes do envio.</div>
      <div id="g-evitavel" class="chart"></div></section>
    <section class="card"><h2>Funil do faturamento</h2>
      <div class="muted">Quantidade de contas em cada etapa</div>
      <div id="g-funil" class="chart"></div></section>
    <section class="card"><h2>Taxa de glosa por convênio</h2>
      <div class="muted">% do valor cobrado que foi glosado · linha tracejada = média</div>
      <div id="g-convenio" class="chart"></div></section>
    <section class="card"><h2>Faturado x glosado por mês</h2>
      <div class="muted">Mês do pagamento (R$)</div>
      <div id="g-mensal" class="chart"></div></section>
    <section class="card"><h2>Contas enviadas fora do prazo</h2>
      <div class="muted">% das contas enviadas após o prazo contratual</div>
      <div id="g-prazo" class="chart"></div></section>
    <section class="card"><h2>Contas paradas (fechadas e não enviadas)</h2>
      <div class="muted">Ordenadas pelo prazo que resta · negativo = prazo vencido</div>
      <div class="scroll">{{TABELA_PARADAS}}</div></section>
  </div>

  <section class="card" style="margin-top:16px">
    <h2>Corrigir antes de enviar</h2>
    <div class="muted">Itens com erro em contas ainda não enviadas, por valor em risco</div>
    <div class="scroll">{{TABELA_PEND}}</div>
  </section>

  <footer>Dados 100% fictícios, gerados por script. Projeto de estudo de SQL, dashboards e automação com IA.</footer>
</main>

<script>
const D = {{DADOS}};
const css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const brl = v => "R$ " + v.toLocaleString("pt-BR", {minimumFractionDigits: 0, maximumFractionDigits: 0});

function base(extra) {
  return Object.assign({
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)",
    font: {family: "system-ui, -apple-system, Segoe UI, sans-serif", size: 12, color: css("--ink-2")},
    separators: ",.", margin: {l: 10, r: 20, t: 10, b: 30}, showlegend: false, bargap: 0.35,
    xaxis: {gridcolor: css("--grid"), zerolinecolor: css("--axis"), automargin: true},
    yaxis: {gridcolor: css("--grid"), zerolinecolor: css("--axis"), automargin: true},
    hoverlabel: {bgcolor: css("--surface"), bordercolor: css("--axis"), font: {color: css("--ink")}},
  }, extra || {});
}
const cfg = {displayModeBar: false, responsive: true};

function desenhar() {
  const s1 = css("--s1"), s2 = css("--s2"), neutro = css("--neutral");

  // Glosa evitável: barras horizontais, cor indica se era detectável por regra
  const ev = D.evitavel;
  Plotly.react("g-evitavel", [{
    type: "bar", orientation: "h", y: ev.causa.slice().reverse(), x: ev.valor.slice().reverse(),
    marker: {color: ev.evitavel.slice().reverse().map(e => e ? s1 : neutro)},
    text: ev.valor.slice().reverse().map(brl), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{y}<br>%{text}<extra></extra>",
  }], base({xaxis: {visible: false}}), cfg);

  // Funil
  Plotly.react("g-funil", [{
    type: "bar", orientation: "h", y: D.funil.etapa.slice().reverse(), x: D.funil.qtd.slice().reverse(),
    marker: {color: s1}, text: D.funil.qtd.slice().reverse(), textposition: "outside", cliponaxis: false,
    hovertemplate: "%{y}: %{x}<extra></extra>",
  }], base({xaxis: {visible: false}}), cfg);

  // Taxa por convênio com linha de média
  const cv = D.convenio;
  Plotly.react("g-convenio", [{
    type: "bar", orientation: "h", y: cv.nome.slice().reverse(), x: cv.taxa.slice().reverse(),
    marker: {color: s1}, text: cv.taxa.slice().reverse().map(v => v.toFixed(1).replace(".", ",") + "%"),
    textposition: "outside", cliponaxis: false, hovertemplate: "%{y}: %{text}<extra></extra>",
  }], base({
    xaxis: {visible: false, range: [0, Math.max(...cv.taxa) * 1.25]},
    shapes: [{type: "line", x0: cv.media, x1: cv.media, yref: "paper", y0: 0, y1: 1,
              line: {color: css("--ink-2"), width: 1.5, dash: "dash"}}],
  }), cfg);

  // Faturado x glosado (mesma unidade, um só eixo)
  const m = D.mensal;
  Plotly.react("g-mensal", [
    {type: "bar", name: "Faturado", x: m.mes, y: m.faturado, marker: {color: s1},
     customdata: m.taxa, hovertemplate: "%{x}<br>Faturado: R$ %{y:,.0f}<extra></extra>"},
    {type: "bar", name: "Glosado", x: m.mes, y: m.glosado, marker: {color: s2},
     customdata: m.taxa, hovertemplate: "%{x}<br>Glosado: R$ %{y:,.0f} (%{customdata:.1f}%)<extra></extra>"},
  ], base({showlegend: true, legend: {orientation: "h", y: 1.12, x: 0}, bargap: 0.3, bargroupgap: 0.06,
           yaxis: {gridcolor: css("--grid"), tickprefix: "R$ ", separatethousands: true, automargin: true}}), cfg);

  // Fora do prazo
  Plotly.react("g-prazo", [{
    type: "bar", orientation: "h", y: D.prazo.nome.slice().reverse(), x: D.prazo.pct.slice().reverse(),
    marker: {color: s1}, text: D.prazo.pct.slice().reverse().map(v => v.toFixed(1).replace(".", ",") + "%"),
    textposition: "outside", cliponaxis: false, hovertemplate: "%{y}: %{text}<extra></extra>",
  }], base({xaxis: {visible: false, range: [0, Math.max(...D.prazo.pct) * 1.3 || 1]}}), cfg);
}

if (window.Plotly) {
  desenhar();
} else {
  document.querySelectorAll(".chart").forEach(el => {
    el.innerHTML = '<p class="muted">Não foi possível carregar a biblioteca de gráficos (Plotly). ' +
                   'Confira a conexão com a internet e recarregue a página.</p>';
  });
}
if (window.Plotly) matchMedia("(prefers-color-scheme: dark)").addEventListener("change", desenhar);
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
