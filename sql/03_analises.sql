-- =====================================================================
-- Análises do ciclo da receita (MySQL 8)
--
-- Cada bloco começa com "-- [nome]" e é lido pelos scripts Python pelo nome.
-- @hoje é a data de referência da base (2026-10-15). Numa base real seria CURDATE().
-- Para rodar no MySQL Workbench, execute antes:  SET @hoje = '2026-10-15';
-- =====================================================================


-- [kpis]
-- Visão geral das contas já pagas: quanto foi cobrado, quanto foi glosado e a taxa de glosa.
WITH glosa_conta AS (
    SELECT conta_id, SUM(valor_glosado) AS glosado
    FROM glosas
    GROUP BY conta_id
)
SELECT COUNT(*)                                                     AS contas_pagas,
       ROUND(SUM(c.valor_cobrado), 2)                               AS faturado,
       ROUND(SUM(COALESCE(g.glosado, 0)), 2)                        AS glosado,
       ROUND(100.0 * SUM(COALESCE(g.glosado, 0)) / SUM(c.valor_cobrado), 2) AS taxa_glosa_pct
FROM contas c
LEFT JOIN glosa_conta g ON g.conta_id = c.id
WHERE c.status = 'PAGA';


-- [funil]
-- Funil do faturamento: onde as contas estão "travando" entre a alta e o pagamento.
SELECT 1 AS ordem, 'Atendimentos com alta' AS etapa, COUNT(*) AS qtd
FROM atendimentos WHERE data_alta <= @hoje
UNION ALL
SELECT 2, 'Contas fechadas', COUNT(*) FROM contas WHERE status IN ('FECHADA', 'ENVIADA', 'PAGA')
UNION ALL
SELECT 3, 'Contas enviadas ao convênio', COUNT(*) FROM contas WHERE status IN ('ENVIADA', 'PAGA')
UNION ALL
SELECT 4, 'Contas pagas', COUNT(*) FROM contas WHERE status = 'PAGA'
UNION ALL
SELECT 5, 'Pagas sem nenhuma glosa', COUNT(*)
FROM contas c
WHERE c.status = 'PAGA'
  AND NOT EXISTS (SELECT 1 FROM glosas g WHERE g.conta_id = c.id)
ORDER BY ordem;


-- [glosa_por_convenio]
-- Qual convênio glosa mais (em % do valor cobrado)?
WITH glosa_conta AS (
    SELECT conta_id, SUM(valor_glosado) AS glosado FROM glosas GROUP BY conta_id
)
SELECT cv.nome                                                      AS convenio,
       COUNT(*)                                                     AS contas_pagas,
       ROUND(SUM(c.valor_cobrado), 2)                               AS faturado,
       ROUND(SUM(COALESCE(g.glosado, 0)), 2)                        AS glosado,
       ROUND(100.0 * SUM(COALESCE(g.glosado, 0)) / SUM(c.valor_cobrado), 2) AS taxa_glosa_pct
FROM contas c
JOIN atendimentos a     ON a.id = c.atendimento_id
JOIN convenios cv       ON cv.id = a.convenio_id
LEFT JOIN glosa_conta g ON g.conta_id = c.id
WHERE c.status = 'PAGA'
GROUP BY cv.nome
ORDER BY taxa_glosa_pct DESC;


-- [evolucao_mensal]
-- Faturado x glosado por mês de pagamento (ignora meses com poucas contas, no início da base).
WITH glosa_conta AS (
    SELECT conta_id, SUM(valor_glosado) AS glosado FROM glosas GROUP BY conta_id
)
SELECT DATE_FORMAT(c.data_pagamento, '%Y-%m')                       AS mes,
       COUNT(*)                                                     AS contas,
       ROUND(SUM(c.valor_cobrado), 2)                               AS faturado,
       ROUND(SUM(COALESCE(g.glosado, 0)), 2)                        AS glosado,
       ROUND(100.0 * SUM(COALESCE(g.glosado, 0)) / SUM(c.valor_cobrado), 2) AS taxa_glosa_pct
