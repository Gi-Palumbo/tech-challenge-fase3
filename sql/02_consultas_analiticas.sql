-- =====================================================================
-- Tech Challenge Fase 3 - Consultas analiticas (Amazon Athena)
-- =====================================================================
-- Cada bloco responde a uma pergunta do enunciado. Rode uma consulta por
-- vez no console do Athena e exporte o resultado em CSV para alimentar os
-- graficos da apresentacao.
--
-- METRICA DE REMUNERACAO: sempre salario_mediano_interpolado. A pesquisa
-- coleta renda em faixas; a mediana do ponto medio da faixa devolve o
-- mesmo valor para grupos diferentes e nao serve para comparacao.
--
-- Edicoes analisadas: 2023 (2023-2024), 2024 (2024-2025), 2025 (2025-2026).
-- =====================================================================


-- ---------------------------------------------------------------------
-- Q0. Sanidade: volume por edicao e cobertura dos campos criticos.
-- Rode SEMPRE antes das analises.
-- ---------------------------------------------------------------------
SELECT
    ano,
    COUNT(*)                                                    AS respondentes,
    COUNT(salario_mensal_estimado)                              AS com_salario,
    ROUND(100.0 * COUNT(salario_mensal_estimado) / COUNT(*), 1) AS pct_com_salario,
    COUNT(cargo)                                                AS com_cargo,
    COUNT(usa_ia)                                               AS com_resposta_ia,
    SUM(CASE WHEN senioridade = 'Nao informado' THEN 1 ELSE 0 END) AS sem_senioridade
FROM respondentes
GROUP BY ano
ORDER BY ano;


-- ---------------------------------------------------------------------
-- Q1. Como esta estruturado o mercado brasileiro de dados?
-- Composicao por senioridade ao longo das 3 edicoes.
-- ---------------------------------------------------------------------
WITH base AS (
    SELECT
        senioridade,
        CAST(ano AS INTEGER) AS ano_numero,
        CAST(respondentes AS BIGINT) AS quantidade
    FROM perfil_mercado
)
SELECT
    senioridade,
    SUM(CASE WHEN ano_numero = 2023 THEN quantidade ELSE 0 END) AS resp_2023,
    SUM(CASE WHEN ano_numero = 2024 THEN quantidade ELSE 0 END) AS resp_2024,
    SUM(CASE WHEN ano_numero = 2025 THEN quantidade ELSE 0 END) AS resp_2025
FROM base
GROUP BY senioridade
ORDER BY resp_2025 DESC;


-- ---------------------------------------------------------------------
-- Q1b. Top 15 cargos por volume de profissionais na edicao mais recente.
-- ---------------------------------------------------------------------
SELECT
    cargo,
    SUM(CAST(respondentes AS BIGINT)) AS respondentes,
    ROUND(SUM(CAST(percentual AS DOUBLE)), 2) AS pct_do_ano
FROM perfil_mercado
WHERE CAST(ano AS INTEGER) = (SELECT MAX(CAST(ano AS INTEGER)) FROM perfil_mercado)
  AND cargo IS NOT NULL
GROUP BY cargo
ORDER BY respondentes DESC
LIMIT 15;


-- ---------------------------------------------------------------------
-- Q2. Quais perfis profissionais sao mais valorizados?
-- Remuneracao por cargo, apenas grupos com amostra suficiente.
-- ---------------------------------------------------------------------
SELECT
    dimensao_1 AS cargo,
    respondentes,
    salario_mediano_interpolado AS salario,
    p25,
    p75
FROM remuneracao
WHERE recorte = 'cargo'
  AND CAST(amostra_suficiente AS BOOLEAN)
  AND dimensao_1 IS NOT NULL
  AND CAST(ano AS INTEGER) = (SELECT MAX(CAST(ano AS INTEGER)) FROM remuneracao)
ORDER BY salario DESC;


-- ---------------------------------------------------------------------
-- Q2b. Progressao salarial por senioridade nas 3 edicoes.
-- ---------------------------------------------------------------------
SELECT
    dimensao_1 AS senioridade,
    MAX(CASE WHEN CAST(ano AS INTEGER) = 2023 THEN salario_mediano_interpolado END) AS salario_2023,
    MAX(CASE WHEN CAST(ano AS INTEGER) = 2024 THEN salario_mediano_interpolado END) AS salario_2024,
    MAX(CASE WHEN CAST(ano AS INTEGER) = 2025 THEN salario_mediano_interpolado END) AS salario_2025
FROM remuneracao
WHERE recorte = 'senioridade'
  AND CAST(amostra_suficiente AS BOOLEAN)
GROUP BY dimensao_1
ORDER BY salario_2025;


-- ---------------------------------------------------------------------
-- Q2c. Retorno da experiencia e da formacao academica.
-- Insumo para a decisao de investir em capacitacao.
-- ---------------------------------------------------------------------
SELECT
    recorte,
    dimensao_1,
    respondentes,
    salario_mediano_interpolado AS salario
