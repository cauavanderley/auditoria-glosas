"""
Roda TODAS as consultas nomeadas de sql/03_analises.sql e mostra quantas linhas cada uma devolveu.
Serve de teste rápido: se alguma consulta tiver erro de SQL, o script falha (e o CI fica vermelho).

Uso:
    python scripts/testar_consultas.py
"""

import sys

import db


def main():
    falhas = 0
    for nome in db.CONSULTAS:
        try:
            df = db.consultar(nome)
            print(f"  OK    {nome:<32} {len(df):>5} linhas")
        except Exception as erro:  # mostra o erro e segue testando as outras
            falhas += 1
            print(f"  ERRO  {nome:<32} {erro}")
    print(f"\n{len(db.CONSULTAS) - falhas} de {len(db.CONSULTAS)} consultas funcionaram.")
    sys.exit(1 if falhas else 0)


if __name__ == "__main__":
    main()
