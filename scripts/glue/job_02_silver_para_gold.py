"""Glue Job 2 - Silver para Gold.

Le a camada Silver e materializa tabelas agregadas, cada uma desenhada para
responder a uma pergunta de negocio do Tech Challenge:

    gold/perfil_mercado/    Como esta estruturado o mercado brasileiro de dados?
    gold/remuneracao/       Quais perfis sao mais valorizados?
    gold/diversidade/       Qual o cenario de diversidade de genero?
    gold/tecnologias/       Quais tecnologias tem maior adocao?
    gold/adocao_ia/         Qual o indice de adocao de IA?
    gold/impacto_ia/        Qual o impacto da IA na remuneracao?
    gold/modelo_trabalho/   Ha diferencas por regiao e modelo de trabalho?

METRICA DE REMUNERACAO: a pesquisa coleta renda em faixas, nao em valor exato.
A mediana do ponto medio da faixa e cega - ela devolve o centro da faixa
mediana e faz grupos diferentes exibirem valores identicos (todas as regioes
davam R$ 10.000). Por isso a metrica principal e a MEDIANA INTERPOLADA, o
estimador classico para dados agrupados, calculada a partir das bandas de faixa
gravadas na Silver.

Parametros do Job:
    --BUCKET            nome do bucket S3 do data lake
    --PREFIXO_SILVER    default: silver
    --PREFIXO_GOLD      default: gold
    --MIN_RESPONDENTES  default: 30 (corte de significancia para remuneracao)
"""

from __future__ import annotations

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame, Window, functions as F
from pyspark.sql.types import DoubleType

from sod import mapeamento as m

ARGS_OBRIGATORIOS = ["JOB_NAME", "BUCKET"]
ARGS_OPCIONAIS = {"PREFIXO_SILVER": "silver", "PREFIXO_GOLD": "gold", "MIN_RESPONDENTES": "30"}

# Recortes de remuneracao. Cruzar todas as dimensoes de uma vez pulveriza a
# amostra (~5 mil respondentes por edicao), entao a Gold e materializada em
# formato longo, com um recorte por conjunto de dimensoes.
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

# Mediana interpolada: recebe a lista de bandas (limite inferior, limite
# superior, contagem) de cada grupo e aplica o estimador para dados agrupados.
udf_mediana_interpolada = F.udf(
    lambda bandas: m.mediana_interpolada(
        [(b["faixa_inferior"], b["faixa_superior"], b["n"]) for b in (bandas or [])]
    ),
    DoubleType(),
)


def resolver_argumentos() -> dict:
    args = getResolvedOptions(sys.argv, ARGS_OBRIGATORIOS + list(ARGS_OPCIONAIS))
    for chave, default in ARGS_OPCIONAIS.items():
        if not args.get(chave):
            args[chave] = default
    return args


def gravar(df: DataFrame, caminho: str, particoes: list[str] | None = None) -> None:
    print(f"[silver->gold] gravando {caminho} ({df.count()} linhas)")
    writer = df.coalesce(1).write.mode("overwrite")
    if particoes:
        writer = writer.partitionBy(*particoes)
    writer.parquet(caminho)


def com_percentual(df: DataFrame, colunas_grupo: list[str], coluna_valor: str) -> DataFrame:
    """Adiciona o percentual da linha dentro do grupo informado."""
    janela = Window.partitionBy(*colunas_grupo)
    return df.withColumn(
        "percentual",
        F.round(100 * F.col(coluna_valor) / F.sum(coluna_valor).over(janela), 2),
    )


def agregar_remuneracao(base: DataFrame, dimensoes: list[str]) -> DataFrame:
    """Estatisticas de remuneracao de um grupo, incluindo a mediana interpolada."""
    chaves = ["ano", *dimensoes]

    estatisticas = base.groupBy(*chaves).agg(
        F.count("*").alias("respondentes"),
        F.round(F.avg("salario_mensal_estimado"), 2).alias("salario_medio"),
        F.round(F.expr("percentile_approx(salario_mensal_estimado, 0.5)"), 2).alias(
            "salario_mediano"
        ),
        F.round(F.expr("percentile_approx(salario_mensal_estimado, 0.25)"), 2).alias("p25"),
        F.round(F.expr("percentile_approx(salario_mensal_estimado, 0.75)"), 2).alias("p75"),
    )

    # Conta quantos respondentes caem em cada banda de faixa e entrega a lista
    # de bandas do grupo para a UDF que interpola a mediana.
    bandas = (
        base.groupBy(*chaves, "faixa_inferior", "faixa_superior")
        .agg(F.count("*").alias("n"))
        .groupBy(*chaves)
        .agg(
            F.collect_list(
                F.struct("faixa_inferior", "faixa_superior", "n")
            ).alias("bandas")
        )
        .withColumn(
            "salario_mediano_interpolado",
            F.round(udf_mediana_interpolada(F.col("bandas")), 2),
        )
        .drop("bandas")
    )

    return estatisticas.join(bandas, on=chaves, how="left")


