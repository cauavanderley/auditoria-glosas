"""
Gera uma base FICTÍCIA de faturamento hospitalar (contas médicas e glosas).

Nenhum dado aqui é real: hospitais, convênios, pacientes e valores são inventados.
O objetivo é ter um cenário realista para praticar SQL, dashboards, alertas e
automação com IA no ciclo da receita hospitalar.

Problemas "plantados" de propósito na base (o que o projeto tenta encontrar):
  1. Item cobrado com preço diferente do contrato com o convênio
  2. Procedimento que exige autorização cobrado sem número de guia
  3. Item lançado em duplicidade na mesma conta
  4. Conta enviada ao convênio depois do prazo contratual
  5. Contas paradas (fechadas e não enviadas)

Uso:
    python dados/gerar_dados.py            # gera os CSVs em dados/csv/
    python dados/gerar_dados.py --seed 7   # outra base, mesma lógica
"""

import argparse
import csv
import random
from datetime import date, timedelta
from pathlib import Path

DATA_REFERENCIA = date(2026, 10, 15)  # "hoje" da base
INICIO, FIM = date(2026, 4, 1), date(2026, 10, 12)
N_ATENDIMENTOS = 1800

# id, nome, prazo de envio (dias após a alta), fator de preço do contrato, rigor na auditoria
CONVENIOS = [
    (1, "Saúde Alfa", 30, 1.00, 1.0),
    (2, "Vida Mais Beta", 45, 0.92, 0.8),
    (3, "Plano Gama", 30, 1.10, 1.5),
    (4, "Cuidar Delta", 60, 0.95, 0.6),
    (5, "Ômega Saúde", 30, 1.05, 1.2),
]
PESO_CONVENIOS = [0.30, 0.25, 0.20, 0.15, 0.10]

# código, descrição, grupo, valor de referência, exige autorização
PROCEDIMENTOS = [
    ("P001", "Diária de enfermaria", "Diária", 450.00, 0),
    ("P002", "Diária de UTI adulto", "Diária", 2200.00, 1),
    ("P003", "Consulta em pronto-socorro", "Consulta", 180.00, 0),
    ("P004", "Hemograma completo", "Exame", 25.00, 0),
    ("P005", "Raio-X de tórax", "Exame", 80.00, 0),
    ("P006", "Tomografia de crânio", "Exame", 650.00, 1),
    ("P007", "Ressonância magnética de joelho", "Exame", 1200.00, 1),
    ("P008", "Ultrassonografia de abdome", "Exame", 220.00, 0),
    ("P009", "Eletrocardiograma", "Exame", 60.00, 0),
    ("P010", "Cateter venoso central", "Material", 380.00, 0),
    ("P011", "Kit de curativo especial", "Material", 140.00, 0),
    ("P012", "Soro fisiológico 500 ml", "Medicamento", 12.00, 0),
    ("P013", "Antibiótico IV (dose)", "Medicamento", 95.00, 0),
    ("P014", "Quimioterápico (dose)", "Medicamento", 3200.00, 1),
    ("P015", "Apendicectomia", "Cirurgia", 2800.00, 1),
    ("P016", "Colecistectomia videolaparoscópica", "Cirurgia", 4500.00, 1),
    ("P017", "Sessão de fisioterapia", "Terapia", 90.00, 0),
    ("P018", "Hemodiálise (sessão)", "Terapia", 850.00, 1),
    ("P019", "Gasometria arterial", "Exame", 70.00, 0),
    ("P020", "Taxa de sala cirúrgica", "Taxa", 1500.00, 0),
    ("P021", "Visita médica hospitalar", "Honorário", 150.00, 0),
    ("P022", "Stent coronariano", "OPME", 9800.00, 1),
    ("P023", "Endoscopia digestiva alta", "Exame", 520.00, 1),
    ("P024", "Analgésico IV (dose)", "Medicamento", 18.00, 0),
]
PROC = {p[0]: p for p in PROCEDIMENTOS}

SETORES = {
    "Pronto-socorro": "PS",
    "Ambulatorial": "Ambulatório",
    "Internação clínica": "Clínica Médica",
    "Internação cirúrgica": "Centro Cirúrgico",
    "Oncologia": "Oncologia",
}
TIPOS = list(SETORES)
PESO_TIPOS = [0.45, 0.22, 0.15, 0.10, 0.08]

# Códigos de motivo da operadora (fictícios). G99 = "outros", texto livre.
CODIGOS = {
    "PRECO_DIVERGENTE": "G01",
    "SEM_AUTORIZACAO": "G02",
    "DUPLICIDADE": "G03",
    "PRAZO_EXPIRADO": "G04",
    "DOCUMENTACAO_INCOMPLETA": "G05",
    "INCOMPATIBILIDADE_CLINICA": "G06",
}

