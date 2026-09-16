# Roteiro do material executivo - Tech Challenge Fase 3

Estrutura para o PowerPoint/PDF. Os números abaixo vêm da execução real do
pipeline sobre as 3 edições (14.005 respondentes) e estão em `data/gold/`.
Os gráficos citados estão em `data/graficos/`.

Regra de ouro: todo gráfico precisa de uma frase de conclusão. Se não houver
conclusão, o gráfico não entra.

---

## Slide 1 - Capa

- Título: "O mercado brasileiro de Dados e IA: evidências para decisão"
- Subtítulo: "Análise das 3 últimas edições do State of Data Brasil"
- Integrantes, curso, fase, data.

## Slide 2 - O problema de negócio

Uma instituição financeira de grande porte quer expandir sua área de Dados,
Analytics e IA e precisa de evidências para decidir **quem contratar, a que
custo, o que capacitar e onde buscar talento**.

Quatro perguntas de decisão que este material responde:
1. Quanto custa cada perfil e em que ponto da carreira o salário salta?
2. Em quais tecnologias investir?
3. A IA generativa já é diferencial ou virou requisito básico?
4. Como acessar talento fora do eixo Sudeste/Sul?

## Slide 3 - Dados utilizados

| Edição | `ano` | Respondentes |
| --- | --- | --- |
| State of Data Brazil 2023-2024 | 2023 | 5.293 |
| State of Data Brazil 2024-2025 | 2024 | 5.217 |
| State of Data Brazil 2025-2026 | 2025 | 3.495 |

Total: **14.005 respondentes**, 388 a 403 colunas por edição.
Fonte: Data Hackers + Bain & Company (Kaggle).

## Slide 4 - Arquitetura da solução (obrigatório)

Inserir a imagem exportada de `diagrams/arquitetura_aws.drawio`.

Narrativa: "Os dados brutos do Kaggle são ingeridos no S3, tratados em Spark via
Glue Jobs, organizados em Bronze/Silver/Gold, catalogados no Glue Data Catalog e
consultados via Athena e Glue Notebook."

## Slide 5 - Estratégia de dados em camadas

| Camada | Conteúdo | Volume |
| --- | --- | --- |
| Bronze | CSV bruto das 3 edições, imutável | 3 arquivos |
| Silver | Modelo canônico unificado | 14.005 linhas x 30 colunas + 93.706 linhas de tecnologias |
| Gold | 7 tabelas agregadas por pergunta de negócio | ~1.500 linhas |

**O ponto a destacar**: as três edições têm questionários diferentes. Em 2023 o
cabeçalho é `('P2_h ', 'Faixa salarial')`; em 2024/2025 é `2.h_faixa_salarial`.
A seção de tecnologias foi renumerada em 2025. A camada Silver é o que torna a
comparação entre anos possível.

## Slide 6 - Tratamento de dados: quatro decisões que mudaram o resultado

Este slide diferencia o trabalho. Mostre o "antes e depois":

| Problema encontrado | Efeito se ignorado | Tratamento |
| --- | --- | --- |
| Renda coletada em faixas | Todas as regiões davam R$ 10.000 | Mediana interpolada |
| Cobertura de resposta cai de 71% para 60% | Toda tecnologia "perdia" ~11pp | Denominador = quem respondeu |
| Gestor não responde nível | 2.668 gestores em "Não informado" | Reclassificação via "atua como gestor" |
| `linguagem_preferida` virou múltipla escolha | SQL "cresceria" de 1,4% para 50,5% | Série excluída da comparação |

Exemplo concreto para a narrativa: com o denominador corrigido, a AWS sai de uma
queda aparente de 12pp para um **crescimento real de 6pp**.

---

## Slides 7 a 15 - Análises

