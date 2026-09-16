"""Glue Job 1 - Bronze para Silver.

Le os CSVs brutos das 3 edicoes da pesquisa State of Data Brasil na camada
Bronze, resolve as colunas de cada edicao para um modelo canonico unico e grava
duas tabelas na camada Silver em Parquet particionado por ano:

    silver/respondentes/   1 linha por respondente (modelo canonico)
    silver/tecnologias/    tabela longa (ano, id_respondente, categoria, tecnologia)

Tratamentos aplicados, todos definidos em src/sod/mapeamento.py:
  - resolucao das colunas por codigo de questao, por edicao (os formatos de
    cabecalho e a numeracao das questoes mudam entre as 3 edicoes);
  - padronizacao de senioridade, forma de trabalho, genero e regiao;
  - senioridade dos gestores, que a pesquisa deixa em branco por desenho;
  - estimativa de remuneracao e limites da faixa salarial (insumo da mediana
    interpolada calculada no Job 2);
  - classificacao do uso de IA generativa;
  - explode das respostas de multipla escolha de tecnologia.

Parametros do Job:
    --BUCKET            nome do bucket S3 do data lake
    --PREFIXO_BRONZE    default: bronze
    --PREFIXO_SILVER    default: silver
    --CAMINHO_CONFIG    s3://.../config/mapeamento_colunas.json

Dependencias: subir src/sod como ZIP em --extra-py-files (ver README).
"""

from __future__ import annotations

import json
import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import DoubleType, IntegerType, StringType

from sod import mapeamento as m

ARGS_OBRIGATORIOS = ["JOB_NAME", "BUCKET"]
ARGS_OPCIONAIS = {
    "PREFIXO_BRONZE": "bronze",
    "PREFIXO_SILVER": "silver",
    "CAMINHO_CONFIG": "",
}


def resolver_argumentos() -> dict:
    args = getResolvedOptions(sys.argv, ARGS_OBRIGATORIOS + list(ARGS_OPCIONAIS))
    for chave, default in ARGS_OPCIONAIS.items():
        if not args.get(chave):
            args[chave] = default
    return args


def ler_config(spark, caminho: str) -> dict:
    """Le o JSON de mapeamento do S3 via Spark, ou do pacote local como fallback."""
    if not caminho:
        return m.carregar_config()
    texto = "".join(spark.read.text(caminho).rdd.map(lambda r: r[0]).collect())
    return json.loads(texto)


def ler_bronze(spark, caminho: str) -> DataFrame:
    """CSV da pesquisa: cabecalho longo, campos multilinha e virgulas dentro das respostas."""
    return (
        spark.read.option("header", "true")
        .option("multiLine", "true")
        .option("escape", '"')
        .option("encoding", "UTF-8")
        .option("mode", "PERMISSIVE")
        .csv(caminho)
    )


def registrar_udfs(config: dict) -> dict:
    """UDFs construidas sobre o nucleo em Python puro (src/sod/mapeamento.py)."""
    mapa_regioes = config["regiao_por_uf"]
    return {
        "salario": F.udf(m.salario_medio_da_faixa, DoubleType()),
        "faixa_inferior": F.udf(lambda f: m.limites_da_faixa(f)[0], DoubleType()),
        "faixa_superior": F.udf(lambda f: m.limites_da_faixa(f)[1], DoubleType()),
        "regiao": F.udf(lambda r, uf: m.padronizar_regiao(r, uf, mapa_regioes), StringType()),
        "senioridade": F.udf(m.padronizar_senioridade, StringType()),
        "senioridade_gestao": F.udf(m.senioridade_com_gestao, StringType()),
        "forma_trabalho": F.udf(m.padronizar_forma_trabalho, StringType()),
        "genero": F.udf(m.padronizar_genero, StringType()),
        "binaria": F.udf(m.resposta_binaria, IntegerType()),
        "usa_ia": F.udf(m.usa_ia, IntegerType()),
        "tipo_uso_ia": F.udf(m.tipo_uso_ia, StringType()),
        "multivalorado": F.udf(m.separar_multivalorado, "array<string>"),
    }