# Textos livres que a operadora escreve na glosa (variados de propósito).
TEXTOS = {
    "PRECO_DIVERGENTE": [
        "Valor cobrado de {proc} acima do acordado em contrato. Pago conforme tabela vigente.",
        "VALOR DIVERGENTE DA TABELA NEGOCIADA - {proc}",
        "Cobrança de R$ {cobrado} p/ {proc}; valor contratual R$ {contrato}. Glosada a diferença.",
        "Item {proc} faturado com preço fora da tabela do prestador.",
        "Preço unitário não confere com o contrato vigente (tabela atualizada em 03/2026).",
        "Diferença de valor - {proc} - aplicar tabela própria da operadora",
    ],
    "SEM_AUTORIZACAO": [
        "Procedimento {proc} realizado sem autorização prévia.",
        "AUSÊNCIA DE SENHA DE AUTORIZAÇÃO PARA {proc}",
        "Não consta guia autorizada para o item {proc}.",
        "Item exige liberação prévia da auditoria médica - sem número de guia na conta.",
        "Sem autorizacao. Solicitar liberação retroativa se houver justificativa de urgência.",
        "{proc}: procedimento eletivo sem pedido de autorização registrado.",
    ],
    "DUPLICIDADE": [
        "Item {proc} cobrado em duplicidade na mesma conta.",
        "COBRANÇA DUPLICADA - {proc}",
        "Lançamento repetido do mesmo procedimento na mesma data.",
        "{proc} já cobrado nesta conta; glosado o segundo lançamento.",
        "Duplicidade de cobrança identificada pela auditoria de contas.",
    ],
    "PRAZO_EXPIRADO": [
        "Conta apresentada fora do prazo contratual de {prazo} dias.",
        "PRAZO DE ENVIO EXPIRADO",
        "Faturamento recebido após o prazo de apresentação previsto em contrato.",
        "Conta enviada {dias} dias após a alta - prazo máximo {prazo} dias.",
        "Intempestividade na apresentação da conta. Não passível de pagamento.",
    ],
    "DOCUMENTACAO_INCOMPLETA": [
        "Falta relatório médico justificando {proc}.",
        "Prescrição médica ilegível ou ausente para {proc}.",
        "AUSÊNCIA DE ASSINATURA DO MÉDICO ASSISTENTE NA EVOLUÇÃO",
        "Não foi enviado laudo do exame {proc}.",
        "Documentação insuficiente para comprovar a realização de {proc}.",
        "Faltou anexar folha de sala / descrição cirúrgica.",
    ],
    "INCOMPATIBILIDADE_CLINICA": [
        "{proc} incompatível com o diagnóstico informado (CID).",
        "Quantidade de {proc} acima do esperado para o quadro clínico.",
        "Procedimento não justificado pelo quadro descrito na evolução.",
        "Auditoria médica: indicação de {proc} não compatível com protocolo clínico.",
        "Excesso de diárias para o diagnóstico apresentado.",
    ],
}

# Composição típica de itens por tipo de atendimento: (código, prob, qtd mín, qtd máx)
CESTAS = {
    "Pronto-socorro": [("P003", 1, 1, 1), ("P004", .6, 1, 1), ("P005", .4, 1, 1), ("P009", .3, 1, 1),
                       ("P012", .7, 1, 3), ("P024", .7, 1, 3), ("P013", .2, 1, 2), ("P006", .1, 1, 1),
                       ("P008", .15, 1, 1)],
    "Ambulatorial": [("P008", .4, 1, 1), ("P007", .2, 1, 1), ("P023", .25, 1, 1), ("P017", .35, 1, 10),
                     ("P009", .3, 1, 1), ("P004", .4, 1, 1)],
    "Internação clínica": [("P001", 1, 2, 10), ("P021", 1, 2, 10), ("P004", .9, 1, 5), ("P013", .8, 2, 14),
                           ("P012", .9, 2, 12), ("P024", .8, 2, 10), ("P005", .6, 1, 3), ("P002", .2, 1, 4),
                           ("P019", .3, 1, 4), ("P010", .2, 1, 1), ("P018", .1, 1, 4), ("P006", .2, 1, 1)],
    "Internação cirúrgica": [("P020", 1, 1, 1), ("P001", 1, 1, 6), ("P021", 1, 1, 6), ("P015", .45, 1, 1),
                             ("P016", .45, 1, 1), ("P022", .1, 1, 2), ("P011", .7, 1, 4), ("P013", .9, 2, 10),
                             ("P024", .9, 2, 10), ("P004", .9, 1, 4), ("P002", .25, 1, 3), ("P010", .3, 1, 1)],
    "Oncologia": [("P014", 1, 1, 3), ("P012", 1, 1, 4), ("P004", .9, 1, 2), ("P021", .6, 1, 1),
                  ("P024", .6, 1, 2)],
}
DURACAO = {"Pronto-socorro": (0, 0), "Ambulatorial": (0, 0), "Internação clínica": (2, 12),
           "Internação cirúrgica": (1, 7), "Oncologia": (0, 0)}


