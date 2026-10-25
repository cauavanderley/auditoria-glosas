# Auditoria de Glosas: SQL, dashboard e IA no ciclo da receita hospitalar

Projeto de estudo que simula o faturamento de um hospital e usa **SQL, um dashboard, alertas e IA (Claude)** para responder a uma pergunta de negócio:

> **Quanto dinheiro o hospital perde em glosas, e quanto disso dava para evitar antes de enviar a conta ao convênio?**

*Glosa* é o valor que o convênio se recusa a pagar numa conta médica: um item cobrado com preço errado, um exame sem autorização, um lançamento duplicado, uma conta enviada fora do prazo. É uma das maiores fontes de perda de receita nos hospitais brasileiros.

> ⚠️ **Todos os dados são fictícios**, gerados por script (`dados/gerar_dados.py`). Hospital, convênios, pacientes e valores são inventados.

## Resultados (base gerada com `--seed 42`)

| Pergunta | Resposta |
|---|---|
| Quanto foi glosado? | **R$ 395 mil** de R$ 3,91 milhões faturados (**10,1%**) |
| Quanto era evitável? | **79%** do valor glosado vinha de erros que regras simples detectam antes do envio |
| O que corrigir agora? | **33 contas ainda não enviadas** já têm itens com erro (**R$ 26 mil em risco**) |
| Onde está o gargalo? | **43 contas paradas** passaram do prazo de envio sem ser enviadas (**R$ 114 mil**) |
| Por que usar IA? | **41%** das glosas chegam com código genérico ("G99 - outros"): o motivo está só no texto livre |
| A IA acerta? | **100%** de acurácia (**100%** nas glosas G99) |
<img width="1305" height="1058" alt="dashboard" src="https://github.com/user-attachments/assets/b153da01-4f99-4095-8393-3c2497c414ee" />


## Como funciona

```
 gerar_dados.py        carregar_mysql.py         03_analises.sql          saídas
┌──────────────┐  CSV  ┌──────────────┐  views  ┌────────────────┐   ┌─────────────────────┐
│ base fictícia│ ────▶ │   MySQL 8    │ ──────▶ │ 12 consultas   │──▶│ dashboard.html      │
│ (6 meses)    │       │ 7 tabelas    │         │ nomeadas       │   │ alertas.md          │
└──────────────┘       └──────────────┘         └────────────────┘   │ glosas → Sheets     │
                                                                      └──────────┬──────────┘
                                                                                 ▼
                                                        Google Sheets + Apps Script + API do Claude
                                                        classifica o texto das glosas, mede a acurácia
                                                        contra um gabarito e aprende com correções
```

1. **Dados**: um script gera atendimentos, contas, itens, tabela de preços por convênio e glosas, com erros "plantados" de propósito (preço fora do contrato, item sem autorização, duplicidade, envio fora do prazo).
2. **SQL (MySQL)**: o esquema tem 7 tabelas e 2 views de auditoria. As **regras de detecção** ficam na view `vw_erros_detectados`, e as análises usam `JOIN`, CTEs (`WITH`), funções de janela (`ROW_NUMBER`, `SUM() OVER`), `UNION ALL`, `DATEDIFF` e `GROUP BY ... HAVING`.
3. **Alertas**: `alertas.py` transforma as consultas em uma lista do que precisa de ação hoje (contas perto do prazo, erros antes do envio, convênio fora da curva, piora no mês).
4. **Dashboard**: `dashboard.py` gera um HTML interativo (Plotly) com indicadores, funil, causas da glosa e listas de trabalho.
5. **IA**: no Google Sheets, um Apps Script chama a API do Claude para classificar o texto livre de cada glosa (categoria, se vale recorrer, confiança e justificativa), mede a acurácia contra um gabarito e usa as **correções do time** como exemplos nas próximas classificações.

## Estrutura

```
auditoria-glosas/
├── dados/gerar_dados.py          # gera a base fictícia em dados/csv/
├── sql/
│   ├── 01_schema.sql             # tabelas
│   ├── 02_views.sql              # regras de auditoria (views)
│   └── 03_analises.sql           # consultas nomeadas: -- [nome]
├── scripts/
│   ├── db.py                     # conexão e leitura das consultas
│   ├── carregar_mysql.py         # cria o banco e carrega os CSVs
│   ├── alertas.py                # alertas operacionais
│   ├── dashboard.py              # gera saida/dashboard.html
│   ├── exportar_planilha.py      # gera o CSV para o Google Sheets
│   └── testar_consultas.py       # roda todas as consultas (usado no CI)
├── apps_script/Code.gs           # classificação com IA no Google Sheets
├── docs/COMO_FUNCIONA.md         # explicação de cada parte e dos conceitos de SQL
└── .github/workflows/ci.yml      # CI: sobe um MySQL e roda o pipeline inteiro a cada push
```

