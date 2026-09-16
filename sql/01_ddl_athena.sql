-- =====================================================================
-- Tech Challenge Fase 3 - DDL do Data Catalog (Amazon Athena)
-- =====================================================================
-- Ordem de execucao no console do Athena:
--   1. CREATE DATABASE
--   2. Rodar os Glue Crawlers (recomendado) OU executar os CREATE TABLE abaixo
--   3. MSCK REPAIR TABLE para registrar as particoes de ano
--
-- Substitua SEU-BUCKET pelo nome real do bucket antes de executar.
-- Os schemas abaixo correspondem exatamente a saida dos Glue Jobs.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS state_of_data
COMMENT 'Data lake da pesquisa State of Data Brasil - Tech Challenge Fase 3';

-- ---------------------------------------------------------------------
-- Camada Bronze: CSV bruto, exatamente como veio do Kaggle.
-- As 3 edicoes tem entre 388 e 403 colunas e formatos de cabecalho
-- diferentes (tupla em 2023, texto plano em 2024/2025). A Bronze e
-- catalogada apenas para rastreabilidade: as consultas analiticas usam
-- Silver e Gold.
-- ---------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.bronze_state_of_data_2025 (
    linha_bruta string
)
ROW FORMAT DELIMITED FIELDS TERMINATED BY '\t'
LOCATION 's3://SEU-BUCKET/bronze/state_of_data_2025/'
TBLPROPERTIES ('skip.header.line.count' = '1');

-- ---------------------------------------------------------------------
-- Camada Silver: modelo canonico, 1 linha por respondente, Parquet.
-- Particionada por ano da pesquisa.
--
-- faixa_inferior / faixa_superior sao os limites da faixa salarial e
-- servem de insumo para a mediana interpolada calculada na Gold.
-- faixa_superior nula indica faixa aberta no topo.
-- ---------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.silver_respondentes (
    id_respondente            string,
    idade                     int,
    genero                    string,
    cor_raca_etnia            string,
    pcd                       string,
    estado_moradia            string,
    uf_moradia                string,
    regiao                    string,
    nivel_ensino              string,
    area_formacao             string,
    situacao_trabalho         string,
    setor_empresa             string,
    porte_empresa             string,
    cargo                     string,
    senioridade               string,
    faixa_salarial            string,
    tempo_experiencia_dados   string,
    tempo_experiencia_ti      string,
    forma_trabalho            string,
    forma_trabalho_ideal      string,
    salario_mensal_estimado   double,
    faixa_inferior            double,
    faixa_superior            double,
    satisfacao_empresa        int,
    atua_como_gestor          int,
    usa_ia                    int,
    tipo_uso_ia               string,
    tipo_uso_ia_empresa       string,
    ia_prioridade_empresa     string
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/silver/respondentes/'
TBLPROPERTIES ('parquet.compression' = 'SNAPPY');

-- Tabela longa de tecnologias: 1 linha por respondente x tecnologia citada.
-- Categorias: linguagem_uso, linguagem_preferida, banco_dados, cloud_uso,
-- cloud_preferida, ferramenta_bi.
CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.silver_tecnologias (
    id_respondente string,
    categoria      string,
    tecnologia     string
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/silver/tecnologias/';

-- ---------------------------------------------------------------------
-- Camada Gold: tabelas agregadas, uma por pergunta de negocio.
--
-- METRICA DE REMUNERACAO: use salario_mediano_interpolado, nao
-- salario_mediano. A pesquisa coleta renda em faixas, e a mediana do
-- ponto medio da faixa devolve o mesmo valor para grupos diferentes
-- (todas as regioes davam R$ 10.000). A coluna salario_mediano e
-- mantida apenas para comparacao metodologica.
-- ---------------------------------------------------------------------
CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.gold_perfil_mercado (
    cargo         string,
    senioridade   string,
    respondentes  bigint,
    idade_media   double,
    percentual    double
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/gold/perfil_mercado/';

-- Formato longo: a coluna 'recorte' define quais dimensoes estao em
-- dimensao_1 e dimensao_2. Recortes disponiveis: senioridade, cargo,
-- cargo_senioridade, regiao, regiao_senioridade, forma_trabalho,
-- forma_trabalho_senioridade, nivel_ensino, tempo_experiencia_dados,
-- genero, setor_empresa.
CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.gold_remuneracao (
    recorte                     string,
    dimensao_1                  string,
    dimensao_2                  string,
    respondentes                bigint,
    salario_mediano_interpolado double,
    salario_mediano             double,
    salario_medio               double,
    p25                         double,
    p75                         double,
    amostra_suficiente          boolean
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/gold/remuneracao/';

CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.gold_diversidade (
    genero                      string,
    senioridade                 string,
    respondentes                bigint,
    salario_medio               double,
    salario_mediano_interpolado double,
    percentual                  double
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/gold/diversidade/';

CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.gold_tecnologias (
    categoria           string,
    tecnologia          string,
    respondentes        bigint,
    total_respondentes  bigint,
    taxa_adocao         double,
    posicao             int
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/gold/tecnologias/';

-- base_resposta e o denominador real da taxa: edicoes sem a pergunta de
-- IA aparecem com base_resposta = 0 e devem ser excluidas da leitura.
CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.gold_adocao_ia (
    senioridade     string,
    respondentes    bigint,
    base_resposta   bigint,
    taxa_adocao_ia  double
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/gold/adocao_ia/';

CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.gold_impacto_ia (
    senioridade                 string,
    usa_ia                      int,
    respondentes                bigint,
    salario_medio               double,
    salario_mediano_interpolado double,
    grupo                       string,
    amostra_suficiente          boolean
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/gold/impacto_ia/';

CREATE EXTERNAL TABLE IF NOT EXISTS state_of_data.gold_modelo_trabalho (
    regiao                      string,
    forma_trabalho              string,
    respondentes                bigint,
    salario_medio               double,
    salario_mediano_interpolado double,
    percentual                  double
)
PARTITIONED BY (ano int)
STORED AS PARQUET
LOCATION 's3://SEU-BUCKET/gold/modelo_trabalho/';

-- ---------------------------------------------------------------------
-- Registro das particoes. Obrigatorio depois de cada carga, caso nao
-- esteja usando Crawler.
-- ---------------------------------------------------------------------
MSCK REPAIR TABLE state_of_data.silver_respondentes;
MSCK REPAIR TABLE state_of_data.silver_tecnologias;
MSCK REPAIR TABLE state_of_data.gold_perfil_mercado;
MSCK REPAIR TABLE state_of_data.gold_remuneracao;
MSCK REPAIR TABLE state_of_data.gold_diversidade;
MSCK REPAIR TABLE state_of_data.gold_tecnologias;
MSCK REPAIR TABLE state_of_data.gold_adocao_ia;
MSCK REPAIR TABLE state_of_data.gold_impacto_ia;
MSCK REPAIR TABLE state_of_data.gold_modelo_trabalho;