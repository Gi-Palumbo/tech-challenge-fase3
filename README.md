# Tech Challenge Fase 3 - Big Data & Analytics

giovanna zambon gennari palumbo
nathan ramos tanabe

Solução de Engenharia de Dados e Analytics sobre a pesquisa **State of Data
Brasil** (Data Hackers + Bain & Company), com pipeline em camadas
Bronze/Silver/Gold na AWS usando S3, Glue (PySpark), Glue Data Catalog e Athena.

## Modelo de dados

**Silver** (Parquet, particionado por `ano`):

- `silver_respondentes` - 1 linha por respondente, modelo canônico unificado das
  3 edições (14.005 linhas, 30 colunas). Campos padronizados: `senioridade`,
  `forma_trabalho`, `genero`, `regiao`, `salario_mensal_estimado`, `usa_ia`.
- `silver_tecnologias` - tabela longa `(ano, id_respondente, categoria, tecnologia)`
  com 93.706 linhas, resultado do explode das respostas de múltipla escolha.

**Gold** (uma tabela por pergunta de negócio): `perfil_mercado`, `remuneracao`,
`diversidade`, `tecnologias`, `adocao_ia`, `impacto_ia`, `modelo_trabalho`.

> `gold_remuneracao` está em **formato longo**: a coluna `recorte` indica quais
> dimensões estão em `dimensao_1`/`dimensao_2`. Cruzar todas as dimensões de uma
> vez pulverizaria a amostra, por isso cada recorte é agregado separadamente e
> grupos com menos de 30 respondentes são marcados com `amostra_suficiente = false`.

## Decisões metodológicas (obrigatório citar na apresentação)

Estas quatro decisões foram tomadas porque os dados brutos **induzem a erro**.
Cada uma delas foi validada contra os CSVs reais.

### 1. Remuneração: mediana interpolada, não mediana simples

A pesquisa coleta renda em **faixas**, não em valor exato. A mediana do ponto
médio da faixa é cega: ela devolve o centro da faixa mediana e fazia *todas* as
regiões exibirem exatamente R$ 10.000. A métrica correta para dados agrupados é
a mediana interpolada (`salario_mediano_interpolado`):

```
mediana = L + ((N/2 - F) / f) * w
```

Com ela, Sudeste (R$ 11.048) e Nordeste (R$ 8.774) passam a se distinguir.
Faixas abertas no topo usam o limite inferior, escolha conservadora que
**subestima** os salários mais altos.

### 2. Adoção de tecnologia: denominador é quem respondeu a questão

A cobertura das questões de tecnologia cai de **71% (2023) para 60% (2025)**.
Usando o total de respondentes da edição como denominador, toda tecnologia
parecia perder ~11 pontos de adoção. Com o denominador correto (`base_resposta`),
a AWS passa de uma queda falsa de 12pp para um **crescimento real de 6pp**
(42,3% → 48,3%).

### 3. Senioridade dos gestores é reconstruída

A pesquisa não pergunta o nível (júnior/pleno/sênior) a quem atua como gestor:
essas pessoas respondem outra questão e o campo fica vazio **por desenho**. Sem
tratamento, 2.668 gestores caíam em "Não informado", que se tornava o segundo
maior grupo. São reclassificados como `Gestao` a partir da questão "atua como
gestor". O nível `Especialista/Staff+`, criado em 2025, também ganhou categoria
própria em vez de ser fundido com Sênior.

### 4. Nem toda série histórica é comparável

Duas categorias **não** podem ser comparadas entre anos:

- `linguagem_uso`: a questão não existe na edição 2025;
- `linguagem_preferida`: passou de escolha única para múltipla em 2025, o que
  faria o SQL "crescer" de 1,4% para 50,5% por mudança de questionário.

A coluna `itens_por_respondente` em `gold_tecnologias` permite detectar isso.
Categorias comparáveis: `banco_dados`, `cloud_uso`, `cloud_preferida`,
`ferramenta_bi`.

---

# Passo a passo de execução

## Etapa 1 - Baixar as 3 bases do Kaggle

Todas as edições ficam no perfil da Data Hackers no Kaggle:
https://www.kaggle.com/datahackers/datasets

As **três últimas edições publicadas** são:

| Edição no Kaggle | `ano` usado no projeto |
| --- | --- |
| State of Data Brazil 2023-2024 | 2023 |
| State of Data Brazil 2024-2025 | 2024 |
| State of Data Brazil 2025-2026 | 2025 |

Não use as edições 2021-2022 e 2022-2023, nem a "Data Hackers Survey 2019-2020"
(pesquisa diferente, com formato antigo).

Baixe o CSV de cada uma e coloque os três arquivos em `data/raw/`.

