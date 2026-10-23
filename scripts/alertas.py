"""
Alertas operacionais do faturamento: o que precisa de ação HOJE.

Uso:
    python scripts/alertas.py      # imprime os alertas e salva em saida/alertas.md
"""

import db

LIMITE_PRAZO_DIAS = 7          # avisar quando faltar até 7 dias para vencer o prazo de envio
FATOR_CONVENIO = 1.4           # convênio com taxa de glosa 40% acima da média
LIMITE_SEM_CODIGO_PCT = 30     # % de glosas que chegam como "G99 - outros"
NOMES_ERRO = {"SEM_AUTORIZACAO": "sem autorização", "DUPLICIDADE": "em duplicidade",
              "PRECO_DIVERGENTE": "com preço fora do contrato"}


def brl(v):
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v):
    return f"{v:.1f}%".replace(".", ",")


def gerar_alertas():
    alertas = []

    # 1) Contas paradas: prazo de envio vencido ou perto de vencer
    paradas = db.consultar("contas_paradas")
    vencidas = paradas[paradas.dias_restantes_prazo < 0]
    vencendo = paradas[paradas.dias_restantes_prazo.between(0, LIMITE_PRAZO_DIAS)]
    if len(vencidas):
        alertas.append({
            "nivel": "CRÍTICO",
            "titulo": f"{len(vencidas)} contas paradas já passaram do prazo de envio",
            "detalhe": f"{brl(vencidas.valor_cobrado.sum())} com risco de glosa total. "
                       "Enviar hoje e negociar com o convênio.",
        })
    if len(vencendo):
        alertas.append({
            "nivel": "ALTO",
            "titulo": f"{len(vencendo)} contas vencem o prazo nos próximos {LIMITE_PRAZO_DIAS} dias",
            "detalhe": f"{brl(vencendo.valor_cobrado.sum())} a enviar com prioridade.",
        })

    # 2) Erros encontrados em contas que ainda não foram enviadas (dá para corrigir!)
    pend = db.consultar("pendencias_pre_envio")
    n_contas = db.consultar("pendencias_pre_envio_detalhe").conta_id.nunique()
    if len(pend):
        partes = ", ".join(f"{r.itens} {NOMES_ERRO[r.tipo_erro]}" for r in pend.itertuples())
        alertas.append({
            "nivel": "ALTO",
            "titulo": f"{n_contas} contas não enviadas têm itens com erro",
            "detalhe": f"{brl(pend.valor_em_risco.sum())} em risco ({partes}). "
                       "Corrigir antes de enviar.",
        })

    # 3) Convênio glosando muito acima da média
    conv = db.consultar("glosa_por_convenio")
    kpis = db.consultar("kpis").iloc[0]
    media = kpis.taxa_glosa_pct
    for r in conv[conv.taxa_glosa_pct > FATOR_CONVENIO * media].itertuples():
        alertas.append({
            "nivel": "MÉDIO",
            "titulo": f"{r.convenio}: taxa de glosa de {pct(r.taxa_glosa_pct)}",
            "detalhe": f"Média geral {pct(media)}. Revisar contrato e principais itens glosados.",
        })

    # 4) Piora da taxa de glosa no último mês
    mensal = db.consultar("evolucao_mensal")
    if len(mensal) >= 2:
        ult, ant = mensal.iloc[-1], mensal.iloc[-2]
        if ult.taxa_glosa_pct - ant.taxa_glosa_pct > 2:
            alertas.append({
                "nivel": "MÉDIO",
                "titulo": f"Taxa de glosa subiu em {ult.mes}",
                "detalhe": f"{pct(ant.taxa_glosa_pct)} → {pct(ult.taxa_glosa_pct)} (mês anterior → último mês). "
                           "Investigar quais convênios e itens puxaram a alta.",
            })

    # 5) Muitas glosas sem código claro -> classificar o texto com IA
    cod = db.consultar("glosa_por_codigo")
    g99 = cod.loc[cod.codigo_motivo == "G99", "pct_qtd"]
    if len(g99) and g99.iloc[0] > LIMITE_SEM_CODIGO_PCT:
        alertas.append({
            "nivel": "INFO",
            "titulo": f"{g99.iloc[0]:.0f}% das glosas vieram como 'G99 - outros'",
            "detalhe": "Motivo só no texto livre. Rodar a classificação com IA na planilha.",
        })

    return alertas


def main():
    alertas = gerar_alertas()
    linhas = [f"# Alertas do faturamento ({db.DATA_REFERENCIA})", ""]
    for a in alertas:
        linhas.append(f"- **[{a['nivel']}] {a['titulo']}**: {a['detalhe']}")
    texto = "\n".join(linhas)
    print(texto)
    saida = db.RAIZ / "saida"
    saida.mkdir(exist_ok=True)
    (saida / "alertas.md").write_text(texto + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