def montar_respondentes(df: DataFrame, plano: dict, ano: int, udf: dict) -> DataFrame:
    """Projeta o CSV bruto no modelo canonico de respondentes."""
    campos = plano["campos"]

    selecao = [F.lit(ano).alias("ano"), F.col("id_respondente")]
    selecao += [
        F.trim(F.col(f"`{origem}`")).alias(nome) for nome, origem in campos.items()
    ]
    selecao += [
        F.trim(F.col(f"`{origem}`")).alias(f"{nome}_bruto")
        for nome, origem in plano["binarios"].items()
    ]
    selecao += [
        F.trim(F.col(f"`{origem}`")).alias(f"{nome}_bruto")
        for nome, origem in plano["ia"].items()
    ]
    out = df.select(*selecao)

    if "idade" in campos:
        out = out.withColumn("idade", F.col("idade").cast(IntegerType()))
    if "genero" in campos:
        out = out.withColumn("genero", udf["genero"](F.col("genero")))
    if "forma_trabalho" in campos:
        out = out.withColumn("forma_trabalho", udf["forma_trabalho"](F.col("forma_trabalho")))
    if "forma_trabalho_ideal" in campos:
        out = out.withColumn(
            "forma_trabalho_ideal", udf["forma_trabalho"](F.col("forma_trabalho_ideal"))
        )

    if "faixa_salarial" in campos:
        out = (
            out.withColumn("salario_mensal_estimado", udf["salario"](F.col("faixa_salarial")))
            .withColumn("faixa_inferior", udf["faixa_inferior"](F.col("faixa_salarial")))
            .withColumn("faixa_superior", udf["faixa_superior"](F.col("faixa_salarial")))
        )

    # A pesquisa ja entrega a regiao; a UF e usada apenas como fallback.
    coluna_regiao = F.col("regiao") if "regiao" in campos else F.lit(None).cast(StringType())
    coluna_uf = F.col("uf_moradia") if "uf_moradia" in campos else F.lit(None).cast(StringType())
    out = out.withColumn("regiao", udf["regiao"](coluna_regiao, coluna_uf))

    for nome in plano["binarios"]:
        out = out.withColumn(nome, udf["binaria"](F.col(f"{nome}_bruto")))

    if "senioridade" in campos:
        out = out.withColumn("senioridade", udf["senioridade"](F.col("senioridade")))
        # Gestores nao respondem a questao de nivel: sem este passo eles
        # cairiam em "Nao informado" e distorceriam a analise por senioridade.
        if "atua_como_gestor" in plano["binarios"]:
            out = out.withColumn(
                "senioridade",
                udf["senioridade_gestao"](F.col("senioridade"), F.col("atua_como_gestor")),
            )

    if "uso_ia_pessoal" in plano["ia"]:
        out = out.withColumn("usa_ia", udf["usa_ia"](F.col("uso_ia_pessoal_bruto"))).withColumn(
            "tipo_uso_ia", udf["tipo_uso_ia"](F.col("uso_ia_pessoal_bruto"))
        )
    for nome in ("tipo_uso_ia_empresa", "ia_prioridade_empresa"):
        if nome in plano["ia"]:
            out = out.withColumn(nome, F.col(f"{nome}_bruto"))

    return out.drop(*[c for c in out.columns if c.endswith("_bruto")])


def montar_tecnologias(df: DataFrame, plano: dict, ano: int, udf: dict) -> DataFrame | None:
    """Explode as respostas multivaloradas de tecnologia em uma tabela longa."""
    if not plano["tecnologias"]:
        return None

    base = df.select(
        F.col("id_respondente"),
        *[
            F.trim(F.col(f"`{origem}`")).alias(f"tec_{categoria}")
            for categoria, origem in plano["tecnologias"].items()
        ],
    )

    partes = [
        base.select(
            F.lit(ano).alias("ano"),
            "id_respondente",
            F.lit(categoria).alias("categoria"),
            F.explode(udf["multivalorado"](F.col(f"tec_{categoria}"))).alias("tecnologia"),
        ).filter(F.length(F.trim(F.col("tecnologia"))) > 0)
        for categoria in plano["tecnologias"]
    ]

    resultado = partes[0]
    for parte in partes[1:]:
        resultado = resultado.unionByName(parte)
    return resultado


