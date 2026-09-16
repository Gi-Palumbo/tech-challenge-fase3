"""Pipeline local em pandas - espelha a logica dos Glue Jobs.

Serve para iterar rapido na sua maquina (sem custo e sem sessao do AWS Academy)
usando exatamente as mesmas regras de negocio de src/sod/mapeamento.py.
A entrega oficial continua sendo a execucao nos Glue Jobs; este script e para
desenvolvimento, conferencia de resultados e geracao dos graficos.

Uso:
    python scripts/local/pipeline_local.py
    python scripts/local/pipeline_local.py --dir-raw data/raw --dir-saida data
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ / "src"))

from sod import mapeamento as m  # noqa: E402

# Mesmos recortes do Glue Job 2 (scripts/glue/job_02_silver_para_gold.py), para
# que a Gold local e a Gold da AWS sejam comparaveis.
RECORTES_REMUNERACAO = {
    "senioridade": ["senioridade"],
    "cargo": ["cargo"],
    "cargo_senioridade": ["cargo", "senioridade"],
    "regiao": ["regiao"],
    "regiao_senioridade": ["regiao", "senioridade"],
    "forma_trabalho": ["forma_trabalho"],
    "forma_trabalho_senioridade": ["forma_trabalho", "senioridade"],
    "nivel_ensino": ["nivel_ensino"],
    "tempo_experiencia_dados": ["tempo_experiencia_dados"],
    "genero": ["genero"],
    "setor_empresa": ["setor_empresa"],
}


def localizar_csv(dir_raw: Path, ano: int) -> Path | None:
    """Localiza o CSV da edicao pelo ano presente no nome do arquivo."""
    candidatos = [p for p in sorted(dir_raw.glob("*.csv")) if str(ano) in p.name]
    return candidatos[0] if candidatos else None


def ler_csv(caminho: Path) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(caminho, encoding=encoding, low_memory=False)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError(f"Nao foi possivel decodificar {caminho}")


def construir_silver(dir_raw: Path, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    mapa_regioes = config["regiao_por_uf"]
    respondentes: list[pd.DataFrame] = []
    tecnologias: list[pd.DataFrame] = []

    for edicao in config["edicoes"]:
        ano = int(edicao["ano"])
        caminho = localizar_csv(dir_raw, ano)
        if caminho is None:
            print(f"[{ano}] AVISO: nenhum CSV encontrado, edicao ignorada.")
            continue

        bruto = ler_csv(caminho)
        plano = m.montar_plano_colunas(list(bruto.columns), config, ano)
        print(f"[{ano}] {caminho.name}: {len(bruto)} linhas, {len(bruto.columns)} colunas")
        if plano["faltando"]:
            print(f"[{ano}] NAO ENCONTRADOS: {plano['faltando']}")
        if plano["nao_aplicavel"]:
            print(f"[{ano}] nao aplicavel a esta edicao: {plano['nao_aplicavel']}")

        ids = pd.Series([f"{ano}-{i}" for i in range(len(bruto))], index=bruto.index)
        df = pd.DataFrame({"ano": ano, "id_respondente": ids})

        for nome, coluna in plano["campos"].items():
            df[nome] = bruto[coluna].astype("string").str.strip()

        # Derivacoes e padronizacoes do modelo canonico.
        if "idade" in df:
            df["idade"] = pd.to_numeric(df["idade"], errors="coerce").astype("Int64")
        if "faixa_salarial" in df:
            df["salario_mensal_estimado"] = df["faixa_salarial"].map(m.salario_medio_da_faixa)
            # Limites da faixa: insumo da mediana interpolada na camada Gold.
            limites = df["faixa_salarial"].map(m.limites_da_faixa)
            df["faixa_inferior"] = [l[0] for l in limites]
            df["faixa_superior"] = [l[1] for l in limites]
        if "senioridade" in df:
            df["senioridade"] = df["senioridade"].map(m.padronizar_senioridade)
        if "forma_trabalho" in df:
            df["forma_trabalho"] = df["forma_trabalho"].map(m.padronizar_forma_trabalho)
        if "forma_trabalho_ideal" in df:
            df["forma_trabalho_ideal"] = df["forma_trabalho_ideal"].map(m.padronizar_forma_trabalho)
        if "genero" in df:
            df["genero"] = df["genero"].map(m.padronizar_genero)

        # A pesquisa ja traz a regiao; a UF e usada apenas como fallback.
        regiao_origem = df["regiao"] if "regiao" in df else pd.Series(pd.NA, index=df.index)
        uf_origem = df["uf_moradia"] if "uf_moradia" in df else pd.Series(pd.NA, index=df.index)
        df["regiao"] = [
            m.padronizar_regiao(r, u, mapa_regioes) for r, u in zip(regiao_origem, uf_origem)
        ]

        for nome, coluna in plano["binarios"].items():
            df[nome] = bruto[coluna].map(m.resposta_binaria).astype("Int64")

        # Gestores nao respondem a questao de nivel: a senioridade deles vem
        # vazia por desenho do questionario e e completada aqui.
        if "senioridade" in df and "atua_como_gestor" in df:
            df["senioridade"] = [
                m.senioridade_com_gestao(s, g)
                for s, g in zip(df["senioridade"], df["atua_como_gestor"])
            ]

        coluna_ia = plano["ia"].get("uso_ia_pessoal")
        if coluna_ia is not None:
            df["usa_ia"] = bruto[coluna_ia].map(m.usa_ia).astype("Int64")
            df["tipo_uso_ia"] = bruto[coluna_ia].map(m.tipo_uso_ia).astype("string")
        for nome in ("tipo_uso_ia_empresa", "ia_prioridade_empresa"):
            coluna = plano["ia"].get(nome)
            if coluna is not None:
                df[nome] = bruto[coluna].astype("string").str.strip()

        respondentes.append(df)

        for categoria, coluna in plano["tecnologias"].items():
            explodido = (
                pd.DataFrame(
                    {
                        "ano": ano,
                        "id_respondente": ids,
                        "categoria": categoria,
                        "tecnologia": bruto[coluna].map(m.separar_multivalorado),
                    }
                )
                .explode("tecnologia")
                .dropna(subset=["tecnologia"])
            )
            tecnologias.append(explodido)

    if not respondentes:
        raise SystemExit("Nenhuma edicao processada. Verifique os CSVs em data/raw.")

    silver_resp = pd.concat(respondentes, ignore_index=True)
    silver_tec = (
        pd.concat(tecnologias, ignore_index=True) if tecnologias else pd.DataFrame(columns=["ano"])
    )
    return silver_resp, silver_tec


def _mediana_interpolada(grupo: pd.DataFrame) -> float | None:
    """Mediana interpolada da faixa salarial para um grupo de respondentes.

    A mediana do ponto medio da faixa e cega: ela devolve sempre o centro da
    faixa mediana, fazendo grupos distintos exibirem valores identicos. Aqui as
    faixas sao reconstruidas em bandas e a mediana e estimada por interpolacao.
    """
    valido = grupo.dropna(subset=["faixa_inferior"])
    if valido.empty:
        return None
    bandas = (
        valido.groupby(["faixa_inferior", "faixa_superior"], dropna=False)
        .size()
        .reset_index(name="n")
    )
    return m.mediana_interpolada(
        [
            (r.faixa_inferior, None if pd.isna(r.faixa_superior) else r.faixa_superior, int(r.n))
            for r in bandas.itertuples()
        ]
    )


def construir_gold(resp: pd.DataFrame, tec: pd.DataFrame, min_resp: int) -> dict[str, pd.DataFrame]:
    gold: dict[str, pd.DataFrame] = {}

    perfil = (
        resp.groupby(["ano", "cargo", "senioridade"], dropna=False)
        .agg(respondentes=("id_respondente", "count"), idade_media=("idade", "mean"))
        .reset_index()
    )
    perfil["percentual"] = (
        100 * perfil["respondentes"] / perfil.groupby("ano")["respondentes"].transform("sum")
    ).round(2)
    gold["perfil_mercado"] = perfil.sort_values(["ano", "respondentes"], ascending=[True, False])

    com_salario = resp[resp["salario_mensal_estimado"].notna()]
    partes = []
    for recorte, dimensoes in RECORTES_REMUNERACAO.items():
        if any(d not in resp.columns for d in dimensoes):
            print(f"  recorte '{recorte}' ignorado: dimensao ausente na Silver")
            continue
        agregado = (
            com_salario.groupby(["ano", *dimensoes], dropna=False)
            .agg(
                respondentes=("id_respondente", "count"),
                salario_mediano=("salario_mensal_estimado", "median"),
                salario_medio=("salario_mensal_estimado", "mean"),
                p25=("salario_mensal_estimado", lambda s: s.quantile(0.25)),
                p75=("salario_mensal_estimado", lambda s: s.quantile(0.75)),
            )
            .reset_index()
        )
        interpolada = (
            com_salario.groupby(["ano", *dimensoes], dropna=False)
            .apply(_mediana_interpolada, include_groups=False)
            .rename("salario_mediano_interpolado")
            .reset_index()
        )
        agregado = agregado.merge(interpolada, on=["ano", *dimensoes], how="left")

        agregado["recorte"] = recorte
        agregado["dimensao_1"] = agregado[dimensoes[0]].astype("string")
        agregado["dimensao_2"] = (
            agregado[dimensoes[1]].astype("string") if len(dimensoes) > 1 else pd.NA
        )
        partes.append(
            agregado[
                [
                    "ano", "recorte", "dimensao_1", "dimensao_2", "respondentes",
                    "salario_mediano_interpolado", "salario_mediano", "salario_medio", "p25", "p75",
                ]
            ]
        )

    remuneracao = pd.concat(partes, ignore_index=True)
    remuneracao["amostra_suficiente"] = remuneracao["respondentes"] >= min_resp
    gold["remuneracao"] = remuneracao.sort_values(
        ["ano", "recorte", "salario_mediano_interpolado"], ascending=[True, True, False]
    )

    diversidade = (
        resp.groupby(["ano", "genero", "senioridade"], dropna=False)
        .agg(
            respondentes=("id_respondente", "count"),
            salario_medio=("salario_mensal_estimado", "mean"),
        )
        .reset_index()
    )
    interpolada_div = (
        resp.groupby(["ano", "genero", "senioridade"], dropna=False)
        .apply(_mediana_interpolada, include_groups=False)
        .rename("salario_mediano_interpolado")
        .reset_index()
    )
    diversidade = diversidade.merge(
        interpolada_div, on=["ano", "genero", "senioridade"], how="left"
    )
    diversidade["percentual"] = (
        100
        * diversidade["respondentes"]
        / diversidade.groupby(["ano", "senioridade"])["respondentes"].transform("sum")
    ).round(2)
    gold["diversidade"] = diversidade

    if not tec.empty and "categoria" in tec.columns:
        # O denominador da taxa de adocao e quem RESPONDEU aquela questao, nao o
        # total da edicao: a cobertura de resposta cai de 71% (2023) para 60%
        # (2025) e usar o total faria todas as tecnologias parecerem perder
        # adocao cerca de 11 pontos por artefato de base.
        base_cat = (
            tec.groupby(["ano", "categoria"])["id_respondente"]
            .nunique()
            .rename("base_resposta")
            .reset_index()
        )
        # Itens por respondente expoe mudanca de formato da questao (escolha
        # unica vs multipla): sem isso, a serie historica compara coisas
        # diferentes. linguagem_preferida passou de 1,0 para 2,0 item em 2025.
        itens = (
            tec.groupby(["ano", "categoria"])
            .size()
            .rename("total_mencoes")
            .reset_index()
            .merge(base_cat, on=["ano", "categoria"])
        )
        itens["itens_por_respondente"] = (
            itens["total_mencoes"] / itens["base_resposta"]
        ).round(2)

        total_ano = resp.groupby("ano")["id_respondente"].nunique().rename("total_respondentes")
        tecnologias = (
            tec.groupby(["ano", "categoria", "tecnologia"])["id_respondente"]
            .nunique()
            .rename("respondentes")
            .reset_index()
            .merge(base_cat, on=["ano", "categoria"])
            .merge(itens[["ano", "categoria", "itens_por_respondente"]], on=["ano", "categoria"])
            .join(total_ano, on="ano")
        )
        tecnologias["taxa_adocao"] = (
            100 * tecnologias["respondentes"] / tecnologias["base_resposta"]
        ).round(2)
        tecnologias["posicao"] = (
            tecnologias.groupby(["ano", "categoria"])["respondentes"]
            .rank(ascending=False, method="first")
            .astype(int)
        )
        gold["tecnologias"] = tecnologias.sort_values(["ano", "categoria", "posicao"])

    if "usa_ia" in resp.columns:
        ia = (
            resp.groupby(["ano", "senioridade"], dropna=False)
            .agg(
                respondentes=("id_respondente", "count"),
                base_resposta=("usa_ia", "count"),
                taxa_adocao_ia=("usa_ia", "mean"),
            )
            .reset_index()
        )
        ia["taxa_adocao_ia"] = (100 * ia["taxa_adocao_ia"]).round(2)
        gold["adocao_ia"] = ia

        # Impacto: compara quem usa e quem nao usa IA, controlando senioridade.
        base_ia = resp[resp["usa_ia"].notna() & resp["salario_mensal_estimado"].notna()]
        if not base_ia.empty:
            impacto = (
                base_ia.groupby(["ano", "senioridade", "usa_ia"], dropna=False)
                .agg(
                    respondentes=("id_respondente", "count"),
                    salario_medio=("salario_mensal_estimado", "mean"),
                )
                .reset_index()
            )
            interpolada_ia = (
                base_ia.groupby(["ano", "senioridade", "usa_ia"], dropna=False)
                .apply(_mediana_interpolada, include_groups=False)
                .rename("salario_mediano_interpolado")
                .reset_index()
            )
            impacto = impacto.merge(
                interpolada_ia, on=["ano", "senioridade", "usa_ia"], how="left"
            )
            impacto["grupo"] = impacto["usa_ia"].map({1: "Usa IA", 0: "Nao usa IA"})
            impacto["amostra_suficiente"] = impacto["respondentes"] >= min_resp
            gold["impacto_ia"] = impacto

    modelo = (
        resp.groupby(["ano", "regiao", "forma_trabalho"], dropna=False)
        .agg(
            respondentes=("id_respondente", "count"),
            salario_medio=("salario_mensal_estimado", "mean"),
        )
        .reset_index()
    )
    interpolada_mod = (
        resp.groupby(["ano", "regiao", "forma_trabalho"], dropna=False)
        .apply(_mediana_interpolada, include_groups=False)
        .rename("salario_mediano_interpolado")
        .reset_index()
    )
    modelo = modelo.merge(interpolada_mod, on=["ano", "regiao", "forma_trabalho"], how="left")
    modelo["percentual"] = (
        100
        * modelo["respondentes"]
        / modelo.groupby(["ano", "regiao"])["respondentes"].transform("sum")
    ).round(2)
    gold["modelo_trabalho"] = modelo

    return gold


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir-raw", default=str(RAIZ / "data" / "raw"))
    ap.add_argument("--dir-saida", default=str(RAIZ / "data"))
    ap.add_argument("--min-respondentes", type=int, default=30)
    args = ap.parse_args()

    dir_raw, dir_saida = Path(args.dir_raw), Path(args.dir_saida)
    config = m.carregar_config()

    print("=== Bronze -> Silver ===")
    silver_resp, silver_tec = construir_silver(dir_raw, config)

    dir_silver = dir_saida / "silver"
    dir_silver.mkdir(parents=True, exist_ok=True)
    silver_resp.to_csv(dir_silver / "respondentes.csv", index=False, encoding="utf-8-sig")
    silver_tec.to_csv(dir_silver / "tecnologias.csv", index=False, encoding="utf-8-sig")
    print(f"silver/respondentes: {len(silver_resp)} linhas, {len(silver_resp.columns)} colunas")
    print(f"silver/tecnologias:  {len(silver_tec)} linhas")

    print("\n=== Silver -> Gold ===")
    gold = construir_gold(silver_resp, silver_tec, args.min_respondentes)
    dir_gold = dir_saida / "gold"
    dir_gold.mkdir(parents=True, exist_ok=True)
    for nome, df in gold.items():
        df.to_csv(dir_gold / f"{nome}.csv", index=False, encoding="utf-8-sig")
        print(f"gold/{nome}: {len(df)} linhas")

    print(f"\nConcluido. Saidas em {dir_silver} e {dir_gold}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