FROM remuneracao
WHERE recorte IN ('tempo_experiencia_dados', 'nivel_ensino')
  AND CAST(amostra_suficiente AS BOOLEAN)
  AND dimensao_1 IS NOT NULL
  AND CAST(ano AS INTEGER) = (SELECT MAX(CAST(ano AS INTEGER)) FROM remuneracao)
ORDER BY recorte, salario DESC;


-- ---------------------------------------------------------------------
-- Q3. Qual o cenario de diversidade de genero nas carreiras de dados?
-- Participacao feminina por senioridade: mostra o afunilamento na carreira.
-- ---------------------------------------------------------------------
SELECT
    senioridade,
    SUM(CASE WHEN genero = 'Feminino'  THEN CAST(respondentes AS BIGINT) ELSE 0 END) AS mulheres,
    SUM(CASE WHEN genero = 'Masculino' THEN CAST(respondentes AS BIGINT) ELSE 0 END) AS homens,
    ROUND(
        100.0 * SUM(CASE WHEN genero = 'Feminino' THEN CAST(respondentes AS BIGINT) ELSE 0 END)
        / NULLIF(SUM(CASE WHEN genero IN ('Feminino', 'Masculino') THEN CAST(respondentes AS BIGINT) ELSE 0 END), 0),
        1
    ) AS pct_feminino
FROM diversidade
GROUP BY senioridade
ORDER BY pct_feminino DESC;


-- ---------------------------------------------------------------------
-- Q3b. Diferenca de remuneracao por genero, controlando por senioridade.
-- ---------------------------------------------------------------------
WITH base AS (
    SELECT
        senioridade,
        MAX(CASE WHEN genero = 'Masculino' THEN salario_mediano_interpolado END) AS salario_masc,
        MAX(CASE WHEN genero = 'Feminino'  THEN salario_mediano_interpolado END) AS salario_fem
    FROM diversidade
    WHERE CAST(ano AS INTEGER) = (SELECT MAX(CAST(ano AS INTEGER)) FROM diversidade)
    GROUP BY senioridade
)
SELECT
    senioridade,
    salario_masc,
    salario_fem,
    ROUND(100.0 * (salario_fem - salario_masc) / salario_masc, 1) AS diferenca_pct
FROM base
WHERE salario_masc IS NOT NULL
  AND salario_fem IS NOT NULL
ORDER BY diferenca_pct;


-- ---------------------------------------------------------------------
-- Q4. Quais tecnologias apresentam maior adocao?
-- Top 10 por categoria na edicao mais recente.
-- Categorias: linguagem_uso, linguagem_preferida, banco_dados,
-- cloud_uso, cloud_preferida, ferramenta_bi.
-- ---------------------------------------------------------------------
SELECT
    categoria,
    tecnologia,
    respondentes,
    taxa_adocao,
    posicao
FROM tecnologias
WHERE CAST(ano AS INTEGER) = (SELECT MAX(CAST(ano AS INTEGER)) FROM tecnologias)
  AND CAST(posicao AS INTEGER) <= 10
ORDER BY categoria, posicao;


-- ---------------------------------------------------------------------
-- Q4b. Tecnologias que mais cresceram e mais cairam entre a primeira e a
-- ultima edicao. Insumo direto para a recomendacao de capacitacao.
-- Atencao: a questao de linguagens usadas no dia a dia (linguagem_uso)
-- nao existe na edicao 2025, por isso ela e excluida da comparacao.
-- ---------------------------------------------------------------------
WITH limites AS (
    SELECT MIN(CAST(ano AS INTEGER)) AS ano_ini, MAX(CAST(ano AS INTEGER)) AS ano_fim
    FROM tecnologias
    WHERE categoria <> 'linguagem_uso'
),
comparativo AS (
    SELECT
        t.categoria,
        t.tecnologia,
        MAX(CASE WHEN t.ano = l.ano_ini THEN t.taxa_adocao END) AS adocao_inicial,
        MAX(CASE WHEN t.ano = l.ano_fim THEN t.taxa_adocao END) AS adocao_final
    FROM tecnologias t
    CROSS JOIN limites l
    WHERE t.categoria <> 'linguagem_uso'
    GROUP BY t.categoria, t.tecnologia
)
SELECT
    categoria,
    tecnologia,
    adocao_inicial,
    adocao_final,
    ROUND(adocao_final - adocao_inicial, 2) AS variacao_pp
FROM comparativo
WHERE adocao_inicial IS NOT NULL
  AND adocao_final IS NOT NULL
  AND (adocao_inicial >= 5 OR adocao_final >= 5)
ORDER BY variacao_pp DESC;


-- ---------------------------------------------------------------------
-- Q5. Qual o indice de adocao de IA generativa?
-- O filtro base_resposta > 0 exclui edicoes sem a pergunta.
-- ---------------------------------------------------------------------
SELECT
    ano,
    senioridade,
    base_resposta,
    taxa_adocao_ia
FROM adocao_ia
WHERE CAST(base_resposta AS BIGINT) > 0
ORDER BY ano, taxa_adocao_ia DESC;


