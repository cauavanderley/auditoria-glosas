# Como funciona cada parte

## 1. O modelo de dados

```
convenios ─┬─< precos_contrato >── procedimentos
           │                            │
           └─< atendimentos ── contas ─< itens_conta
                                  │          │
                                  └─< glosas >┘
```

- Um **atendimento** (passagem do paciente) gera uma **conta**, que tem vários **itens** (diárias, exames, medicamentos, cirurgias).
- Cada convênio tem um **preço negociado** para cada item (`precos_contrato`) e um **prazo** para receber a conta.
- A conta passa por `ABERTA → FECHADA → ENVIADA → PAGA`. Quando o convênio paga, ele pode **glosar** itens específicos ou a conta inteira.

## 2. As regras de auditoria (`sql/02_views.sql`)

A view `vw_erros_detectados` junta três regras com `UNION ALL`:

| Regra | Como o SQL encontra |
|---|---|
| Preço fora do contrato | `JOIN` entre o item e `precos_contrato` pelo convênio do atendimento; filtra `valor_unitario <> valor_contratado` |
| Sem autorização | `JOIN` com `procedimentos`; filtra `exige_autorizacao = 1 AND numero_guia IS NULL` |
| Duplicidade | `ROW_NUMBER() OVER (PARTITION BY conta, item, data, quantidade, preço)`: a 1ª ocorrência é válida, as seguintes são suspeitas |

Como as regras estão numa **view**, todas as consultas usam a mesma definição de "erro". Para mudar uma regra, basta mudar a view.

## 3. Conceitos de SQL usados nas análises

| Conceito | Onde aparece | Para quê |
|---|---|---|
| `JOIN` / `LEFT JOIN` | quase todas | cruzar conta → atendimento → convênio; `LEFT` mantém contas sem glosa |
| CTE (`WITH ... AS`) | `kpis`, `glosa_evitavel` | somar as glosas por conta **antes** de juntar, para não duplicar valores |
| Função de janela `SUM() OVER ()` | `glosa_por_codigo`, `glosa_evitavel` | calcular o % de cada linha sobre o total sem um segundo `GROUP BY` |
| `ROW_NUMBER() OVER (PARTITION BY ...)` | `top_itens_glosados`, view de duplicidade | ranking dentro de cada grupo |
| `UNION ALL` + `ORDER BY` | `funil` | empilhar contagens de etapas diferentes |
| `CASE WHEN` | `glosa_evitavel`, `vw_prazo_envio` | classificar cada glosa pela causa |
| `DATEDIFF` | `contas_paradas`, `vw_prazo_envio` | dias entre alta, envio e hoje |
| `GROUP BY ... HAVING` | `evolucao_mensal` | descartar meses com poucas contas |
| `NOT EXISTS` | `funil` | contas pagas sem nenhuma glosa |

**Armadilha clássica que o projeto evita:** juntar `contas` com `glosas` diretamente e depois somar `valor_cobrado` conta a mesma conta várias vezes (uma vez por glosa). Por isso as glosas são somadas por conta numa CTE antes do `JOIN`.

## 4. A pergunta principal: quanto era evitável?

A consulta `glosa_evitavel` olha cada glosa e pergunta: "o item glosado tinha um erro que as regras detectam?"

- Sim → a glosa era **evitável** (dava para corrigir antes de enviar).
- A glosa é da conta inteira e a conta foi enviada fora do prazo → **prazo expirado** (evitável com gestão de fila).
- Nenhum dos dois → **não detectável por regra** (problemas clínicos ou de documentação, que exigem análise humana ou IA).

## 5. Alertas e dashboard

- `alertas.py` aplica limites simples sobre as consultas (prazo ≤ 7 dias, taxa 40% acima da média, alta de 2 p.p. no mês) e gera frases acionáveis.
- `dashboard.py` roda as consultas, monta um JSON e injeta num HTML com Plotly. Não precisa de servidor: é só abrir o arquivo.

## 6. IA no Google Sheets (`apps_script/Code.gs`)

1. Lê as glosas sem categoria e envia **lotes de 25** para a API do Claude (`UrlFetchApp`).
2. O prompt define as 6 categorias e pede uma resposta **somente em JSON** (categoria, recorrível, confiança, justificativa), que o script valida e grava nas colunas.
3. Trata erros da API: em caso de limite de taxa (429) ou sobrecarga (5xx), espera e tenta de novo.
4. Respeita o limite de 6 minutos do Apps Script: para e pede para rodar de novo, sem perder o progresso.
5. **Avaliação:** compara com o gabarito e calcula acurácia, precisão e recall por categoria. Assim a qualidade da automação é medida, não suposta.
6. **Melhoria contínua:** correções do time (`correcao_humana`) viram exemplos no prompt (*few-shot*). O modelo aprende o critério do time sem treinar nada.