FROM contas c
LEFT JOIN glosa_conta g ON g.conta_id = c.id
WHERE c.status = 'PAGA'
GROUP BY DATE_FORMAT(c.data_pagamento, '%Y-%m')
HAVING COUNT(*) >= 20
ORDER BY mes;


-- [glosa_por_codigo]
-- Quantas glosas vêm só como "G99 - outros"? Essas exigem ler o texto livre (trabalho para a IA).
SELECT codigo_motivo,
       COUNT(*)                                          AS qtd,
       ROUND(SUM(valor_glosado), 2)                      AS valor,
       ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_qtd
FROM glosas
GROUP BY codigo_motivo
ORDER BY qtd DESC;


-- [glosa_evitavel]
-- Pergunta principal: quanto da glosa poderia ter sido evitado com uma auditoria
-- automática antes do envio (erros que as regras da vw_erros_detectados encontram)?
WITH item_com_erro AS (
    SELECT item_id, MIN(tipo_erro) AS tipo_erro
    FROM vw_erros_detectados
    GROUP BY item_id
),
glosa_classificada AS (
    SELECT g.valor_glosado,
           CASE
               WHEN e.item_id IS NOT NULL                       THEN e.tipo_erro
               WHEN g.item_id IS NULL AND pz.fora_do_prazo = 1  THEN 'PRAZO_EXPIRADO'
               ELSE 'NAO_DETECTAVEL_POR_REGRA'
           END AS causa
    FROM glosas g
    LEFT JOIN item_com_erro e  ON e.item_id = g.item_id
    LEFT JOIN vw_prazo_envio pz ON pz.conta_id = g.conta_id
)
SELECT causa,
       COUNT(*)                                                    AS glosas,
       ROUND(SUM(valor_glosado), 2)                                AS valor,
       ROUND(100.0 * SUM(valor_glosado) / SUM(SUM(valor_glosado)) OVER (), 1) AS pct_valor
FROM glosa_classificada
GROUP BY causa
ORDER BY valor DESC;


-- [pendencias_pre_envio]
-- Contas que AINDA NÃO foram enviadas e já têm erro detectado: dá para corrigir agora.
WITH erro_por_item AS (
    SELECT item_id, conta_id, MIN(tipo_erro) AS tipo_erro, MAX(valor_em_risco) AS valor_em_risco
    FROM vw_erros_detectados
    GROUP BY item_id, conta_id
)
SELECT e.tipo_erro,
       COUNT(DISTINCT e.conta_id)       AS contas,
       COUNT(*)                         AS itens,
       ROUND(SUM(e.valor_em_risco), 2)  AS valor_em_risco
FROM erro_por_item e
JOIN contas c ON c.id = e.conta_id
WHERE c.status IN ('ABERTA', 'FECHADA')
GROUP BY e.tipo_erro
ORDER BY valor_em_risco DESC;


-- [pendencias_pre_envio_detalhe]
-- Lista de trabalho para o time de faturamento: o que corrigir, em qual conta.
-- (um item pode cair em mais de uma regra; mostramos uma linha por item)
WITH erro_por_item AS (
    SELECT item_id, conta_id, MIN(tipo_erro) AS tipo_erro, MAX(valor_em_risco) AS valor_em_risco
    FROM vw_erros_detectados
    GROUP BY item_id, conta_id
)
SELECT c.id                       AS conta_id,
       cv.nome                    AS convenio,
       e.tipo_erro,
       p.descricao                AS item,
       i.quantidade,
       i.valor_unitario,
       pc.valor_contratado,
       e.valor_em_risco
FROM erro_por_item e
JOIN itens_conta i      ON i.id = e.item_id
JOIN contas c           ON c.id = e.conta_id
JOIN atendimentos a     ON a.id = c.atendimento_id
JOIN convenios cv       ON cv.id = a.convenio_id
JOIN procedimentos p    ON p.codigo = i.procedimento_codigo
JOIN precos_contrato pc ON pc.convenio_id = a.convenio_id
                       AND pc.procedimento_codigo = i.procedimento_codigo
