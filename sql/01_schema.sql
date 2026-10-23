-- =====================================================================
-- Auditoria de Glosas | Esquema do banco (MySQL 8)
-- Base FICTÍCIA de faturamento hospitalar: atendimento -> conta -> itens -> glosas
-- =====================================================================

DROP TABLE IF EXISTS glosas;
DROP TABLE IF EXISTS itens_conta;
DROP TABLE IF EXISTS contas;
DROP TABLE IF EXISTS atendimentos;
DROP TABLE IF EXISTS precos_contrato;
DROP TABLE IF EXISTS procedimentos;
DROP TABLE IF EXISTS convenios;

-- Operadoras de saúde (planos) com quem o hospital tem contrato
CREATE TABLE convenios (
    id               INT PRIMARY KEY,
    nome             VARCHAR(60) NOT NULL,
    prazo_envio_dias INT NOT NULL            -- prazo máximo entre a alta e o envio da conta
);

-- Catálogo de itens que podem ser cobrados
CREATE TABLE procedimentos (
    codigo            VARCHAR(10) PRIMARY KEY,
    descricao         VARCHAR(100) NOT NULL,
    grupo             VARCHAR(30) NOT NULL,
    valor_referencia  DECIMAL(10,2) NOT NULL,
    exige_autorizacao TINYINT(1) NOT NULL    -- 1 = precisa de guia autorizada pelo convênio
);

-- Preço negociado de cada item em cada contrato
CREATE TABLE precos_contrato (
    convenio_id         INT NOT NULL,
    procedimento_codigo VARCHAR(10) NOT NULL,
    valor_contratado    DECIMAL(10,2) NOT NULL,
    PRIMARY KEY (convenio_id, procedimento_codigo),
    FOREIGN KEY (convenio_id) REFERENCES convenios(id),
    FOREIGN KEY (procedimento_codigo) REFERENCES procedimentos(codigo)
);

-- Passagem do paciente pelo hospital
CREATE TABLE atendimentos (
    id           INT PRIMARY KEY,
    paciente     VARCHAR(10) NOT NULL,       -- identificador anônimo
    convenio_id  INT NOT NULL,
    tipo         VARCHAR(30) NOT NULL,
    setor        VARCHAR(30) NOT NULL,
    data_entrada DATE NOT NULL,
    data_alta    DATE NOT NULL,
    FOREIGN KEY (convenio_id) REFERENCES convenios(id),
    INDEX idx_atend_convenio (convenio_id)
);

-- Conta médica: o que o hospital cobra do convênio por um atendimento
CREATE TABLE contas (
    id              INT PRIMARY KEY,
    atendimento_id  INT NOT NULL,
    status          VARCHAR(10) NOT NULL,    -- ABERTA > FECHADA > ENVIADA > PAGA
    data_fechamento DATE NULL,
    data_envio      DATE NULL,
    data_pagamento  DATE NULL,
    valor_cobrado   DECIMAL(12,2) NOT NULL,
    valor_pago      DECIMAL(12,2) NULL,
    FOREIGN KEY (atendimento_id) REFERENCES atendimentos(id),
    INDEX idx_conta_status (status)
);

-- Itens cobrados em cada conta
CREATE TABLE itens_conta (
    id                  INT PRIMARY KEY,
    conta_id            INT NOT NULL,
    procedimento_codigo VARCHAR(10) NOT NULL,
    quantidade          INT NOT NULL,
    valor_unitario      DECIMAL(10,2) NOT NULL,
    numero_guia         VARCHAR(12) NULL,    -- autorização do convênio (quando exigida)
    data_execucao       DATE NOT NULL,
    FOREIGN KEY (conta_id) REFERENCES contas(id),
    FOREIGN KEY (procedimento_codigo) REFERENCES procedimentos(codigo),
    INDEX idx_item_conta (conta_id)
);

-- Glosas: valores que o convênio se recusou a pagar
CREATE TABLE glosas (
    id            INT PRIMARY KEY,
    conta_id      INT NOT NULL,
    item_id       INT NULL,                  -- NULL = glosa da conta inteira
    codigo_motivo VARCHAR(5) NOT NULL,       -- G99 = "outros" (motivo só no texto livre)
    texto_glosa   VARCHAR(255) NOT NULL,
    valor_glosado DECIMAL(12,2) NOT NULL,
    data_glosa    DATE NOT NULL,
    FOREIGN KEY (conta_id) REFERENCES contas(id),
    FOREIGN KEY (item_id) REFERENCES itens_conta(id)
);
