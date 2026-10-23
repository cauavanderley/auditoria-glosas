"""
Cria o banco no MySQL, as tabelas e as views, e carrega os CSVs de dados/csv/.

Uso:
    python scripts/carregar_mysql.py
"""

import csv
import re

import db

ORDEM_TABELAS = ["convenios", "procedimentos", "precos_contrato", "atendimentos",
                 "contas", "itens_conta", "glosas"]


def executar_arquivo_sql(cur, caminho):
    texto = caminho.read_text(encoding="utf-8")
    texto = re.sub(r"^\s*--.*$", "", texto, flags=re.M)        # remove comentários de linha
    for comando in texto.split(";"):
        if comando.strip():
            cur.execute(comando)


def main():
    conn = db.conectar(com_banco=False)
    with conn.cursor() as cur:
        cur.execute(f"CREATE DATABASE IF NOT EXISTS {db.NOME_BANCO} "
                    "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        cur.execute(f"USE {db.NOME_BANCO}")
        executar_arquivo_sql(cur, db.PASTA_SQL / "01_schema.sql")
        print("Tabelas criadas.")

        for tabela in ORDEM_TABELAS:
            with open(db.RAIZ / "dados" / "csv" / f"{tabela}.csv", encoding="utf-8") as f:
                leitor = csv.reader(f)
                colunas = next(leitor)
                linhas = [[v if v != "" else None for v in linha] for linha in leitor]
            marcadores = ", ".join(["%s"] * len(colunas))
            cur.executemany(
                f"INSERT INTO {tabela} ({', '.join(colunas)}) VALUES ({marcadores})", linhas)
            print(f"  {tabela:<16} {len(linhas):>6} linhas")

        executar_arquivo_sql(cur, db.PASTA_SQL / "02_views.sql")
        print("Views criadas. Banco pronto!")
    conn.close()


if __name__ == "__main__":
    main()