-- ---------------------------------------------------------------------
-- Q5b. Qual o impacto da IA na remuneracao?
-- Compara quem usa e quem nao usa, controlando por senioridade.
-- OBSERVACAO METODOLOGICA: e uma associacao, nao causalidade. O grupo
-- que usa IA tambem difere em setor, porte de empresa e cargo.
-- ---------------------------------------------------------------------
SELECT
    ano,
    senioridade,
    MAX(CASE WHEN grupo = 'Usa IA'     THEN salario_mediano_interpolado END) AS salario_usa_ia,
    MAX(CASE WHEN grupo = 'Nao usa IA' THEN salario_mediano_interpolado END) AS salario_nao_usa_ia,
    MAX(CASE WHEN grupo = 'Usa IA'     THEN CAST(respondentes AS BIGINT) END) AS n_usa_ia,
    MAX(CASE WHEN grupo = 'Nao usa IA' THEN CAST(respondentes AS BIGINT) END) AS n_nao_usa_ia
FROM impacto_ia
WHERE amostra_suficiente
GROUP BY ano, senioridade
ORDER BY ano, senioridade;


-- ---------------------------------------------------------------------
-- Q5c. Perfil do uso de IA: solucoes gratuitas, pagas ou assistentes de
-- codigo. Insumo para a politica de licenciamento e uso corporativo.
-- ---------------------------------------------------------------------
SELECT
    ano,
    tipo_uso_ia,
    COUNT(*) AS respondentes,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (PARTITION BY ano), 2) AS pct_do_ano
FROM respondentes
WHERE tipo_uso_ia IS NOT NULL
GROUP BY ano, tipo_uso_ia
ORDER BY ano, respondentes DESC;


-- ---------------------------------------------------------------------
-- Q6. Existem diferencas relevantes entre regioes, senioridades ou
-- modelos de trabalho?
-- ---------------------------------------------------------------------
SELECT
    ano,
    regiao,
    forma_trabalho,
    respondentes,
    percentual,
    salario_mediano_interpolado AS salario
FROM modelo_trabalho
WHERE regiao <> 'Nao informado'
  AND forma_trabalho <> 'Nao informado'
  AND CAST(ano AS INTEGER) = (SELECT MAX(CAST(ano AS INTEGER)) FROM modelo_trabalho)
ORDER BY regiao, respondentes DESC;


-- ---------------------------------------------------------------------
-- Q6b. Concentracao geografica e remuneracao por regiao.
-- Sustenta a recomendacao de contratacao remota para acessar talento
-- fora do eixo Sudeste/Sul.
-- ---------------------------------------------------------------------
SELECT
    r.ano,
    r.dimensao_1 AS regiao,
    r.respondentes,
    ROUND(100.0 * CAST(r.respondentes AS DOUBLE) / CAST(t.total AS DOUBLE), 2) AS pct_do_ano,
    r.salario_mediano_interpolado AS salario
FROM remuneracao r
JOIN (
    SELECT ano, SUM(CAST(respondentes AS BIGINT)) AS total
    FROM remuneracao
    WHERE recorte = 'regiao'
    GROUP BY ano
) t ON t.ano = r.ano
WHERE r.recorte = 'regiao'
  AND r.dimensao_1 <> 'Nao informado'
ORDER BY r.ano, r.respondentes DESC;


-- ---------------------------------------------------------------------
-- Q6c. Diferenca de remuneracao entre modelos de trabalho.
-- ---------------------------------------------------------------------
SELECT
    dimensao_1 AS forma_trabalho,
    MAX(CASE WHEN CAST(ano AS INTEGER) = 2023 THEN salario_mediano_interpolado END) AS salario_2023,
    MAX(CASE WHEN CAST(ano AS INTEGER) = 2024 THEN salario_mediano_interpolado END) AS salario_2024,
    MAX(CASE WHEN CAST(ano AS INTEGER) = 2025 THEN salario_mediano_interpolado END) AS salario_2025,
    MAX(CASE WHEN CAST(ano AS INTEGER) = 2025 THEN CAST(respondentes AS BIGINT) END) AS n_2025
FROM remuneracao
WHERE recorte = 'forma_trabalho'
  AND dimensao_1 <> 'Nao informado'
  AND CAST(amostra_suficiente AS BOOLEAN)
GROUP BY dimensao_1
ORDER BY salario_2025 DESC;


-- ---------------------------------------------------------------------
-- Q7. Oportunidades por setor: onde estao os profissionais e quanto
-- paga o setor financeiro em relacao aos demais.
-- ---------------------------------------------------------------------
SELECT
    dimensao_1 AS setor,
    respondentes,
    salario_mediano_interpolado AS salario
FROM remuneracao
WHERE recorte = 'setor_empresa'
  AND CAST(amostra_suficiente AS BOOLEAN)
  AND dimensao_1 IS NOT NULL
  AND CAST(ano AS INTEGER) = (SELECT MAX(CAST(ano AS INTEGER)) FROM remuneracao)
ORDER BY salario DESC;