"""
Conexão com o MySQL e leitura das consultas nomeadas de sql/03_analises.sql.

Configure a conexão por variáveis de ambiente (ou edite os valores padrão):
    MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD, MYSQL_DATABASE
"""

import os
import re
from decimal import Decimal
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
PASTA_SQL = RAIZ / "sql"
DATA_REFERENCIA = "2026-10-15"   # "hoje" da base fictícia (numa base real: date.today())
NOME_BANCO = os.getenv("MYSQL_DATABASE", "auditoria_glosas")


def conectar(com_banco=True):
    import pymysql  # importado aqui para os outros módulos funcionarem sem o driver instalado

    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=NOME_BANCO if com_banco else None,
        charset="utf8mb4",
        autocommit=True,
        local_infile=False,
    )


def carregar_consultas(arquivo=PASTA_SQL / "03_analises.sql"):
    """Lê o arquivo .sql e devolve {nome: sql} usando os marcadores '-- [nome]'."""
    texto = Path(arquivo).read_text(encoding="utf-8")
    partes = re.split(r"^-- \[(\w+)\]\s*$", texto, flags=re.M)
    # partes = [cabeçalho, nome1, sql1, nome2, sql2, ...]
    return {nome: sql.strip().rstrip(";") for nome, sql in zip(partes[1::2], partes[2::2])}


CONSULTAS = carregar_consultas()
_conexao = None


def consultar(nome):
    """Executa uma consulta nomeada e devolve um DataFrame."""
    global _conexao
    if _conexao is None:
        _conexao = conectar()
    with _conexao.cursor() as cur:
        cur.execute("SET @hoje = %s", (DATA_REFERENCIA,))
        cur.execute(CONSULTAS[nome])
        colunas = [c[0] for c in cur.description]
        linhas = cur.fetchall()
    df = pd.DataFrame(linhas, columns=colunas)
    # O MySQL devolve DECIMAL como Decimal; convertemos para float para facilitar contas e gráficos
    for col in df.columns:
        if df[col].map(lambda v: isinstance(v, Decimal)).any():
            df[col] = df[col].astype(float)
    return df
