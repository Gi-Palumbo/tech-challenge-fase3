"""Valida o mapeamento canonico contra os CSVs brutos das 3 edicoes.

Este e o primeiro script a rodar depois de baixar as bases do Kaggle. Ele nao
transforma dados: le apenas os cabecalhos e informa, por edicao, qual coluna foi
resolvida para cada campo canonico, o que nao foi encontrado e o que nao se
aplica aquela edicao. Ajuste config/mapeamento_colunas.json ate nao restar
campo critico faltando.

Uso:
    python scripts/00_explorar_schema.py
    python scripts/00_explorar_schema.py --dir-raw data/raw
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ / "src"))

from sod import mapeamento as m  # noqa: E402

csv.field_size_limit(10_000_000)


def localizar_csv(dir_raw: Path, ano: int) -> Path | None:
    """Localiza o CSV da edicao pelo ano presente no nome do arquivo."""
    candidatos = [p for p in sorted(dir_raw.glob("*.csv")) if str(ano) in p.name]
    return candidatos[0] if candidatos else None


def ler_cabecalho(caminho: Path) -> list[str]:
    """Le apenas a primeira linha do CSV, respeitando aspas e virgulas internas."""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with caminho.open("r", encoding=encoding, newline="") as f:
                return next(csv.reader(f))
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"Nao foi possivel decodificar {caminho}")


def contar_linhas(caminho: Path) -> int:
    with caminho.open("r", encoding="utf-8-sig", errors="replace", newline="") as f:
        return max(0, sum(1 for _ in f) - 1)


def relatar_edicao(ano: int, caminho: Path, config: dict) -> dict:
    cabecalhos = ler_cabecalho(caminho)
    plano = m.montar_plano_colunas(cabecalhos, config, ano)
    criticos = set(config.get("campos_criticos", []))

    print(f"\n{'=' * 96}")
    print(f"EDICAO {ano} | {caminho.name}")
    print(f"colunas: {len(cabecalhos)} | registros: {contar_linhas(caminho)}")

    print("\ncampos resolvidos:")
    for grupo in m.GRUPOS:
        for nome, coluna in plano[grupo].items():
            col = m.parse_cabecalho(coluna)
            marca = "*" if f"{grupo}.{nome}" in criticos else " "
            print(f"  {marca} {grupo[:4]}.{nome:<24} {col.codigo_normalizado:<7} {col.rotulo[:52]}")

    if plano["nao_aplicavel"]:
        print("\nnao aplicavel a esta edicao (questao inexistente, ausencia esperada):")
        for nome in plano["nao_aplicavel"]:
            print(f"    {nome}")

    if plano["faltando"]:
        print("\nNAO ENCONTRADOS (codigo mapeado nao existe no CSV):")
        for nome in plano["faltando"]:
            marca = "[CRITICO]" if nome in criticos else "         "
            print(f"    {marca} {nome}")

    return {"ano": ano, "arquivo": caminho.name, "plano": plano, "cabecalhos": cabecalhos}


def salvar_inventario(resultados: list[dict], destino: Path) -> None:
    """Grava o inventario completo de colunas, util para anexo do trabalho."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["ano", "codigo_questao", "rotulo", "cabecalho_original"])
        for r in resultados:
            for cab in r["cabecalhos"]:
                col = m.parse_cabecalho(cab)
                w.writerow([r["ano"], col.codigo_normalizado, col.rotulo, cab])
    print(f"\ninventario de colunas salvo em {destino}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir-raw", default=str(RAIZ / "data" / "raw"))
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    dir_raw = Path(args.dir_raw)
    config = m.carregar_config(args.config)
    criticos = set(config.get("campos_criticos", []))

    resultados = []
    ausentes = []
    for edicao in config["edicoes"]:
        ano = int(edicao["ano"])
        caminho = localizar_csv(dir_raw, ano)
        if caminho is None:
            ausentes.append(ano)
            continue
        resultados.append(relatar_edicao(ano, caminho, config))

    if ausentes:
        print(f"\nSem CSV para as edicoes {ausentes} em {dir_raw}.")
        print("O nome do arquivo precisa conter o ano da edicao (ver README).")
    if not resultados:
        return 1

    salvar_inventario(resultados, RAIZ / "data" / "inventario_colunas.csv")

    print(f"\n{'=' * 96}\nRESUMO")
    pendentes = {}
    for r in resultados:
        faltando_criticos = [c for c in r["plano"]["faltando"] if c in criticos]
        total = sum(len(r["plano"][g]) for g in m.GRUPOS)
        print(f"  {r['ano']}: {total} campos resolvidos, {len(r['plano']['faltando'])} nao encontrados")
        if faltando_criticos:
            pendentes[r["ano"]] = faltando_criticos

    if pendentes:
        print("\nATENCAO: campos criticos nao resolvidos. Ajuste config/mapeamento_colunas.json:")
        for ano, campos in pendentes.items():
            print(f"  {ano}: {', '.join(campos)}")
        return 2

    print("\nTodos os campos criticos foram resolvidos nas edicoes encontradas.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