def alinhar_schemas(dfs: list[DataFrame]) -> list[DataFrame]:
    """Garante o mesmo conjunto de colunas em todas as edicoes antes do union.

    Campos que nao existem em uma edicao entram como nulo, preservando o tipo
    das colunas numericas para nao quebrar as agregacoes do Job 2.
    """
    tipos: dict[str, object] = {}
    for df in dfs:
        for campo in df.schema.fields:
            tipos.setdefault(campo.name, campo.dataType)

    alinhados = []
    for df in dfs:
        faltando = [
            F.lit(None).cast(tipos[nome]).alias(nome) for nome in tipos if nome not in df.columns
        ]
        alinhados.append(df.select(*df.columns, *faltando).select(*tipos))
    return alinhados


def main() -> None:
    args = resolver_argumentos()
    sc = SparkContext.getOrCreate()
    glue = GlueContext(sc)
    spark = glue.spark_session
    job = Job(glue)
    job.init(args["JOB_NAME"], args)

    config = ler_config(spark, args["CAMINHO_CONFIG"])
    udf = registrar_udfs(config)

    base_bronze = f"s3://{args['BUCKET']}/{args['PREFIXO_BRONZE']}"
    base_silver = f"s3://{args['BUCKET']}/{args['PREFIXO_SILVER']}"

    respondentes: list[DataFrame] = []
    tecnologias: list[DataFrame] = []

    for edicao in config["edicoes"]:
        ano = int(edicao["ano"])
        caminho = f"{base_bronze}/state_of_data_{ano}/"
        print(f"[bronze->silver] lendo {caminho}")

        bruto = ler_bronze(spark, caminho)
        plano = m.montar_plano_colunas(bruto.columns, config, ano)

        print(f"[{ano}] colunas no csv: {len(bruto.columns)}")
        for grupo in m.GRUPOS:
            print(f"[{ano}] {grupo}: {sorted(plano[grupo])}")
        if plano["nao_aplicavel"]:
            print(f"[{ano}] nao aplicavel a esta edicao: {plano['nao_aplicavel']}")
        if plano["faltando"]:
            print(f"[{ano}] ATENCAO - NAO ENCONTRADOS: {plano['faltando']}")

        # ID gerado uma unica vez por edicao e reaproveitado pelas duas tabelas
        # Silver, para que respondentes e tecnologias possam ser unidos por join.
        bruto = bruto.withColumn(
            "id_respondente", F.concat_ws("-", F.lit(ano), F.monotonically_increasing_id())
        ).cache()

        respondentes.append(montar_respondentes(bruto, plano, ano, udf))
        tec = montar_tecnologias(bruto, plano, ano, udf)
        if tec is not None:
            tecnologias.append(tec)

    alinhados = alinhar_schemas(respondentes)
    silver_resp = alinhados[0]
    for df in alinhados[1:]:
        silver_resp = silver_resp.unionByName(df)

    destino_resp = f"{base_silver}/respondentes/"
    print(f"[bronze->silver] gravando {destino_resp} ({silver_resp.count()} linhas)")
    silver_resp.write.mode("overwrite").partitionBy("ano").parquet(destino_resp)

    if tecnologias:
        silver_tec = tecnologias[0]
        for df in tecnologias[1:]:
            silver_tec = silver_tec.unionByName(df)
        destino_tec = f"{base_silver}/tecnologias/"
        print(f"[bronze->silver] gravando {destino_tec} ({silver_tec.count()} linhas)")
        silver_tec.write.mode("overwrite").partitionBy("ano").parquet(destino_tec)

    job.commit()


if __name__ == "__main__":
    main()