**Importante**: o pipeline localiza os arquivos pelo **ano no nome**. Garanta que
cada arquivo contenha `2023`, `2024` e `2025` no nome, respectivamente, seguindo
a coluna `ano` da tabela acima. Se o nome baixado não tiver o ano, renomeie. A
convenção adotada é o **primeiro ano do título** da edição.

## Etapa 2 - Validar o mapeamento de colunas

```powershell
python scripts/00_explorar_schema.py
```

Os CSVs da pesquisa têm cabeçalhos em formato de tupla, por exemplo
`('P1_a ', 'Idade')`, e **os códigos das questões mudam entre edições**. Por isso
o mapeamento em `config/mapeamento_colunas.json` resolve cada campo por regex no
rótulo, com o código da questão como alternativa.

Os CSVs das 3 edições usam **formatos de cabeçalho diferentes**:

| Edição | Formato | Exemplo |
| --- | --- | --- |
| 2023 | tupla | `('P2_h ', 'Faixa salarial')` |
| 2024 / 2025 | texto plano | `2.h_faixa_salarial` |

Os dois são normalizados para um código pontilhado (`P2_h` → `2.h`), que é a
chave do mapeamento. Os códigos das seções 1 e 2 são estáveis, mas **a seção 4
foi renumerada em 2025** (BI passou de `4.j` para `4.g`) e o modelo de trabalho
mudou de `2.r` para `2.q`. Por isso cada campo declara o código **por ano** em
`config/mapeamento_colunas.json`, com `null` quando a questão não existe.

O script imprime, para cada edição, qual coluna resolveu cada campo, o que não
foi encontrado e o que não se aplica, e grava `data/inventario_colunas.csv`.

Resultado esperado (já validado contra os CSVs reais):

```
2023: 30 campos resolvidos, 0 nao encontrados
2024: 30 campos resolvidos, 0 nao encontrados
2025: 29 campos resolvidos, 0 nao encontrados
Todos os campos criticos foram resolvidos nas edicoes encontradas.
```

**Se algum campo marcado `[CRITICO]` não resolver**, abra
`data/inventario_colunas.csv`, encontre o código real daquela pergunta na edição
em questão e corrija `config/mapeamento_colunas.json`.

## Etapa 3 - Rodar o pipeline local (recomendado antes da AWS)

```powershell
python -m pip install -r requirements.txt
python scripts/local/pipeline_local.py
python scripts/local/gerar_graficos.py
```

Gera `data/silver/`, `data/gold/` e 22 PNGs em `data/graficos/`. Usa exatamente
as mesmas regras de negócio dos Glue Jobs, então serve para conferir se os
números fazem sentido **antes** de gastar sessão do AWS Academy.

> Para testar sem os dados reais: `python tests/gerar_amostra_sintetica.py` e
> depois rode o pipeline com `--dir-raw data/amostra`.

## Resultados já obtidos (base para a apresentação)

Números extraídos da execução real do pipeline sobre as 3 edições
(14.005 respondentes). Use-os como referência para conferir se sua execução na
AWS chegou ao mesmo lugar.

**Remuneração mensal por senioridade (2025, mediana interpolada)**

| Senioridade | Salário | n |
| --- | --- | --- |
| Júnior | R$ 3.500 | 518 |
| Pleno | R$ 7.505 | 776 |
| Sênior | R$ 12.357 | 858 |
| Especialista/Staff+ | R$ 17.326 | 349 |
| Gestão | R$ 18.236 | 2.668 (3 edições) |

**Retorno da experiência (2025)**: menos de 1 ano R$ 3.406 → mais de 10 anos
R$ 20.000. **Formação**: graduação R$ 8.929 → mestrado R$ 15.262 → doutorado
R$ 15.408.

**Modelo de trabalho (2025)**: remoto R$ 12.234 (n=1.282), híbrido R$ 11.230
(n=1.276), presencial R$ 6.635 (n=670).

**Concentração geográfica**: Sudeste 61% → 64% da amostra. Nordeste paga
R$ 8.774 contra R$ 11.048 do Sudeste.

**Adoção de IA generativa**: 80% (2023) → 94% (2024) → 97% (2025). O salário de
quem usa e de quem não usa IA é praticamente igual quando se controla por
senioridade — a IA virou requisito básico, não diferencial salarial.

**Diversidade**: participação feminina cai de 28,4% em Júnior para 24,9% em
Pleno, 21,4% em Sênior e 18,8% em Gestão — um funil claro. Diferença salarial de
-12% (Júnior) e -13% (Sênior) em 2025.

**Tecnologias que mais cresceram (2023 → 2025)**: Databricks +11,5pp,
PostgreSQL +8,4pp, S3 +7,9pp, AWS +6,0pp. Maior queda: Tableau -5,3pp.
Power BI lidera BI com 59%.

