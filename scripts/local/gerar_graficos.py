"""Gera os graficos da apresentacao a partir da camada Gold.

Le os CSVs de data/gold (produzidos pelo pipeline local ou exportados do Athena)
e grava PNGs em data/graficos, prontos para colar no material executivo.

A metrica de remuneracao usada e a MEDIANA INTERPOLADA, nao a mediana simples:
a pesquisa coleta renda em faixas, e a mediana do ponto medio da faixa devolve
o mesmo valor para grupos diferentes (todas as regioes davam R$ 10.000).

Uso:
    python scripts/local/gerar_graficos.py
    python scripts/local/gerar_graficos.py --dir-gold data/gold --dir-saida data/graficos
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

RAIZ = Path(__file__).resolve().parents[2]

PALETA = ["#1f4e79", "#2e75b6", "#9dc3e6", "#f4b183", "#c55a11", "#7f7f7f"]
ORDEM_SENIORIDADE = ["Junior", "Pleno", "Senior", "Especialista", "Gestao"]
# Categorias de tecnologia com formato de questao estavel nas 3 edicoes, e
# portanto validas para comparacao ao longo do tempo.
CATEGORIAS_COMPARAVEIS = ("banco_dados", "cloud_uso", "cloud_preferida", "ferramenta_bi")
METRICA_SALARIO = "salario_mediano_interpolado"
ROTULO_SALARIO = "R$ / mes (mediana interpolada)"

plt.rcParams.update({"figure.autolayout": True, "axes.grid": True, "grid.alpha": 0.3})


def carregar(dir_gold: Path, nome: str) -> pd.DataFrame | None:
    caminho = dir_gold / f"{nome}.csv"
    if not caminho.exists():
        print(f"  (pulando {nome}: {caminho.name} nao encontrado)")
        return None
    return pd.read_csv(caminho)


def salvar(fig, dir_saida: Path, nome: str) -> None:
    destino = dir_saida / f"{nome}.png"
    fig.savefig(destino, dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"  gerado {destino.name}")


def ordenar_senioridade(valores) -> list[str]:
    return [s for s in ORDEM_SENIORIDADE if s in list(valores)]


def _recorte(df: pd.DataFrame, nome: str, so_amostra_suficiente: bool = True) -> pd.DataFrame:
    """Filtra a Gold de remuneracao (formato longo) por recorte."""
    base = df[df["recorte"] == nome]
    if so_amostra_suficiente and "amostra_suficiente" in base.columns:
        filtrado = base[base["amostra_suficiente"].astype(bool)]
        # Se o corte de amostra zerar o recorte, e melhor mostrar tudo e
        # sinalizar a limitacao no slide do que entregar um grafico vazio.
        if not filtrado.empty:
            return filtrado
    return base


# --- Perfil do mercado ---

def grafico_perfil_por_senioridade(df: pd.DataFrame, dir_saida: Path) -> None:
    pivot = df.groupby(["ano", "senioridade"])["respondentes"].sum().unstack(fill_value=0)
    colunas = ordenar_senioridade(pivot.columns)
    if not colunas:
        return
    pct = 100 * pivot[colunas].div(pivot[colunas].sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    pct.plot(kind="bar", stacked=True, ax=ax, color=PALETA)
    ax.set_title("Composicao do mercado por senioridade")
    ax.set_xlabel("Ano da pesquisa")
    ax.set_ylabel("% dos respondentes")
    ax.legend(title="Senioridade", bbox_to_anchor=(1.02, 1), loc="upper left")
    salvar(fig, dir_saida, "01_perfil_senioridade")


def grafico_top_cargos(df: pd.DataFrame, dir_saida: Path) -> None:
    ano = df["ano"].max()
    top = (
        df[(df["ano"] == ano) & df["cargo"].notna()]
        .groupby("cargo")["respondentes"]
        .sum()
        .nlargest(10)
        .sort_values()
    )
    if top.empty:
        return
    fig, ax = plt.subplots(figsize=(10, 5))
    top.plot(kind="barh", ax=ax, color=PALETA[1])
    ax.set_title(f"Top 10 cargos por numero de profissionais ({ano})")
    ax.set_xlabel("Respondentes")
    ax.set_ylabel("")
    salvar(fig, dir_saida, "02_top_cargos")


# --- Remuneracao ---

def grafico_salario_senioridade(df: pd.DataFrame, dir_saida: Path) -> None:
    base = _recorte(df, "senioridade")
    if base.empty:
        return
    pivot = base.pivot_table(index="ano", columns="dimensao_1", values=METRICA_SALARIO)
    colunas = ordenar_senioridade(pivot.columns)
    if not colunas:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot[colunas].plot(kind="bar", ax=ax, color=PALETA)
    ax.set_title("Remuneracao mensal por senioridade")
    ax.set_xlabel("Ano da pesquisa")
    ax.set_ylabel(ROTULO_SALARIO)
    ax.legend(title="Senioridade")
    salvar(fig, dir_saida, "03_salario_senioridade")


def grafico_salario_regiao(df: pd.DataFrame, dir_saida: Path) -> None:
    base = _recorte(df, "regiao")
    if base.empty:
        return
    ano = base["ano"].max()
    serie = (
        base[(base["ano"] == ano) & (base["dimensao_1"] != "Nao informado")]
        .set_index("dimensao_1")[METRICA_SALARIO]
        .sort_values()
    )
    if serie.empty:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    serie.plot(kind="barh", ax=ax, color=PALETA[2])
    ax.set_title(f"Remuneracao mensal por regiao ({ano})")
    ax.set_xlabel(ROTULO_SALARIO)
    ax.set_ylabel("")
    salvar(fig, dir_saida, "04_salario_regiao")


def grafico_salario_forma_trabalho(df: pd.DataFrame, dir_saida: Path) -> None:
    base = _recorte(df, "forma_trabalho")
    base = base[base["dimensao_1"] != "Nao informado"]
    if base.empty:
        return
    pivot = base.pivot_table(index="dimensao_1", columns="ano", values=METRICA_SALARIO)
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.plot(kind="bar", ax=ax, color=PALETA)
    ax.set_title("Remuneracao mensal por modelo de trabalho")
    ax.set_xlabel("")
    ax.set_ylabel(ROTULO_SALARIO)
    ax.legend(title="Ano")
    salvar(fig, dir_saida, "05_salario_forma_trabalho")


def grafico_salario_por_cargo(df: pd.DataFrame, dir_saida: Path) -> None:
    base = _recorte(df, "cargo")
    base = base[base["dimensao_1"].notna()]
    if base.empty:
        return
    ano = base["ano"].max()
    serie = (
        base[base["ano"] == ano]
        .nlargest(10, METRICA_SALARIO)
        .set_index("dimensao_1")[METRICA_SALARIO]
        .sort_values()
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    serie.plot(kind="barh", ax=ax, color=PALETA[0])
    ax.set_title(f"Cargos com maior remuneracao ({ano})")
    ax.set_xlabel(ROTULO_SALARIO)
    ax.set_ylabel("")
    salvar(fig, dir_saida, "06_salario_por_cargo")


def grafico_retorno_experiencia(df: pd.DataFrame, dir_saida: Path) -> None:
    base = _recorte(df, "tempo_experiencia_dados")
    base = base[base["dimensao_1"].notna()]
    if base.empty:
        return
    ano = base["ano"].max()
    serie = (
        base[base["ano"] == ano].set_index("dimensao_1")[METRICA_SALARIO].sort_values()
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    serie.plot(kind="barh", ax=ax, color=PALETA[1])
    ax.set_title(f"Remuneracao por tempo de experiencia em dados ({ano})")
    ax.set_xlabel(ROTULO_SALARIO)
    ax.set_ylabel("")
    salvar(fig, dir_saida, "07_retorno_experiencia")


# --- Tecnologias ---

def grafico_top_tecnologias(df: pd.DataFrame, dir_saida: Path) -> None:
    ano = df["ano"].max()
    for categoria in sorted(df["categoria"].dropna().unique()):
        base = (
            df[(df["ano"] == ano) & (df["categoria"] == categoria)]
            .nlargest(10, "respondentes")
            .sort_values("taxa_adocao")
        )
        if base.empty:
            continue
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh([str(t)[:45] for t in base["tecnologia"]], base["taxa_adocao"], color=PALETA[1])
        ax.set_title(f"Top 10 - {categoria.replace('_', ' ')} ({ano})")
        ax.set_xlabel("% dos respondentes")
        salvar(fig, dir_saida, f"08_tecnologias_{categoria}")


def grafico_evolucao_tecnologias(df: pd.DataFrame, dir_saida: Path) -> None:
    """Evolucao das tecnologias nas categorias comparaveis entre edicoes.

    Categorias excluidas da serie historica, por nao serem comparaveis:
      - linguagem_uso: a questao nao existe na edicao 2025;
      - linguagem_preferida: passou de escolha unica (1,0 item por respondente)
        para multipla (2,0) em 2025, o que faria o SQL "crescer" de 1,4% para
        50,5% por mudanca de questionario, nao de mercado.
    """
    anos = sorted(df["ano"].unique())
    for categoria in CATEGORIAS_COMPARAVEIS:
        base = df[df["categoria"] == categoria]
        if base["ano"].nunique() < 2:
            continue
        # Guarda de seguranca: se o formato da questao mudou, nao compare.
        if "itens_por_respondente" in base.columns:
            variacao = base.groupby("ano")["itens_por_respondente"].first()
            if variacao.max() - variacao.min() > 0.5:
                print(f"  (pulando evolucao de {categoria}: formato da questao mudou)")
                continue
        principais = (
            base[base["ano"] == base["ano"].max()].nlargest(5, "respondentes")["tecnologia"].tolist()
        )
        serie = base[base["tecnologia"].isin(principais)]
        if serie.empty:
            continue
        pivot = serie.pivot_table(index="ano", columns="tecnologia", values="taxa_adocao")
        fig, ax = plt.subplots(figsize=(9, 5))
        pivot.plot(kind="line", marker="o", ax=ax, color=PALETA)
        ax.set_title(f"Evolucao da adocao - {categoria.replace('_', ' ')}")
        ax.set_xlabel("Ano da pesquisa")
        ax.set_ylabel("% dos respondentes")
        ax.set_xticks(anos)
        ax.legend(bbox_to_anchor=(1.02, 1), loc="upper left")
        salvar(fig, dir_saida, f"09_evolucao_{categoria}")


# --- Inteligencia Artificial ---

def grafico_adocao_ia(df: pd.DataFrame, dir_saida: Path) -> None:
    # Edicoes sem a pergunta tem base de resposta zero e nao entram no grafico.
    base = df[df["base_resposta"] > 0]
    if base.empty:
        return
    pivot = base.pivot_table(index="senioridade", columns="ano", values="taxa_adocao_ia")
    linhas = ordenar_senioridade(pivot.index)
    if not linhas:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.loc[linhas].plot(kind="bar", ax=ax, color=PALETA)
    ax.set_title("Adocao de IA generativa por senioridade")
    ax.set_xlabel("Senioridade")
    ax.set_ylabel("% que usa IA no trabalho")
    ax.set_ylim(0, 100)
    ax.legend(title="Ano")
    salvar(fig, dir_saida, "10_adocao_ia")


def grafico_impacto_ia(df: pd.DataFrame, dir_saida: Path) -> None:
    base = df[df["amostra_suficiente"].astype(bool)] if "amostra_suficiente" in df else df
    base = base[base["senioridade"].isin(ORDEM_SENIORIDADE)]
    pivot = base.pivot_table(index="senioridade", columns="grupo", values=METRICA_SALARIO)
    pivot = pivot.dropna()
    linhas = ordenar_senioridade(pivot.index)
    if not linhas:
        print("  (pulando impacto_ia: sem grupo com amostra suficiente nos dois lados)")
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.loc[linhas].plot(kind="bar", ax=ax, color=[PALETA[3], PALETA[0]])
    ax.set_title("Remuneracao de quem usa e de quem nao usa IA, por senioridade")
    ax.set_xlabel("Senioridade")
    ax.set_ylabel(ROTULO_SALARIO)
    salvar(fig, dir_saida, "11_impacto_ia")


# --- Diversidade ---

def grafico_diversidade(df: pd.DataFrame, dir_saida: Path) -> None:
    pivot = df.groupby(["ano", "genero"])["respondentes"].sum().unstack(fill_value=0)
    pct = 100 * pivot.div(pivot.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    pct.plot(kind="bar", stacked=True, ax=ax, color=PALETA)
    ax.set_title("Distribuicao de genero por ano")
    ax.set_xlabel("Ano da pesquisa")
    ax.set_ylabel("% dos respondentes")
    ax.legend(title="Genero", bbox_to_anchor=(1.02, 1), loc="upper left")
    salvar(fig, dir_saida, "12_diversidade_genero")


def grafico_gap_salarial_genero(df: pd.DataFrame, dir_saida: Path) -> None:
    base = df[df["genero"].isin(["Masculino", "Feminino"])]
    ano = base["ano"].max()
    pivot = base[base["ano"] == ano].pivot_table(
        index="senioridade", columns="genero", values=METRICA_SALARIO
    ).dropna()
    linhas = ordenar_senioridade(pivot.index)
    if not linhas:
        return
    fig, ax = plt.subplots(figsize=(9, 5))
    pivot.loc[linhas].plot(kind="bar", ax=ax, color=[PALETA[3], PALETA[0]])
    ax.set_title(f"Remuneracao por genero e senioridade ({ano})")
    ax.set_xlabel("Senioridade")
    ax.set_ylabel(ROTULO_SALARIO)
    salvar(fig, dir_saida, "13_gap_salarial_genero")


def grafico_participacao_feminina_por_nivel(df: pd.DataFrame, dir_saida: Path) -> None:
    """Participacao feminina por senioridade: mostra o afunilamento na carreira."""
    base = df[df["genero"].isin(["Masculino", "Feminino"])]
    pivot = base.pivot_table(
        index="senioridade", columns="genero", values="respondentes", aggfunc="sum"
    ).dropna()
    linhas = ordenar_senioridade(pivot.index)
    if not linhas:
        return
    pct = 100 * pivot.loc[linhas, "Feminino"] / pivot.loc[linhas].sum(axis=1)
    fig, ax = plt.subplots(figsize=(9, 5))
    pct.plot(kind="bar", ax=ax, color=PALETA[3])
    ax.set_title("Participacao feminina por senioridade (3 edicoes)")
    ax.set_xlabel("Senioridade")
    ax.set_ylabel("% de mulheres")
    salvar(fig, dir_saida, "14_participacao_feminina")


# --- Modelo de trabalho ---

def grafico_modelo_trabalho(df: pd.DataFrame, dir_saida: Path) -> None:
    ano = df["ano"].max()
    base = df[
        (df["ano"] == ano)
        & (df["regiao"] != "Nao informado")
        & (df["forma_trabalho"] != "Nao informado")
    ]
    pivot = base.pivot_table(
        index="regiao", columns="forma_trabalho", values="respondentes", aggfunc="sum"
    ).fillna(0)
    if pivot.empty:
        return
    pct = 100 * pivot.div(pivot.sum(axis=1), axis=0)
    fig, ax = plt.subplots(figsize=(9, 5))
    pct.plot(kind="barh", stacked=True, ax=ax, color=PALETA)
    ax.set_title(f"Modelo de trabalho por regiao ({ano})")
    ax.set_xlabel("% dos respondentes da regiao")
    ax.set_ylabel("")
    ax.legend(title="Modelo", bbox_to_anchor=(1.02, 1), loc="upper left")
    salvar(fig, dir_saida, "15_modelo_trabalho_regiao")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir-gold", default=str(RAIZ / "data" / "gold"))
    ap.add_argument("--dir-saida", default=str(RAIZ / "data" / "graficos"))
    args = ap.parse_args()

    dir_gold, dir_saida = Path(args.dir_gold), Path(args.dir_saida)
    dir_saida.mkdir(parents=True, exist_ok=True)

    print(f"Lendo Gold de {dir_gold}")
    perfil = carregar(dir_gold, "perfil_mercado")
    remuneracao = carregar(dir_gold, "remuneracao")
    diversidade = carregar(dir_gold, "diversidade")
    tecnologias = carregar(dir_gold, "tecnologias")
    ia = carregar(dir_gold, "adocao_ia")
    impacto = carregar(dir_gold, "impacto_ia")
    modelo = carregar(dir_gold, "modelo_trabalho")

    print("Gerando graficos:")
    if perfil is not None:
        grafico_perfil_por_senioridade(perfil, dir_saida)
        grafico_top_cargos(perfil, dir_saida)
    if remuneracao is not None:
        grafico_salario_senioridade(remuneracao, dir_saida)
        grafico_salario_regiao(remuneracao, dir_saida)
        grafico_salario_forma_trabalho(remuneracao, dir_saida)
        grafico_salario_por_cargo(remuneracao, dir_saida)
        grafico_retorno_experiencia(remuneracao, dir_saida)
    if tecnologias is not None:
        grafico_top_tecnologias(tecnologias, dir_saida)
        grafico_evolucao_tecnologias(tecnologias, dir_saida)
    if ia is not None:
        grafico_adocao_ia(ia, dir_saida)
    if impacto is not None:
        grafico_impacto_ia(impacto, dir_saida)
    if diversidade is not None:
        grafico_diversidade(diversidade, dir_saida)
        grafico_gap_salarial_genero(diversidade, dir_saida)
        grafico_participacao_feminina_por_nivel(diversidade, dir_saida)
    if modelo is not None:
        grafico_modelo_trabalho(modelo, dir_saida)

    print(f"\nGraficos em {dir_saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
