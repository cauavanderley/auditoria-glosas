-- =====================================================================
-- Views de auditoria: regras que encontram erros ANTES do convênio glosar
-- =====================================================================

-- Cada linha = um item com problema detectável por regra, e quanto dinheiro está em risco.
DROP VIEW IF EXISTS vw_erros_detectados;
CREATE VIEW vw_erros_detectados AS
-- Regra 1: preço cobrado diferente do preço negociado no contrato
SELECT i.id AS item_id,
       i.conta_id,
       'PRECO_DIVERGENTE' AS tipo_erro,
       ROUND((i.valor_unitario - pc.valor_contratado) * i.quantidade, 2) AS valor_em_risco
FROM itens_conta i
JOIN contas c           ON c.id = i.conta_id
JOIN atendimentos a     ON a.id = c.atendimento_id
JOIN precos_contrato pc ON pc.convenio_id = a.convenio_id
                       AND pc.procedimento_codigo = i.procedimento_codigo
WHERE i.valor_unitario <> pc.valor_contratado

UNION ALL
-- Regra 2: item que exige autorização prévia, mas está sem número de guia
SELECT i.id, i.conta_id, 'SEM_AUTORIZACAO', ROUND(i.quantidade * i.valor_unitario, 2)
FROM itens_conta i
JOIN procedimentos p ON p.codigo = i.procedimento_codigo
WHERE p.exige_autorizacao = 1
  AND i.numero_guia IS NULL

UNION ALL
-- Regra 3: mesmo item lançado mais de uma vez (mesma conta, data, quantidade e preço).
-- O 1º lançamento é considerado válido; os seguintes são os suspeitos.
SELECT d.id, d.conta_id, 'DUPLICIDADE', ROUND(d.quantidade * d.valor_unitario, 2)
FROM (
    SELECT i.*,
           ROW_NUMBER() OVER (
               PARTITION BY i.conta_id, i.procedimento_codigo, i.data_execucao,
                            i.quantidade, i.valor_unitario
               ORDER BY i.id) AS ordem
    FROM itens_conta i
) d
WHERE d.ordem > 1;


-- Situação de cada conta em relação ao prazo de envio do contrato
DROP VIEW IF EXISTS vw_prazo_envio;
CREATE VIEW vw_prazo_envio AS
SELECT c.id AS conta_id,
       cv.nome AS convenio,
       cv.prazo_envio_dias,
       DATEDIFF(c.data_envio, a.data_alta) AS dias_ate_envio,
       CASE WHEN c.data_envio IS NOT NULL
             AND DATEDIFF(c.data_envio, a.data_alta) > cv.prazo_envio_dias
            THEN 1 ELSE 0 END AS fora_do_prazo
FROM contas c
JOIN atendimentos a ON a.id = c.atendimento_id
JOIN convenios cv   ON cv.id = a.convenio_id;
