"""Testes do nucleo de mapeamento.

Os cabecalhos e valores usados aqui foram extraidos dos CSVs reais das 3
edicoes, incluindo os casos problematicos encontrados na inspecao dos dados.

Rodar com: python tests/test_mapeamento.py (ou python -m pytest -q)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sod import mapeamento as m  # noqa: E402

# Formato da edicao 2023: cabecalho em tupla.
CABECALHOS_2023 = [
    "('P0', 'id')",
    "('P1_a ', 'Idade')",
    "('P1_b ', 'Genero')",
    "('P1_i ', 'Estado onde mora')",
    "('P1_i_1 ', 'uf onde mora')",
    "('P1_i_2 ', 'Regiao onde mora')",
    "('P1_m ', 'Área de Formação')",
    "('P2_f ', 'Cargo Atual')",
    "('P2_g ', 'Nivel')",
    "('P2_h ', 'Faixa salarial')",
    "('P2_k ', 'Você está satisfeito na sua empresa atual?')",
    "('P2_r ', 'Atualmente qual a sua forma de trabalho?')",
    "('P2_s ', 'Qual a forma de trabalho ideal para você?')",
    "('P4_d ', 'Quais das linguagens listadas abaixo você utiliza no trabalho?')",
    "('P4_d_15 ', 'Não utilizo nenhuma linguagem')",
    "('P4_f ', 'Entre as linguagens listadas abaixo, qual é a sua preferida?')",
    "('P4_h ', 'Dentre as opções listadas, qual sua Cloud preferida?')",
    "('P4_h_7 ', 'Cloud Própria')",
    "('P4_j ', 'Ferramenta de BI utilizada no dia a dia')",
    "('P4_m ', 'Utiliza ChatGPT ou LLMs no trabalho?')",
]

# Formato das edicoes 2024/2025: cabecalho em texto plano.
CABECALHOS_2025 = [
    "0.a_token",
    "1.a_idade",
    "1.b_genero",
    "1.i_estado_onde_mora",
    "1.i.1_uf_onde_mora",
    "1.i.2_regiao_onde_mora",
    "1.m_área_de_formação",
    "2.f_cargo_atual",
    "2.g_nivel",
    "2.h_faixa_salarial",
    "2.k_satisfeito_atualmente",
    "2.q_modelo_de_trabalho_atual",
    "2.r_modelo_de_trabalho_ideal",
    "3.f.8 Não sei opinar sobre o uso de IA Generativa e LLMs na empresa",
    "4.c_linguagem_preferida",
    "4.d_banco_de_dados_(dia_a_dia)",
    "4.e_cloud_(dia_a_dia)",
    "4.g_ferramenta_de_bi_(dia_a_dia)",
    "4.j_usa_chatgpt_ou_copilot_no_trabalho?",
]


# --- Parse de cabecalho ---

def test_parse_tupla():
    col = m.parse_cabecalho("('P1_a ', 'Idade')")
    assert (col.codigo, col.rotulo) == ("P1_a", "Idade")


def test_parse_tupla_com_acento():
    col = m.parse_cabecalho("('P1_m ', 'Área de Formação')")
    assert col.rotulo_normalizado == "area de formacao"


def test_parse_tupla_com_aspas_duplas():
    col = m.parse_cabecalho("('P5_a ', \"Você usa LLM's no trabalho?\")")
    assert col.codigo == "P5_a"
    assert "LLM's" in col.rotulo


def test_parse_plano():
    col = m.parse_cabecalho("2.h_faixa_salarial")
    assert (col.codigo, col.rotulo) == ("2.h", "faixa_salarial")


def test_parse_plano_com_subitem_e_espaco():
    col = m.parse_cabecalho("3.f.8 Não sei opinar sobre o uso de IA Generativa")
    assert col.codigo == "3.f.8"


def test_parse_plano_com_parenteses_no_rotulo():
    col = m.parse_cabecalho("4.d_banco_de_dados_(dia_a_dia)")
    assert col.codigo == "4.d"


def test_parse_fora_dos_formatos():
    col = m.parse_cabecalho("idade")
    assert (col.codigo, col.rotulo) == ("", "idade")


# --- Normalizacao de codigo: os dois formatos convergem ---

def test_normalizar_codigo_equivalencia_entre_formatos():
    assert m.normalizar_codigo("P2_h") == m.normalizar_codigo("2.h") == "2.h"
    assert m.normalizar_codigo("P1_i_1") == m.normalizar_codigo("1.i.1") == "1.i.1"


def test_normalizar_codigo_vazio():
    assert m.normalizar_codigo(None) == ""
    assert m.normalizar_codigo("") == ""


# --- Resolucao de colunas ---

def test_resolver_coluna_nos_dois_formatos():
    assert m.resolver_coluna(CABECALHOS_2023, "2.h") == "('P2_h ', 'Faixa salarial')"
    assert m.resolver_coluna(CABECALHOS_2025, "2.h") == "2.h_faixa_salarial"


def test_resolver_coluna_nao_confunde_questao_com_dummy():
    # "4.h" nao pode resolver para a coluna dummy "P4_h_7" (Cloud Propria).
    assert m.resolver_coluna(CABECALHOS_2023, "4.h") == "('P4_h ', 'Dentre as opções listadas, qual sua Cloud preferida?')"
    assert m.resolver_coluna(CABECALHOS_2023, "4.d") == "('P4_d ', 'Quais das linguagens listadas abaixo você utiliza no trabalho?')"


def test_resolver_coluna_inexistente():
    assert m.resolver_coluna(CABECALHOS_2023, "9.z") is None
    assert m.resolver_coluna(CABECALHOS_2023, None) is None


def test_plano_2023_com_config_real():
    config = m.carregar_config()
    plano = m.montar_plano_colunas(CABECALHOS_2023, config, 2023)
    assert plano["campos"]["faixa_salarial"] == "('P2_h ', 'Faixa salarial')"
    assert plano["campos"]["forma_trabalho"] == "('P2_r ', 'Atualmente qual a sua forma de trabalho?')"
    assert plano["campos"]["regiao"] == "('P1_i_2 ', 'Regiao onde mora')"
    assert plano["tecnologias"]["linguagem_uso"] == "('P4_d ', 'Quais das linguagens listadas abaixo você utiliza no trabalho?')"
    assert plano["ia"]["uso_ia_pessoal"] == "('P4_m ', 'Utiliza ChatGPT ou LLMs no trabalho?')"


def test_plano_2025_usa_a_renumeracao_da_secao_4():
    config = m.carregar_config()
    plano = m.montar_plano_colunas(CABECALHOS_2025, config, 2025)
    # Em 2025 o modelo de trabalho passou de 2.r para 2.q.
    assert plano["campos"]["forma_trabalho"] == "2.q_modelo_de_trabalho_atual"
    assert plano["campos"]["forma_trabalho_ideal"] == "2.r_modelo_de_trabalho_ideal"
    # E a secao 4 foi renumerada.
    assert plano["tecnologias"]["banco_dados"] == "4.d_banco_de_dados_(dia_a_dia)"
    assert plano["tecnologias"]["ferramenta_bi"] == "4.g_ferramenta_de_bi_(dia_a_dia)"
    assert plano["ia"]["uso_ia_pessoal"] == "4.j_usa_chatgpt_ou_copilot_no_trabalho?"


def test_plano_marca_questao_ausente_como_nao_aplicavel():
    # A questao de linguagens usadas no dia a dia nao existe em 2025.
    config = m.carregar_config()
    plano = m.montar_plano_colunas(CABECALHOS_2025, config, 2025)
    assert "tecnologias.linguagem_uso" in plano["nao_aplicavel"]
    assert "tecnologias.linguagem_uso" not in plano["faltando"]


# --- Faixa salarial ---

def test_salario_faixa_fechada():
    assert m.salario_medio_da_faixa("de R$ 8.001/mês a R$ 12.000/mês") == 10000.5


def test_salario_faixa_aberta_inferior():
    assert m.salario_medio_da_faixa("Menos de R$ 1.000/mês") == 500.0


def test_salario_faixa_aberta_superior():
    assert m.salario_medio_da_faixa("Acima de R$ 40.001/mês") == 40001.0


def test_salario_faixa_malformada_da_edicao_2025():
    # Valor real presente na edicao 2025: limite superior menor que o inferior.
    # Nao pode virar 14000.5 (ponto medio), que subestimaria em mais de 40%.
    assert m.salario_medio_da_faixa("de R$ 25.001/mês a R$ 3000/mês") == 25001.0


def test_normalizar_texto_trata_nulos_de_pandas_e_spark():
    # Sem isso, um NaN convertido para string viraria a categoria "Outro" e
    # inflaria esse bucket: na edicao 2024 sao 1.399 respondentes sem nivel.
    for nulo in [None, float("nan"), "nan", "NaN", "<NA>", "None", "null", ""]:
        assert m.normalizar_texto(nulo) == "", f"falhou para {nulo!r}"


def test_padronizar_categorias_com_nulo_textual():
    for nulo in [None, float("nan"), "nan", "<NA>"]:
        assert m.padronizar_senioridade(nulo) == "Nao informado"
        assert m.padronizar_genero(nulo) == "Nao informado"
        assert m.padronizar_forma_trabalho(nulo) == "Nao informado"


def test_limites_da_faixa():
    assert m.limites_da_faixa("de R$ 8.001/mês a R$ 12.000/mês") == (8001.0, 12000.0)
    assert m.limites_da_faixa("Menos de R$ 1.000/mês") == (0.0, 1000.0)
    assert m.limites_da_faixa("Acima de R$ 40.001/mês") == (40001.0, None)
    # Faixa malformada da edicao 2025: tratada como aberta no topo.
    assert m.limites_da_faixa("de R$ 25.001/mês a R$ 3000/mês") == (25001.0, None)
    assert m.limites_da_faixa("Prefiro não informar") == (None, None)
    assert m.limites_da_faixa(None) == (None, None)


def test_mediana_interpolada_formula_classica():
    # N=40, alvo=20. Acumulado: 10, 30, 40 -> faixa mediana e (1000, 2000).
    # 1000 + ((20-10)/20) * 1000 = 1500
    bandas = [(0.0, 1000.0, 10), (1000.0, 2000.0, 20), (2000.0, 3000.0, 10)]
    assert m.mediana_interpolada(bandas) == 1500.0


def test_mediana_interpolada_ordena_bandas():
    bandas = [(2000.0, 3000.0, 10), (1000.0, 2000.0, 20), (0.0, 1000.0, 10)]
    assert m.mediana_interpolada(bandas) == 1500.0


def test_mediana_interpolada_distingue_grupos_que_a_mediana_simples_iguala():
    # Os dois grupos tem a mesma faixa mediana, mas distribuicoes diferentes.
    # A mediana do ponto medio daria 1500 para ambos; a interpolada diferencia.
    grupo_a = [(0.0, 1000.0, 40), (1000.0, 2000.0, 30), (2000.0, 3000.0, 20)]
    grupo_b = [(0.0, 1000.0, 20), (1000.0, 2000.0, 30), (2000.0, 3000.0, 40)]
    assert m.mediana_interpolada(grupo_a) != m.mediana_interpolada(grupo_b)


def test_mediana_interpolada_faixa_aberta_no_topo():
    # Se a mediana cai na faixa aberta, retorna o limite inferior.
    bandas = [(0.0, 1000.0, 5), (40001.0, None, 50)]
    assert m.mediana_interpolada(bandas) == 40001.0


def test_mediana_interpolada_sem_dados():
    assert m.mediana_interpolada([]) is None
    assert m.mediana_interpolada([(None, None, 0)]) is None


def test_salario_sem_informacao():
    assert m.salario_medio_da_faixa(None) is None
    assert m.salario_medio_da_faixa("") is None
    assert m.salario_medio_da_faixa("Prefiro não informar") is None


# --- Padronizacao de dominios ---

def test_padronizar_regiao_usa_a_coluna_da_pesquisa():
    mapa = m.carregar_config()["regiao_por_uf"]
    assert m.padronizar_regiao("Sudeste", "SP", mapa) == "Sudeste"


def test_padronizar_regiao_deriva_da_uf_quando_vazia():
    mapa = m.carregar_config()["regiao_por_uf"]
    assert m.padronizar_regiao("", "BA", mapa) == "Nordeste"
    assert m.padronizar_regiao(None, None, mapa) == "Nao informado"


def test_padronizar_senioridade():
    assert m.padronizar_senioridade("Júnior") == "Junior"
    assert m.padronizar_senioridade("Sênior") == "Senior"
    assert m.padronizar_senioridade("Pleno") == "Pleno"
    assert m.padronizar_senioridade("Gerente de dados") == "Gestao"
    assert m.padronizar_senioridade(None) == "Nao informado"


def test_padronizar_senioridade_nivel_novo_de_2025():
    # "Especialista/Staff+" foi criado na edicao 2025 e nao pode virar Senior.
    assert m.padronizar_senioridade("Especialista/Staff+") == "Especialista"


def test_senioridade_com_gestao_completa_gestores():
    # A pesquisa nao pergunta o nivel a quem e gestor: o campo vem vazio.
    assert m.senioridade_com_gestao("Nao informado", 1) == "Gestao"
    # Quem nao e gestor e nao informou o nivel continua sem informacao.
    assert m.senioridade_com_gestao("Nao informado", 0) == "Nao informado"
    assert m.senioridade_com_gestao("Nao informado", None) == "Nao informado"
    # Um nivel informado nunca e sobrescrito.
    assert m.senioridade_com_gestao("Senior", 1) == "Senior"


def test_padronizar_forma_trabalho_com_valores_reais():
    assert m.padronizar_forma_trabalho("Modelo 100% remoto") == "Remoto"
    assert m.padronizar_forma_trabalho("Modelo híbrido flexível (o funcionário tem liberdade)") == "Hibrido"
    assert m.padronizar_forma_trabalho("Modelo híbrido com dias fixos de trabalho presencial") == "Hibrido"
    assert m.padronizar_forma_trabalho("Modelo 100% presencial") == "Presencial"


def test_padronizar_genero():
    assert m.padronizar_genero("Masculino") == "Masculino"
    assert m.padronizar_genero("Feminino") == "Feminino"
    assert m.padronizar_genero("Prefiro não informar") == "Nao informado"


def test_resposta_binaria_cobre_os_tres_formatos_das_edicoes():
    # 2023 e 2025 gravam 0/1; 2024 grava TRUE/FALSE.
    assert m.resposta_binaria("1") == 1
    assert m.resposta_binaria("0") == 0
    assert m.resposta_binaria("TRUE") == 1
    assert m.resposta_binaria("FALSE") == 0
    assert m.resposta_binaria("") is None


# --- Uso de IA ---

FRASE_GRATUITA = "Utilizo apenas soluções gratuitas (como por exemplo o ChatGPT), para me ajudar a ser mais produtivo"
FRASE_PAGA = "Utilizo soluções pagas de AI Generativa (como por exemplo ChatGPT plus, MidJourney etc), para me ajudar"
FRASE_COPILOT = 'Utilizo soluções no estilo "Copilot" (exemplo: Github Copilot, Amazon CodeWhisperer ou Codeium)'
FRASE_NENHUMA = "Não utilizo nenhum tipo de solução de IA Generativa para melhorar a produtividade no dia a dia"


def test_usa_ia_reconhece_uso_apesar_da_virgula_no_texto():
    # Estas frases tem virgula fora de parenteses: nao podem ser quebradas.
    assert m.usa_ia(FRASE_GRATUITA) == 1
    assert m.usa_ia(FRASE_PAGA) == 1
    assert m.usa_ia(FRASE_COPILOT) == 1


def test_usa_ia_reconhece_nao_uso():
    assert m.usa_ia(FRASE_NENHUMA) == 0


def test_usa_ia_sem_resposta():
    assert m.usa_ia("") is None
    assert m.usa_ia(None) is None


def test_tipo_uso_ia_classifica_categorias():
    assert m.tipo_uso_ia(FRASE_NENHUMA) == "Nenhuma"
    assert m.tipo_uso_ia(FRASE_GRATUITA) == "Gratuita"
    assert m.tipo_uso_ia(FRASE_PAGA) == "Paga"
    assert m.tipo_uso_ia(FRASE_COPILOT) == "Assistente de codigo"


def test_tipo_uso_ia_multiplas_categorias():
    combinado = f"{FRASE_PAGA}, {FRASE_COPILOT}"
    resultado = m.tipo_uso_ia(combinado)
    assert "Paga" in resultado and "Assistente de codigo" in resultado


# --- Respostas de multipla escolha ---

def test_separar_multivalorado_respeita_parenteses():
    valor = "Azure (Microsoft), Amazon Web Services (AWS), Google Cloud (GCP)"
    assert m.separar_multivalorado(valor) == [
        "Azure (Microsoft)",
        "Amazon Web Services (AWS)",
        "Google Cloud (GCP)",
    ]


def test_separar_multivalorado_nao_quebra_em_barra():
    # Nomes reais de tecnologia contem barra e nao devem ser divididos.
    assert m.separar_multivalorado("SQL, Python, SAS/Stata") == ["SQL", "Python", "SAS/Stata"]
    assert m.separar_multivalorado("Servidores On Premise/Não utilizamos Cloud") == [
        "Servidores On Premise/Não utilizamos Cloud"
    ]
    assert m.separar_multivalorado("Salesforce/Einstein Analytics, Amazon QuickSight") == [
        "Salesforce/Einstein Analytics",
        "Amazon QuickSight",
    ]


def test_separar_multivalorado_vazio():
    assert m.separar_multivalorado(None) == []
    assert m.separar_multivalorado("nan") == []


if __name__ == "__main__":
    falhas = 0
    for nome, func in sorted(globals().items()):
        if nome.startswith("test_") and callable(func):
            try:
                func()
                print(f"OK    {nome}")
            except AssertionError as exc:
                falhas += 1
                print(f"FALHA {nome}: {exc!r}")
    print(f"\n{falhas} falha(s)")
    sys.exit(1 if falhas else 0)