def gold_perfil_mercado(resp: DataFrame) -> DataFrame:
    base = resp.groupBy("ano", "cargo", "senioridade").agg(
        F.count("*").alias("respondentes"),
        F.round(F.avg("idade"), 1).alias("idade_media"),
    )
    return com_percentual(base, ["ano"], "respondentes").orderBy(
        "ano", F.col("respondentes").desc()
    )


def gold_remuneracao(resp: DataFrame, min_resp: int) -> DataFrame:
    base = resp.filter(F.col("salario_mensal_estimado").isNotNull())

    partes = []
    for recorte, dimensoes in RECORTES_REMUNERACAO.items():
        if any(d not in resp.columns for d in dimensoes):
            print(f"[gold_remuneracao] recorte '{recorte}' ignorado: dimensao ausente na Silver")
            continue

        agregado = agregar_remuneracao(base, dimensoes)
        partes.append(
            agregado.select(
                "ano",
                F.lit(recorte).alias("recorte"),
                F.col(dimensoes[0]).cast("string").alias("dimensao_1"),
                (
                    F.col(dimensoes[1]).cast("string")
                    if len(dimensoes) > 1
                    else F.lit(None).cast("string")
                ).alias("dimensao_2"),
                "respondentes",
                "salario_mediano_interpolado",
                "salario_mediano",
                "salario_medio",
                "p25",
                "p75",
            )
        )

    resultado = partes[0]
    for parte in partes[1:]:
        resultado = resultado.unionByName(parte)

    return resultado.withColumn(
        "amostra_suficiente", F.col("respondentes") >= F.lit(min_resp)
    ).orderBy("ano", "recorte", F.col("salario_mediano_interpolado").desc())


def gold_diversidade(resp: DataFrame) -> DataFrame:
    dimensoes = ["genero", "senioridade"]
    contagem = resp.groupBy("ano", *dimensoes).agg(F.count("*").alias("respondentes"))
    salarios = agregar_remuneracao(
        resp.filter(F.col("salario_mensal_estimado").isNotNull()), dimensoes
    ).select("ano", *dimensoes, "salario_mediano_interpolado", "salario_medio")

    base = contagem.join(salarios, on=["ano", *dimensoes], how="left")
    return com_percentual(base, ["ano", "senioridade"], "respondentes").orderBy(
        "ano", "senioridade", F.col("respondentes").desc()
    )


def gold_tecnologias(tec: DataFrame, resp: DataFrame) -> DataFrame:
    """Adocao por tecnologia.

    O denominador da taxa e quem RESPONDEU aquela questao (base_resposta), nao o
    total de respondentes da edicao: a cobertura de resposta das questoes de
    tecnologia cai de 71% em 2023 para 60% em 2025, e usar o total faria todas
    as tecnologias parecerem perder cerca de 11 pontos de adocao por artefato.

    itens_por_respondente expoe mudanca de formato da questao (escolha unica vs
    multipla). Categorias cujo valor muda entre edicoes nao sao comparaveis na
    serie historica: linguagem_preferida passou de 1,0 para 2,0 item em 2025.
    """
    total_por_ano = resp.groupBy("ano").agg(F.count("*").alias("total_respondentes"))

    base_categoria = tec.groupBy("ano", "categoria").agg(
        F.countDistinct("id_respondente").alias("base_resposta"),
        F.count("*").alias("total_mencoes"),
    ).withColumn(
        "itens_por_respondente",
        F.round(F.col("total_mencoes") / F.col("base_resposta"), 2),
    ).drop("total_mencoes")

    contagem = tec.groupBy("ano", "categoria", "tecnologia").agg(
        F.countDistinct("id_respondente").alias("respondentes")
    )

    ranqueado = (
        contagem.join(base_categoria, on=["ano", "categoria"], how="left")
        .join(total_por_ano, on="ano", how="left")
        .withColumn(
            "taxa_adocao", F.round(100 * F.col("respondentes") / F.col("base_resposta"), 2)
        )
    )
    janela = Window.partitionBy("ano", "categoria").orderBy(F.col("respondentes").desc())
    return ranqueado.withColumn("posicao", F.row_number().over(janela)).orderBy(
        "ano", "categoria", "posicao"
    )