WHERE c.status IN ('ABERTA', 'FECHADA')
ORDER BY e.valor_em_risco DESC;


-- [contas_paradas]
-- Contas fechadas e não enviadas há mais de 10 dias, ordenadas pelo prazo que resta.
SELECT c.id                                              AS conta_id,
       cv.nome                                           AS convenio,
       a.tipo,
       c.valor_cobrado,
       DATEDIFF(@hoje, c.data_fechamento)                AS dias_parada,
       cv.prazo_envio_dias - DATEDIFF(@hoje, a.data_alta) AS dias_restantes_prazo
FROM contas c
JOIN atendimentos a ON a.id = c.atendimento_id
JOIN convenios cv   ON cv.id = a.convenio_id
WHERE c.status = 'FECHADA'
  AND DATEDIFF(@hoje, c.data_fechamento) > 10
ORDER BY dias_restantes_prazo, c.valor_cobrado DESC;


-- [prazo_por_convenio]
-- Tempo médio entre a alta e o envio, e % de contas enviadas fora do prazo.
SELECT convenio,
       prazo_envio_dias,
       COUNT(*)                                 AS contas_enviadas,
       ROUND(AVG(dias_ate_envio), 1)            AS media_dias_ate_envio,
       SUM(fora_do_prazo)                       AS fora_do_prazo,
       ROUND(100.0 * SUM(fora_do_prazo) / COUNT(*), 1) AS pct_fora_do_prazo
FROM vw_prazo_envio
WHERE dias_ate_envio IS NOT NULL
GROUP BY convenio, prazo_envio_dias
ORDER BY pct_fora_do_prazo DESC;


-- [top_itens_glosados]
-- Os 3 itens com mais valor glosado em cada convênio (função de janela ROW_NUMBER).
WITH ranking AS (
    SELECT cv.nome AS convenio,
           p.descricao AS item,
           COUNT(*) AS glosas,
           ROUND(SUM(g.valor_glosado), 2) AS valor_glosado,
           ROW_NUMBER() OVER (PARTITION BY cv.nome ORDER BY SUM(g.valor_glosado) DESC) AS posicao
    FROM glosas g
    JOIN itens_conta i   ON i.id = g.item_id
    JOIN procedimentos p ON p.codigo = i.procedimento_codigo
    JOIN contas c        ON c.id = g.conta_id
    JOIN atendimentos a  ON a.id = c.atendimento_id
    JOIN convenios cv    ON cv.id = a.convenio_id
    GROUP BY cv.nome, p.descricao
)
SELECT convenio, posicao, item, glosas, valor_glosado
FROM ranking
WHERE posicao <= 3
ORDER BY convenio, posicao;


-- [glosas_para_planilha]
-- Exportação para o Google Sheets, onde a IA (Claude) classifica o texto livre de cada glosa.
SELECT g.id                          AS glosa_id,
       cv.nome                       AS convenio,
       COALESCE(p.descricao, '(conta inteira)') AS item,
       g.codigo_motivo,
       g.texto_glosa,
       g.valor_glosado
FROM glosas g
JOIN contas c            ON c.id = g.conta_id
JOIN atendimentos a      ON a.id = c.atendimento_id
JOIN convenios cv        ON cv.id = a.convenio_id
LEFT JOIN itens_conta i  ON i.id = g.item_id
LEFT JOIN procedimentos p ON p.codigo = i.procedimento_codigo
ORDER BY g.id;

-- [ticket_medio_por_tipo]
-- Valor médio das contas por tipo de atendimento.
SELECT a.tipo,
       COUNT(*)                       AS contas,
       ROUND(AVG(c.valor_cobrado), 2) AS ticket_medio
FROM contas c
JOIN atendimentos a ON a.id = c.atendimento_id
GROUP BY a.tipo
ORDER BY ticket_medio DESC;