**Setor financeiro**: R$ 11.864 de mediana, 2º lugar entre os setores, atrás de
Internet/Ecommerce (R$ 12.626) — dado direto para a política salarial do case.

## Etapa 4 - Preparar o ambiente AWS Academy

1. Inicie o laboratório e aguarde o indicador ficar verde.
2. Em **AWS Details**, copie as credenciais (`aws_access_key_id`,
   `aws_secret_access_key`, `aws_session_token`).
3. A sessão do AWS Academy **expira** (tipicamente algumas horas) e as
   credenciais mudam a cada início. O S3 persiste entre sessões; jobs em
   execução, não. Planeje rodar os jobs em uma sessão só.
4. Use sempre a role **LabRole** ao criar Glue Jobs e Crawlers: é a única com
   permissão no ambiente do Academy.

Se for usar o AWS CLI localmente, instale-o e configure o perfil com as três
credenciais acima (incluindo o `session_token`).

## Etapa 5 - Criar o bucket e subir a camada Bronze

Escolha um nome único, por exemplo `tech-challenge-fase3-<seu-nome>`.

```powershell
aws s3 mb s3://SEU-BUCKET

# Bronze: um prefixo por edição (os Glue Jobs esperam exatamente estes caminhos)
aws s3 cp "data/raw/<arquivo 2023>.csv" s3://SEU-BUCKET/bronze/state_of_data_2023/
aws s3 cp "data/raw/<arquivo 2024>.csv" s3://SEU-BUCKET/bronze/state_of_data_2024/
aws s3 cp "data/raw/<arquivo 2025>.csv" s3://SEU-BUCKET/bronze/state_of_data_2025/

# Configuração e scripts
aws s3 cp config/mapeamento_colunas.json s3://SEU-BUCKET/config/
aws s3 cp scripts/glue/job_01_bronze_para_silver.py s3://SEU-BUCKET/scripts/
aws s3 cp scripts/glue/job_02_silver_para_gold.py   s3://SEU-BUCKET/scripts/
```

Dá para fazer tudo pelo Console do S3 se preferir; só mantenha os mesmos
prefixos, pois os anos em `config/mapeamento_colunas.json` definem os caminhos.

## Etapa 6 - Empacotar o módulo compartilhado

O Job 1 importa `src/sod`, então esse módulo precisa ir como dependência:

```powershell
Compress-Archive -Path src/sod -DestinationPath dist/sod.zip -Force
aws s3 cp dist/sod.zip s3://SEU-BUCKET/scripts/
```

## Etapa 7 - Criar e executar os Glue Jobs

No Console: **AWS Glue > ETL jobs > Script editor > Spark**, e em cada job:

**Job 1 - `sod_bronze_para_silver`**

| Configuração | Valor |
| --- | --- |
| Script | `s3://SEU-BUCKET/scripts/job_01_bronze_para_silver.py` |
| IAM Role | `LabRole` |
| Glue version | 4.0 |
| Workers | 2 (G.1X) |
| Python library path | `s3://SEU-BUCKET/scripts/sod.zip` |

Job parameters:

```
--BUCKET            SEU-BUCKET
--PREFIXO_BRONZE    bronze
--PREFIXO_SILVER    silver
--CAMINHO_CONFIG    s3://SEU-BUCKET/config/mapeamento_colunas.json
```

**Job 2 - `sod_silver_para_gold`**

Mesmas configurações (sem necessidade do `sod.zip`), com os parâmetros:

```
--BUCKET            SEU-BUCKET
--PREFIXO_SILVER    silver
--PREFIXO_GOLD      gold
--MIN_RESPONDENTES  30
```

Execute o Job 1, confirme o sucesso, e só então o Job 2. **Leia os logs no
CloudWatch**: o Job 1 imprime quais campos resolveu em cada edição e quais não
resolveu — é a sua validação de que o tratamento funcionou.

## Etapa 8 - Catalogar as tabelas

Opção recomendada, **Glue Crawler** (é o que o enunciado pede):

1. **AWS Glue > Crawlers > Create crawler**
2. Data sources: `s3://SEU-BUCKET/silver/` e `s3://SEU-BUCKET/gold/`
3. IAM role: `LabRole`
4. Database de destino: `state_of_data` (crie se não existir)
5. Execute e confira as tabelas criadas no Data Catalog.

Alternativa manual: execute `sql/01_ddl_athena.sql` no Athena, trocando
`SEU-BUCKET`. Nesse caso, rode os `MSCK REPAIR TABLE` do fim do arquivo para
registrar as partições de ano.