# Alguns textos só fazem sentido para certos grupos de itens
RESTRICOES = {"laudo do exame": {"Exame"}, "folha de sala": {"Cirurgia", "Taxa"},
              "Excesso de diárias": {"Diária"}}


def combina(texto, grupo):
    return all(grupo in grupos for chave, grupos in RESTRICOES.items() if chave in texto)


def brl(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar(seed: int, pasta: Path):
    rnd = random.Random(seed)
    pasta.mkdir(parents=True, exist_ok=True)

    # Tabela de preços contratados por convênio
    contratos = {}
    for cid, _, _, fator, _ in CONVENIOS:
        for cod, _, _, ref, _ in PROCEDIMENTOS:
            contratos[(cid, cod)] = round(ref * fator * rnd.uniform(0.95, 1.05), 2)

    atendimentos, contas, itens, glosas, gabarito = [], [], [], [], []
    item_id = glosa_id = 0
    dias_periodo = (FIM - INICIO).days

    for aid in range(1, N_ATENDIMENTOS + 1):
        tipo = rnd.choices(TIPOS, PESO_TIPOS)[0]
        conv = rnd.choices(CONVENIOS, PESO_CONVENIOS)[0]
        cid, _, prazo, _, rigor = conv
        entrada = INICIO + timedelta(days=rnd.randint(0, dias_periodo))
        dmin, dmax = DURACAO[tipo]
        alta = entrada + timedelta(days=rnd.randint(dmin, dmax))
        atendimentos.append([aid, f"PAC{rnd.randint(10000, 99999)}", cid, tipo, SETORES[tipo],
                             entrada.isoformat(), alta.isoformat()])

        # ---- Datas do ciclo da conta -------------------------------------------------
        fechamento = alta + timedelta(days=rnd.choice([1, 1, 2, 2, 3, 4, 5, 7, 10, 15]))
        r = rnd.random()
        if r < 0.03:
            envio = fechamento + timedelta(days=rnd.randint(40, 70))   # atraso grave -> fora do prazo
        elif r < 0.055:
            envio = None                                               # conta "esquecida"
        else:
            envio = fechamento + timedelta(days=rnd.randint(1, 12))
        pagamento = envio + timedelta(days=rnd.randint(20, 45)) if envio else None

        if fechamento > DATA_REFERENCIA:
            status, fechamento, envio, pagamento = "ABERTA", None, None, None
        elif envio is None or envio > DATA_REFERENCIA:
            status, envio, pagamento = "FECHADA", None, None
        elif pagamento > DATA_REFERENCIA:
            status, pagamento = "ENVIADA", None
        else:
            status = "PAGA"

        # ---- Itens da conta ----------------------------------------------------------
        itens_conta = []
        cesta = CESTAS[tipo]
        sorteados = [c for c in cesta if rnd.random() <= c[1]] or [rnd.choice(cesta)]  # ao menos 1 item
        for cod, prob, qmin, qmax in sorteados:
            qtd = rnd.randint(qmin, qmax)
            preco = contratos[(cid, cod)]
            erro = None
            if rnd.random() < 0.04:                       # 1) preço divergente
                preco = round(preco * rnd.choice([1.08, 1.15, 1.25, 1.30]), 2)
                erro = "PRECO_DIVERGENTE"
            guia = f"GA{rnd.randint(1000000, 9999999)}" if PROC[cod][4] else None
            if guia and rnd.random() < 0.09:              # 2) sem autorização
                guia, erro = None, "SEM_AUTORIZACAO"
            data_item = entrada + timedelta(days=rnd.randint(0, (alta - entrada).days))
            item_id += 1
            itens_conta.append([item_id, aid, cod, qtd, preco, guia, data_item.isoformat(), erro])
            if rnd.random() < 0.015:                      # 3) duplicidade
                item_id += 1
                itens_conta.append([item_id, aid, cod, qtd, preco, guia, data_item.isoformat(),
                                    "DUPLICIDADE"])
        valor_cobrado = round(sum(i[3] * i[4] for i in itens_conta), 2)

        # ---- Glosas (só aparecem em contas já analisadas e pagas) --------------------
        valor_glosado = 0.0
        if status == "PAGA":
            data_glosa = (pagamento - timedelta(days=rnd.randint(0, 10))).isoformat()
            dias_envio = (envio - alta).days

            def nova_glosa(item, cat, valor, extra=None):
                nonlocal glosa_id, valor_glosado
                glosa_id += 1
                valor = round(min(valor, (item[3] * item[4]) if item else valor_cobrado), 2)
                valor_glosado += valor
                nome = PROC[item[2]][1] if item else ""
                grupo = PROC[item[2]][2] if item else ""
                opcoes = [t for t in TEXTOS[cat] if combina(t, grupo)]
                texto = rnd.choice(opcoes).format(
                    proc=nome or "itens da conta", cobrado=brl(item[4]) if item else "",
                    contrato=brl(contratos[(cid, item[2])]) if item else "",
                    prazo=prazo, dias=dias_envio)
                if rnd.random() < 0.15:
                    texto = texto.lower()
                codigo = "G99" if rnd.random() < 0.40 else CODIGOS[cat]  # 40% vêm como "outros"
                glosas.append([glosa_id, aid, item[0] if item else "", codigo, texto, valor, data_glosa])
                gabarito.append([glosa_id, cat])

            if dias_envio > prazo and rnd.random() < 0.6:  # 4) prazo expirado: glosa a conta toda
                nova_glosa(None, "PRAZO_EXPIRADO", valor_cobrado)
            else:
                for it in itens_conta:
                    total_item = it[3] * it[4]
                    if it[7] == "PRECO_DIVERGENTE" and rnd.random() < 0.85:
                        diff = (it[4] - contratos[(cid, it[2])]) * it[3]
                        nova_glosa(it, "PRECO_DIVERGENTE", diff)
                    elif it[7] == "SEM_AUTORIZACAO" and rnd.random() < 0.85:
                        nova_glosa(it, "SEM_AUTORIZACAO", total_item)
                    elif it[7] == "DUPLICIDADE" and rnd.random() < 0.90:
                        nova_glosa(it, "DUPLICIDADE", total_item)
                    elif rnd.random() < 0.04 * rigor:  # glosas "clínicas" (não detectáveis por regra)
                        cat = rnd.choice(["DOCUMENTACAO_INCOMPLETA", "INCOMPATIBILIDADE_CLINICA"])
                        nova_glosa(it, cat, total_item * rnd.choice([0.3, 0.5, 1.0]))

        valor_pago = round(valor_cobrado - valor_glosado, 2) if status == "PAGA" else ""
        contas.append([aid, aid, status,
                       fechamento.isoformat() if fechamento else "",
                       envio.isoformat() if envio else "",
                       pagamento.isoformat() if pagamento else "",
                       valor_cobrado, valor_pago])
        itens.extend(i[:7] for i in itens_conta)

    # ---- Escrita dos CSVs --------------------------------------------------------------
    def salvar(nome, cabecalho, linhas):
        with open(pasta / f"{nome}.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(cabecalho)
            w.writerows(linhas)

    salvar("convenios", ["id", "nome", "prazo_envio_dias"], [c[:3] for c in CONVENIOS])
    salvar("procedimentos", ["codigo", "descricao", "grupo", "valor_referencia", "exige_autorizacao"],
           PROCEDIMENTOS)
    salvar("precos_contrato", ["convenio_id", "procedimento_codigo", "valor_contratado"],
           [[c, p, v] for (c, p), v in contratos.items()])
    salvar("atendimentos", ["id", "paciente", "convenio_id", "tipo", "setor", "data_entrada", "data_alta"],
           atendimentos)
    salvar("contas", ["id", "atendimento_id", "status", "data_fechamento", "data_envio",
                      "data_pagamento", "valor_cobrado", "valor_pago"], contas)
    salvar("itens_conta", ["id", "conta_id", "procedimento_codigo", "quantidade",
                           "valor_unitario", "numero_guia", "data_execucao"], itens)
    salvar("glosas", ["id", "conta_id", "item_id", "codigo_motivo", "texto_glosa", "valor_glosado",
                      "data_glosa"], glosas)
    # Gabarito: a categoria "verdadeira" de cada glosa. NÃO vai para o banco;
    # serve só para medir a precisão da classificação feita pela IA.
    salvar("glosas_gabarito", ["glosa_id", "categoria_real"], gabarito)

    print(f"Base gerada em {pasta}/")
    print(f"  {len(atendimentos)} atendimentos | {len(itens)} itens | {len(glosas)} glosas")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    gerar(args.seed, Path(__file__).parent / "csv")
