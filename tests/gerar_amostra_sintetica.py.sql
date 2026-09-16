"""Gera CSVs sinteticos no mesmo formato da pesquisa State of Data Brasil.

Serve para validar o pipeline de ponta a ponta sem depender do download do
Kaggle, e para testar mudancas no mapeamento. Os dados sao aleatorios e NAO
devem ser usados em nenhuma analise da entrega.

Uso:
    python tests/gerar_amostra_sintetica.py --dir-saida data/amostra
"""

from __future__ import annotations

import argparse
import csv
import random
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

FAIXAS_SALARIAIS = [
    "Menos de R$ 1.000/mês",
    "de R$ 1.001/mês a R$ 2.000/mês",
    "de R$ 4.001/mês a R$ 6.000/mês",
    "de R$ 8.001/mês a R$ 12.000/mês",
    "de R$ 12.001/mês a R$ 16.000/mês",
    "de R$ 16.001/mês a R$ 20.000/mês",
    "Acima de R$ 40.001/mês",
    "Prefiro não informar",
]
GENEROS = ["Masculino", "Feminino", "Prefiro não informar", "Outro"]
UFS = ["SP", "RJ", "MG", "RS", "PR", "SC", "BA", "PE", "CE", "DF", "GO", "AM", "PA"]
CARGOS = [
    "Analista de Dados/Data Analyst",
    "Cientista de Dados/Data Scientist",
    "Engenheiro de Dados/Data Engineer",
    "Analista de BI/BI Analyst",
    "Analista de Negócios/Business Analyst",
    "Engenheiro de Machine Learning/ML Engineer",
]
SENIORIDADES = ["Júnior", "Pleno", "Sênior", "Gerente", "Coordenador"]
FORMAS_TRABALHO = [
    "Modelo 100% presencial",
    "Modelo híbrido flexível",
    "Modelo 100% remoto",
    "Modelo híbrido com dias fixos",
]
NIVEIS_ENSINO = ["Graduação/Bacharelado", "Pós-graduação", "Mestrado", "Doutorado ou Phd"]
AREAS_FORMACAO = ["Computação / Engenharia de Software", "Estatística", "Economia", "Outras Engenharias"]
SETORES = ["Finanças ou Bancos", "Tecnologia/Fábrica de Software", "Varejo", "Indústria"]
LINGUAGENS = ["Python", "SQL", "R", "Scala", "Java", "JavaScript"]
BANCOS = ["MySQL", "PostgreSQL", "SQL Server", "Oracle", "BigQuery", "Amazon Redshift"]
CLOUDS = ["Amazon Web Services (AWS)", "Google Cloud (GCP)", "Azure (Microsoft)"]
FERRAMENTAS_BI = ["Power BI", "Tableau", "Looker Studio", "Qlik Sense", "Metabase"]
RESPOSTAS_IA = ["Sim", "Não", ""]

CABECALHOS = {
    "id": "('P0', 'id')",
    "idade": "('P1_a ', 'Idade')",
    "genero": "('P1_b ', 'Genero')",
    "cor": "('P1_c ', 'Cor/raca/etnia')",
    "pcd": "('P1_d ', 'PCD')",
    "uf": "('P1_i_1 ', 'uf onde mora')",
    "ensino": "('P1_l ', 'Nivel de Ensino')",
    "formacao": "('P1_m ', 'Área de Formação')",
    "situacao": "('P2_a ', 'Qual sua situação atual de trabalho?')",
    "setor": "('P2_b ', 'Setor da empresa')",
    "cargo": "('P2_f ', 'Cargo atual')",
    "senioridade": "('P2_g ', 'Nivel')",
    "salario": "('P2_h ', 'Faixa salarial')",
    "experiencia": "('P2_i ', 'Quanto tempo de experiência na área de dados você tem?')",
    "forma_trabalho": "('P2_r ', 'Atualmente qual a sua forma de trabalho?')",
    "linguagem": "('P4_d ', 'Linguagens que utiliza no trabalho')",
    "banco": "('P4_h ', 'Bancos de dados que utiliza no trabalho')",
    "cloud": "('P4_i ', 'Cloud que utiliza no trabalho')",
    "bi": "('P4_j ', 'Ferramenta de BI utilizada no dia a dia')",
    "ia": "('P5_a ', \"Você usa IA generativa (LLM's) no seu trabalho?\")",
}


def amostra_multipla(opcoes: list[str], rng: random.Random, maximo: int = 3) -> str:
    escolhidas = rng.sample(opcoes, k=rng.randint(1, min(maximo, len(opcoes))))
    return ", ".join(escolhidas)


def gerar_edicao(ano: int, n: int, destino: Path, rng: random.Random, com_ia: bool) -> None:
    chaves = [k for k in CABECALHOS if k != "ia" or com_ia]
    with destino.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([CABECALHOS[k] for k in chaves])

        for i in range(n):
            senioridade = rng.choice(SENIORIDADES)
            # Correlaciona salario com senioridade, para os graficos fazerem sentido.
            peso = {"Júnior": 0, "Pleno": 2, "Sênior": 3, "Coordenador": 4, "Gerente": 5}[senioridade]
            idx = min(len(FAIXAS_SALARIAIS) - 1, max(0, peso + rng.randint(-1, 1)))

            linha = {
                "id": f"{ano}{i:05d}",
                "idade": rng.randint(20, 55),
                "genero": rng.choices(GENEROS, weights=[65, 30, 3, 2])[0],
                "cor": rng.choice(["Branca", "Parda", "Preta", "Amarela"]),
                "pcd": rng.choices(["Sim", "Não"], weights=[5, 95])[0],
                "uf": rng.choice(UFS),
                "ensino": rng.choice(NIVEIS_ENSINO),
                "formacao": rng.choice(AREAS_FORMACAO),
                "situacao": "Empregado (CLT)",
                "setor": rng.choice(SETORES),
                "cargo": rng.choice(CARGOS),
                "senioridade": senioridade,
                "salario": FAIXAS_SALARIAIS[idx],
                "experiencia": rng.choice(["de 1 a 2 anos", "de 3 a 4 anos", "de 5 a 6 anos"]),
                "forma_trabalho": rng.choice(FORMAS_TRABALHO),
                "linguagem": amostra_multipla(LINGUAGENS, rng),
                "banco": amostra_multipla(BANCOS, rng),
                "cloud": amostra_multipla(CLOUDS, rng, maximo=2),
                "bi": amostra_multipla(FERRAMENTAS_BI, rng, maximo=2),
                "ia": rng.choices(RESPOSTAS_IA, weights=[60, 30, 10])[0],
            }
            w.writerow([linha[k] for k in chaves])

    print(f"gerado {destino} ({n} linhas, {len(chaves)} colunas)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir-saida", default=str(RAIZ / "data" / "amostra"))
    ap.add_argument("--linhas", type=int, default=800)
    args = ap.parse_args()

    destino = Path(args.dir_saida)
    destino.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)

    # Anos correspondentes as 3 ultimas edicoes (2023-2024, 2024-2025, 2025-2026).
    # A primeira e gerada sem a questao de IA para exercitar o caso de pergunta
    # ausente em parte da serie historica.
    gerar_edicao(2023, args.linhas, destino / "sintetico_2023.csv", rng, com_ia=False)
    gerar_edicao(2024, args.linhas, destino / "sintetico_2024.csv", rng, com_ia=True)
    gerar_edicao(2025, args.linhas, destino / "sintetico_2025.csv", rng, com_ia=True)


if __name__ == "__main__":
    main()