Antes da primeira consulta, o Athena exige um local de resultados: configure
`s3://SEU-BUCKET/athena-results/` em **Settings**.

## Etapa 9 - Consultas analíticas

Execute os blocos de `sql/02_consultas_analiticas.sql` no Athena, **começando
pela `Q0`** (sanidade e cobertura dos campos). Cada bloco seguinte responde a
uma pergunta do enunciado. Exporte os resultados em CSV para montar os gráficos.

## Etapa 10 - Notebook e gráficos

Abra `notebooks/analises_glue_notebook.ipynb` no **Glue Notebook** (Glue >
Notebooks > Jupyter Notebook, role `LabRole`), ajuste a variável `BUCKET` e
execute as células. Ele roda as análises em Spark SQL e gera os gráficos.

Se preferir iterar mais rápido nos gráficos, rode
`scripts/local/gerar_graficos.py` sobre os CSVs exportados da célula final do
notebook (que grava em `s3://SEU-BUCKET/exportacao/`).

## Etapa 11 - Montar as entregas

1. **Material executivo** - siga `presentation/roteiro_apresentacao.md`.
2. **Diagrama** - abra `diagrams/arquitetura_aws.drawio` em
   https://app.diagrams.net, ajuste o nome do bucket, exporte como PNG e insira
   no material executivo (o enunciado exige o diagrama dentro da apresentação).
3. **Scripts e notebooks** - este repositório.

---

## Testes

```powershell
python tests/test_mapeamento.py
```

Ambiente usado no desenvolvimento: Python 3.14 + pandas/matplotlib. O PySpark
não roda localmente nessa versão, então o `pipeline_local.py` replica em pandas
as mesmas regras dos Glue Jobs para iteração rápida (~2 min sobre os 3 CSVs).

42 testes cobrindo os casos reais encontrados nos dados:

- parser dos **dois formatos** de cabeçalho, incluindo rótulos com acento e
  apóstrofo (`LLM's`) e a equivalência `P2_h` ≡ `2.h`;
- resolução exata por código, sem confundir a questão `4.h` com as colunas dummy
  `4.h.3` / `4.h.7`;
- renumeração da seção 4 em 2025 e questões ausentes marcadas como
  "não aplicável" em vez de erro;
- faixa salarial malformada real da edição 2025 (`de R$ 25.001/mês a R$ 3000/mês`);
- mediana interpolada, incluindo o caso em que ela distingue grupos que a mediana
  simples igualaria;
- nulos do pandas/Spark (`nan`, `<NA>`, `NaT`) que antes viravam a categoria
  "Outro";
- respostas multivaloradas que **não** podem ser quebradas por barra
  (`SAS/Stata`, `Salesforce/Einstein Analytics`);
- classificação de uso de IA, cujo texto tem vírgula fora de parênteses e por
  isso não pode ser separado por vírgula.

## Limitações a declarar na apresentação

- **Amostra voluntária**: respondentes da comunidade Data Hackers, com viés para
  profissionais engajados. Não representa o mercado brasileiro como um todo.
- **Amostra decrescente**: 5.293 → 5.217 → 3.495 respondentes. A edição 2025 tem
  ~1/3 menos respostas, ampliando a incerteza dos recortes menores.
- **Faixas abertas no topo** usam o limite inferior, o que subestima os salários
  mais altos.
- **Corte de amostra**: grupos com menos de 30 respondentes são sinalizados em
  `amostra_suficiente`, não excluídos silenciosamente.
- **Região Norte** tem apenas 36 respondentes com salário em 2025: não sustenta
  conclusão regional.
- **Associação não é causalidade**: as diferenças salariais não controlam
  simultaneamente senioridade, setor, porte e região.

## Problemas comuns

| Sintoma | Causa provável |
| --- | --- |
| `ModuleNotFoundError: sod` no Job 1 | `sod.zip` não informado em Python library path |
| Campos críticos não resolvidos | Códigos de questão mudaram; ajuste `config/mapeamento_colunas.json` (Etapa 2) |
| Salário igual para todos os grupos | Você usou `salario_mediano` em vez de `salario_mediano_interpolado` |
| Toda tecnologia "caindo" em 2025 | Denominador errado; use `taxa_adocao` (base = `base_resposta`) |
| "Não informado" é o maior grupo de senioridade | `atua_como_gestor` não foi mapeado; confira a Etapa 2 |
| Athena retorna 0 linhas | Partições não registradas: rode o Crawler ou `MSCK REPAIR TABLE` |
| `AccessDenied` no Glue | Job criado com role diferente de `LabRole` |
| Credenciais inválidas no CLI | Sessão do Academy expirou; recopie as 3 credenciais |
| Gráfico sai vazio | Recorte sem grupo com amostra suficiente; confira a `Q0` |