| Slide | Pergunta | Gráfico | Conclusão sugerida |
| --- | --- | --- | --- |
| 7 | Como está estruturado o mercado? | `01_perfil_senioridade`, `02_top_cargos` | Mercado concentrado em Pleno/Sênior; Analista de Dados é o cargo mais numeroso |
| 8 | Quais perfis são mais valorizados? | `03_salario_senioridade` | Júnior R$ 3.500 → Pleno R$ 7.505 → Sênior R$ 12.357 → Especialista R$ 17.326 → Gestão R$ 18.236 |
| 9 | Quais cargos pagam mais? | `06_salario_por_cargo` | ML/AI Engineer lidera com R$ 16.251; Analytics Engineer R$ 12.264 |
| 10 | Vale investir em formação e experiência? | `07_retorno_experiencia` | Menos de 1 ano R$ 3.406 → mais de 10 anos R$ 20.000; mestrado R$ 15.262 vs graduação R$ 8.929 |
| 11 | Quais tecnologias têm maior adoção? | `08_tecnologias_*` | Power BI 59%, AWS 48%, PostgreSQL 37% |
| 12 | Quais tecnologias crescem? | `09_evolucao_*` | Databricks +11,5pp, PostgreSQL +8,4pp, S3 +7,9pp, AWS +6,0pp; Tableau -5,3pp |
| 13 | Qual a adoção de IA e seu impacto? | `10_adocao_ia`, `11_impacto_ia` | 80% → 94% → 97%. Salário de quem usa e não usa é equivalente: **IA virou requisito, não diferencial** |
| 14 | Como está a diversidade de gênero? | `12_diversidade_genero`, `14_participacao_feminina`, `13_gap_salarial_genero` | Funil: 28,4% em Júnior → 18,8% em Gestão. Diferença salarial -12% (Júnior) e -13% (Sênior) |
| 15 | Há diferenças por região e modelo? | `04_salario_regiao`, `05_salario_forma_trabalho`, `15_modelo_trabalho_regiao` | Remoto R$ 12.234 vs presencial R$ 6.635. Sudeste concentra 64% e paga R$ 11.048; Nordeste R$ 8.774 |

---

## Slide 16 - Principais insights

Cinco achados, cada um com o número que o sustenta:

1. **O salto de carreira está entre Pleno e Sênior**: +65% (R$ 7.505 → R$ 12.357).
   É aí que a retenção importa mais.
2. **IA generativa deixou de ser diferencial**: 97% de adoção em 2025, e o
   salário de quem usa é estatisticamente equivalente ao de quem não usa quando
   se controla por senioridade.
3. **Trabalho remoto paga 84% mais que presencial** (R$ 12.234 vs R$ 6.635) —
   ainda que parte da diferença reflita o perfil de quem acessa vagas remotas.
4. **Há um funil de gênero, não um teto único**: a participação feminina cai
   progressivamente de 28,4% (Júnior) para 18,8% (Gestão).
5. **A stack de dados migrou para lakehouse e cloud**: Databricks +11,5pp e
   S3 +7,9pp, com AWS crescendo para 48% de uso.

## Slide 17 - Recomendações estratégicas

| Recomendação | Evidência |
| --- | --- |
| Calibrar faixas salariais por senioridade usando a mediana de mercado; o setor financeiro paga R$ 11.864, 2º lugar, atrás de Internet/Ecommerce (R$ 12.626) | Slides 8 e 9 |
| Priorizar retenção na transição Pleno → Sênior, onde o salário salta 65% | Slide 8 |
| Investir em capacitação em Databricks, PostgreSQL e AWS, as tecnologias em alta | Slide 12 |
| Tratar IA generativa como competência básica e política de licenciamento, não como diferencial de contratação | Slide 13 |
| Adotar contratação remota/híbrida para acessar talento fora do Sudeste, com custo menor no Nordeste | Slide 15 |
| Criar metas de diversidade **por nível de senioridade**, não apenas no total, dado o formato de funil | Slide 14 |
| Formar pipeline interno de juniores (R$ 3.500) com trilha para pleno, dada a escassez de sênior | Slides 7 e 8 |

## Slide 18 - Limitações metodológicas (não omitir)

- **Amostra voluntária**: respondentes da comunidade Data Hackers, com viés para
  profissionais engajados. Não representa o mercado brasileiro como um todo.
- **Amostra decrescente**: 5.293 → 5.217 → 3.495. A edição 2025 tem ~1/3 menos
  respostas, o que amplia a incerteza nos recortes menores.
- **Renda em faixas**: faixas abertas no topo usam o limite inferior, o que
  **subestima** os salários mais altos.
- **Região Norte tem 36 respondentes com salário em 2025**: não sustenta
  conclusão regional isolada.
- **Comparabilidade entre edições**: o questionário muda; duas séries de
  linguagem foram excluídas da análise temporal por esse motivo.
- **Associação não é causalidade**: nenhuma diferença salarial aqui controla
  simultaneamente senioridade, setor, porte de empresa e região.

## Slide 19 - Conclusão

Retomar as quatro perguntas do slide 2 e responder cada uma em uma frase apoiada
em número.

## Anexos

- Diagrama da arquitetura em tamanho cheio.
- Inventário de colunas por edição (`data/inventario_colunas.csv`).
- Lista dos scripts, notebooks e consultas entregues.