## Como rodar

### 1. MySQL

Com Docker (mais simples):

```bash
docker run --name mysql-glosas -e MYSQL_ROOT_PASSWORD=senha123 -p 3306:3306 -d mysql:8.0
```

Ou instale o [MySQL Community Server 8](https://dev.mysql.com/downloads/mysql/).

### 2. Python

```bash
pip install -r requirements.txt

# senha do MySQL (padrão: usuário root em localhost:3306)
export MYSQL_PASSWORD=senha123          # macOS/Linux
$env:MYSQL_PASSWORD="senha123"          # Windows PowerShell

python dados/gerar_dados.py             # 1) gera a base em dados/csv/
python scripts/carregar_mysql.py        # 2) cria o banco auditoria_glosas e carrega os dados
python scripts/testar_consultas.py      #    confere se todas as consultas rodam
python scripts/alertas.py               # 3) imprime os alertas e salva saida/alertas.md
python scripts/dashboard.py             # 4) gera saida/dashboard.html (abra no navegador)
python scripts/exportar_planilha.py     # 5) gera saida/glosas_para_planilha.csv
```

Para explorar as consultas no MySQL Workbench, rode `SET @hoje = '2026-10-15';` e depois qualquer bloco de `sql/03_analises.sql`.

### 3. IA no Google Sheets

1. Crie uma planilha no Google Sheets.
2. **Arquivo → Importar** `saida/glosas_para_planilha.csv` numa aba chamada **`glosas`**.
3. Importe `dados/csv/glosas_gabarito.csv` numa aba chamada **`gabarito`**.
4. **Extensões → Apps Script**: cole o conteúdo de `apps_script/Code.gs`, salve e recarregue a planilha.
5. Gere uma chave em [console.anthropic.com](https://console.anthropic.com) (a API é cobrada à parte; classificar ~600 glosas com o Haiku custa centavos).
6. No menu **🤖 IA Glosas**:
   - **Configurar chave da API**: a chave fica nas propriedades do script, fora da planilha.
   - **Classificar glosas pendentes**: em lotes de 25 por chamada.
   - **Avaliar com o gabarito**: cria a aba `avaliacao` com acurácia geral, precisão e recall por categoria e a lista de erros.
   - **Gerar resumo para a liderança**: o Claude escreve um resumo executivo com os números.
7. **Ciclo de melhoria**: nas linhas em que a IA errou, preencha `correcao_humana` com a categoria certa e reclassifique (apague `categoria_ia` dessas linhas). As correções entram no prompt como exemplos.

Opcional: conecte a planilha ao **Looker Studio** para um painel de BI das glosas classificadas.

## Perguntas que as consultas respondem

| Consulta | Pergunta |
|---|---|
| `kpis` | Quanto foi faturado e glosado, e qual a taxa de glosa? |
| `funil` | Em que etapa (fechamento, envio, pagamento) as contas travam? |
| `glosa_por_convenio` | Qual convênio glosa mais? |
| `evolucao_mensal` | A taxa de glosa está melhorando ou piorando? |
| `glosa_por_codigo` | Quantas glosas vêm sem código claro (G99)? |
| `glosa_evitavel` | Quanto da glosa era detectável antes do envio, e por qual regra? |
| `pendencias_pre_envio(_detalhe)` | O que corrigir **agora**, antes de enviar? |
| `contas_paradas` | Quais contas estão paradas e quanto prazo resta? |
| `prazo_por_convenio` | Quanto tempo leva da alta ao envio? Quantas saem fora do prazo? |
| `top_itens_glosados` | Quais itens mais geram glosa em cada convênio? |

## Próximos passos

- Agendar os alertas (gatilho diário do Apps Script ou cron) com envio por e-mail.
- Usar a IA para redigir o texto do recurso das glosas marcadas como recorríveis.
- Ler contratos em PDF com IA para montar a tabela `precos_contrato` automaticamente.

---
Feito por Cauã Vanderley Lopes Furtado (Engenharia Eletrônica, ITA), com o Claude como apoio no desenvolvimento.