def gold_adocao_ia(resp: DataFrame) -> DataFrame:
    """Taxa de adocao de IA por senioridade.

    A media da flag 0/1 ignora nulos, portanto o resultado e a taxa entre quem
    respondeu a questao. A coluna base_resposta expoe esse denominador: edicoes
    sem a pergunta aparecem com base zero e devem ser excluidas da leitura.
    """
    return (
        resp.groupBy("ano", "senioridade")
        .agg(
            F.count("*").alias("respondentes"),
            F.count(F.col("usa_ia")).alias("base_resposta"),
            F.round(100 * F.avg(F.col("usa_ia")), 2).alias("taxa_adocao_ia"),
        )
        .orderBy("ano", F.col("taxa_adocao_ia").desc())
    )


def gold_impacto_ia(resp: DataFrame, min_resp: int) -> DataFrame:
    """Remuneracao de quem usa e de quem nao usa IA, controlando por senioridade.

    E uma associacao, nao uma relacao causal: o grupo que usa IA difere tambem
    em setor, porte de empresa e perfil de cargo.
    """
    base = resp.filter(F.col("usa_ia").isNotNull() & F.col("salario_mensal_estimado").isNotNull())
    agregado = agregar_remuneracao(base, ["senioridade", "usa_ia"]).select(
        "ano",
        "senioridade",
        "usa_ia",
        "respondentes",
        "salario_medio",
        "salario_mediano_interpolado",
    )
    return (
        agregado.withColumn(
            "grupo",
            F.when(F.col("usa_ia") == 1, F.lit("Usa IA")).otherwise(F.lit("Nao usa IA")),
        )
        .withColumn("amostra_suficiente", F.col("respondentes") >= F.lit(min_resp))
        .orderBy("ano", "senioridade", "grupo")
    )


def gold_modelo_trabalho(resp: DataFrame) -> DataFrame:
    dimensoes = ["regiao", "forma_trabalho"]
    contagem = resp.groupBy("ano", *dimensoes).agg(F.count("*").alias("respondentes"))
    salarios = agregar_remuneracao(
        resp.filter(F.col("salario_mensal_estimado").isNotNull()), dimensoes
    ).select("ano", *dimensoes, "salario_mediano_interpolado", "salario_medio")

    base = contagem.join(salarios, on=["ano", *dimensoes], how="left")
    return com_percentual(base, ["ano", "regiao"], "respondentes").orderBy(
        "ano", "regiao", F.col("respondentes").desc()
    )


def main() -> None:
    args = resolver_argumentos()
    sc = SparkContext.getOrCreate()
    glue = GlueContext(sc)
    spark = glue.spark_session
    job = Job(glue)
    job.init(args["JOB_NAME"], args)

    base_silver = f"s3://{args['BUCKET']}/{args['PREFIXO_SILVER']}"
    base_gold = f"s3://{args['BUCKET']}/{args['PREFIXO_GOLD']}"
    min_resp = int(args["MIN_RESPONDENTES"])

    resp = spark.read.parquet(f"{base_silver}/respondentes/").cache()
    tec = spark.read.parquet(f"{base_silver}/tecnologias/")
    print(f"[silver->gold] respondentes: {resp.count()} | tecnologias: {tec.count()}")

    gravar(gold_perfil_mercado(resp), f"{base_gold}/perfil_mercado/", ["ano"])
    gravar(gold_remuneracao(resp, min_resp), f"{base_gold}/remuneracao/", ["ano"])
    gravar(gold_diversidade(resp), f"{base_gold}/diversidade/", ["ano"])
    gravar(gold_tecnologias(tec, resp), f"{base_gold}/tecnologias/", ["ano"])
    gravar(gold_adocao_ia(resp), f"{base_gold}/adocao_ia/", ["ano"])
    gravar(gold_impacto_ia(resp, min_resp), f"{base_gold}/impacto_ia/", ["ano"])
    gravar(gold_modelo_trabalho(resp), f"{base_gold}/modelo_trabalho/", ["ano"])

    job.commit()


if __name__ == "__main__":
    main()