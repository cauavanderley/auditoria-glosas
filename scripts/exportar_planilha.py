"""
Exporta as glosas para importar no Google Sheets (aba "glosas"), onde o Apps Script
usa o Claude para classificar o texto livre de cada glosa.

Uso:
    python scripts/exportar_planilha.py    # cria saida/glosas_para_planilha.csv
"""

import db


def main():
    df = db.consultar("glosas_para_planilha")
    saida = db.RAIZ / "saida"
    saida.mkdir(exist_ok=True)
    arquivo = saida / "glosas_para_planilha.csv"
    df.to_csv(arquivo, index=False, encoding="utf-8")
    print(f"{len(df)} glosas exportadas para {arquivo}")
    print("Importe também dados/csv/glosas_gabarito.csv numa aba chamada 'gabarito'.")


if __name__ == "__main__":
    main()
