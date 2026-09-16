"""Nucleo de regras de negocio do pipeline State of Data Brasil.

Modulo em Python puro (sem pandas/pyspark) para poder ser reaproveitado tanto
pelos Glue Jobs em PySpark quanto pelo pipeline local em pandas.

As 3 edicoes usam formatos de cabecalho diferentes:
    2023        "('P2_h ', 'Faixa salarial')"   (tupla)
    2024/2025   "2.h_faixa_salarial"            (texto plano)
Os dois sao normalizados para um codigo pontilhado (P2_h -> 2.h), que e a chave
usada em config/mapeamento_colunas.json.
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

CAMINHO_CONFIG_PADRAO = Path(__file__).resolve().parents[2] / "config" / "mapeamento_colunas.json"

GRUPOS = ("campos", "binarios", "tecnologias", "ia")

_RE_CABECALHO_TUPLA = re.compile(
    r"""^\(\s*(['"])(?P<codigo>.*?)\1\s*,\s*(['"])(?P<rotulo>.*)\3\s*\)$""",
    re.DOTALL,
)
# Formato 2024/2025: codigo pontilhado seguido de "_" ou espaco. Ex: "1.i.1_uf_onde_mora".
_RE_CABECALHO_PLANO = re.compile(r"^(?P<codigo>\d+(?:\.[0-9a-zA-Z]+)*)[_ ](?P<rotulo>.*)$", re.DOTALL)


def carregar_config(caminho: str | Path | None = None) -> dict:
    caminho = Path(caminho) if caminho else CAMINHO_CONFIG_PADRAO
    return json.loads(caminho.read_text(encoding="utf-8"))


#Representacoes textuais de ausencia produzidas por pandas/Spark ao converter
# nulos para string. Sem esse tratamento, um NaN vira a string "nan" e passa a
# ser classificado como categoria valida ("Outro"), inflando esse bucket.
_NULOS_TEXTUAIS = {"nan", "none", "null", "<na>", "nat", "na", "-", "--"}


def normalizar_texto(valor: object | None) -> str:
    """Minusculas, sem acentos e sem espacos duplicados. Usado para comparacoes.

    Retorna string vazia para qualquer forma de ausencia: None, float('nan') e
    os sentinelas de nulo do pandas (pd.NA, pd.NaT), que sao capturados pela sua
    representacao textual. A comparacao "valor != valor" nao pode ser usada aqui
    porque pd.NA a propaga e levanta TypeError ao ser avaliada como booleano.
    """
    if valor is None:
        return ""
    if isinstance(valor, float) and valor != valor:
        return ""
    sem_acento = unicodedata.normalize("NFKD", str(valor))
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", sem_acento).strip().lower()
    return "" if texto in _NULOS_TEXTUAIS else texto


def normalizar_codigo(codigo: str | None) -> str:
    """Converte o codigo da questao para a forma pontilhada canonica.

    "P2_h" -> "2.h" | "P1_i_1" -> "1.i.1" | "2.h" -> "2.h" | "1.i.1" -> "1.i.1"
    """
    if not codigo:
        return ""
    texto = normalizar_texto(codigo).replace(" ", "")
    texto = re.sub(r"^p(?=\d)", "", texto)
    texto = texto.replace("_", ".")
    return re.sub(r"\.+", ".", texto).strip(".")


@dataclass(frozen=True)
class ColunaOrigem:
    """Uma coluna do CSV bruto, com o cabecalho ja decomposto."""

    original: str
    codigo: str
    rotulo: str

    @property
    def codigo_normalizado(self) -> str:
        return normalizar_codigo(self.codigo)

    @property
    def rotulo_normalizado(self) -> str:
        return normalizar_texto(self.rotulo)


def parse_cabecalho(cabecalho: str) -> ColunaOrigem:
    """Decompoe o cabecalho em codigo de questao e rotulo, nos dois formatos."""
    bruto = (cabecalho or "").strip()

    m = _RE_CABECALHO_TUPLA.match(bruto)
    if m:
        return ColunaOrigem(cabecalho, m.group("codigo").strip(), m.group("rotulo").strip())

    m = _RE_CABECALHO_PLANO.match(bruto)
    if m:
        return ColunaOrigem(cabecalho, m.group("codigo").strip(), m.group("rotulo").strip())

    return ColunaOrigem(cabecalho, "", bruto)


def indexar_por_codigo(cabecalhos: list[str]) -> dict[str, str]:
    """Mapeia codigo normalizado -> cabecalho original.

    Em caso de codigo repetido, a primeira ocorrencia vence: nos CSVs da pesquisa
    a coluna principal da questao aparece antes das colunas dummy derivadas.
    """
    indice: dict[str, str] = {}
    for cabecalho in cabecalhos:
        codigo = parse_cabecalho(cabecalho).codigo_normalizado
        if codigo and codigo not in indice:
            indice[codigo] = cabecalho
    return indice


def resolver_coluna(cabecalhos: list[str], codigo: str | None) -> str | None:
    """Encontra a coluna cujo codigo de questao corresponde exatamente ao informado.

    A comparacao e exata (e nao por prefixo) para nao confundir a questao "4.h"
    com as colunas dummy "4.h.3", "4.h.7" etc.
    """
    if not codigo:
        return None
    return indexar_por_codigo(cabecalhos).get(normalizar_codigo(codigo))


def montar_plano_colunas(cabecalhos: list[str], config: dict, ano: int | str) -> dict:
    """Resolve todos os campos canonicos de uma edicao da pesquisa.

    Retorna o que resolveu e o que ficou faltando, para ser logado pelo job e
    revisado antes de confiar no resultado.
    """
    ano = str(ano)
    plano: dict = {grupo: {} for grupo in GRUPOS}
    plano["faltando"] = []
    plano["nao_aplicavel"] = []

    for grupo in GRUPOS:
        for nome, regra in config.get(grupo, {}).items():
            codigo = (regra.get("codigos") or {}).get(ano)
            if codigo is None:
                # Questao inexistente nesta edicao: ausencia esperada, nao erro.
                plano["nao_aplicavel"].append(f"{grupo}.{nome}")
                continue

            escolhida = resolver_coluna(cabecalhos, codigo)
            if escolhida is None:
                plano["faltando"].append(f"{grupo}.{nome}")
                continue
            plano[grupo][nome] = escolhida

    return plano


# --- Faixa salarial ---

_RE_NUMERO_MONETARIO = re.compile(r"(\d[\d\.\s]*)")


def _numeros_da_faixa(texto: str) -> list[float]:
    valores: list[float] = []
    for bruto in _RE_NUMERO_MONETARIO.findall(texto.replace(",", ".")):
        limpo = re.sub(r"[^\d]", "", bruto)
        if limpo:
            valores.append(float(limpo))
    return valores


def limites_da_faixa(faixa: str | None) -> tuple[float | None, float | None]:
    """Extrai os limites inferior e superior da faixa salarial.

    O limite superior e None quando a faixa e aberta no topo ("Acima de
    R$ 40.001/mes"), o que sinaliza para a mediana interpolada que aquela faixa
    nao pode ser interpolada.

    Retorna (None, None) quando nao ha informacao de renda utilizavel.
    """
    if faixa is None:
        return (None, None)

    texto = normalizar_texto(faixa)
    if not texto:
        return (None, None)
    if "nao" in texto and ("informar" in texto or "receb" in texto or "aplica" in texto):
        return (None, None)

    numeros = _numeros_da_faixa(texto)
    if not numeros:
        return (None, None)

    if len(numeros) >= 2:
        inferior, superior = numeros[0], numeros[1]
        # Faixa malformada da edicao 2025 ("de R$ 25.001/mes a R$ 3000/mes"):
        # trata como aberta no topo, preservando o limite inferior confiavel.
        if superior < inferior:
            return (inferior, None)
        return (inferior, superior)
    if texto.startswith("menos de") or texto.startswith("ate") or "abaixo" in texto:
        return (0.0, numeros[0])
    return (numeros[0], None)


def mediana_interpolada(bandas: list[tuple[float, float | None, int]]) -> float | None:
    """Mediana de dados agrupados em faixas, por interpolacao linear.

    A pesquisa coleta renda em faixas, nao em valor exato. A mediana dos pontos
    medios e cega: ela retorna sempre o centro da faixa mediana, o que na pratica
    faz grupos diferentes (por exemplo, todas as regioes) exibirem exatamente o
    mesmo valor. Este e o estimador classico para dados agrupados:

        mediana = L + ((N/2 - F) / f) * w

    onde L e o limite inferior da faixa mediana, N o total de observacoes, F a
    frequencia acumulada antes da faixa, f a frequencia da faixa e w sua
    amplitude.

    Espera uma lista de (limite_inferior, limite_superior, contagem). Faixas com
    limite superior None (abertas no topo) nao sao interpoladas: nesse caso
    retorna o proprio limite inferior, escolha conservadora.
    """
    validas = [(inf, sup, n) for inf, sup, n in bandas if inf is not None and n > 0]
    if not validas:
        return None

    validas.sort(key=lambda b: b[0])
    total = sum(n for _, _, n in validas)
    alvo = total / 2

    acumulado = 0
    for inferior, superior, n in validas:
        if acumulado + n >= alvo:
            if superior is None or superior <= inferior:
                return float(inferior)
            return float(inferior) + ((alvo - acumulado) / n) * (float(superior) - float(inferior))
        acumulado += n

    return float(validas[-1][0])


def salario_medio_da_faixa(faixa: str | None) -> float | None:
    """Converte a faixa salarial textual em um valor numerico mensal estimado.

    Regras, documentadas na apresentacao:
      - faixa fechada ("de R$ 8.001/mes a R$ 12.000/mes") -> ponto medio;
      - faixa aberta inferior ("Menos de R$ 1.000/mes")   -> metade do limite;
      - faixa aberta superior ("Acima de R$ 40.001/mes")  -> o proprio limite,
        para nao inflar artificialmente medias e medianas;
      - faixa malformada, com limite superior menor que o inferior (existe na
        edicao 2025: "de R$ 25.001/mes a R$ 3000/mes") -> usa o limite inferior,
        que e a informacao confiavel da resposta.
    Retorna None quando nao ha informacao de renda utilizavel.
    """
    if faixa is None:
        return None

    texto = normalizar_texto(faixa)
    if not texto:
        return None
    if "nao" in texto and ("informar" in texto or "receb" in texto or "aplica" in texto):
        return None

    numeros = _numeros_da_faixa(texto)
    if not numeros:
        return None

    if len(numeros) >= 2:
        inferior, superior = numeros[0], numeros[1]
        if superior < inferior:
            return inferior
        return (inferior + superior) / 2
    if texto.startswith("menos de") or texto.startswith("ate") or "abaixo" in texto:
        return numeros[0] / 2
    return numeros[0]


# --- Padronizacao de dominios ---

def regiao_da_uf(uf: object | None, mapa_regioes: dict) -> str:
    chave = normalizar_texto(uf).upper()
    if not chave:
        return "Nao informado"
    return mapa_regioes.get(chave, "Nao informado")


def padronizar_regiao(regiao: object | None, uf: object | None, mapa_regioes: dict) -> str:
    """Usa a regiao informada pela pesquisa; se vazia, deriva da UF."""
    if normalizar_texto(regiao):
        return str(regiao).strip()
    return regiao_da_uf(uf, mapa_regioes)


# A ordem importa: "especialista" e verificado antes de "senior" porque o nivel
# "Especialista/Staff+", criado na edicao 2025, nao deve ser fundido com Senior.
_MAPA_SENIORIDADE = (
    ("junior", "Junior"),
    ("jr", "Junior"),
    ("pleno", "Pleno"),
    ("especialista", "Especialista"),
    ("staff", "Especialista"),
    ("senior", "Senior"),
    ("sr", "Senior"),
)

_TERMOS_GESTAO = ("coordenador", "gerente", "head", "diretor", "manager", "lideran")


def padronizar_senioridade(valor: object | None) -> str:
    texto = normalizar_texto(valor)
    if not texto:
        return "Nao informado"
    for chave, padrao in _MAPA_SENIORIDADE:
        if chave in texto:
            return padrao
    if any(t in texto for t in _TERMOS_GESTAO):
        return "Gestao"
    return "Outro"


def senioridade_com_gestao(senioridade: str | None, atua_como_gestor: object | None) -> str:
    """Completa a senioridade dos gestores.

    A pesquisa nao pergunta o nivel (junior/pleno/senior) a quem atua como
    gestor: essas pessoas respondem a questao de cargo de gestao, e o campo de
    nivel fica vazio por desenho do questionario. Sem este tratamento, 2.668
    gestores das 3 edicoes cairiam em "Nao informado", que se tornaria o segundo
    maior grupo e distorceria qualquer analise por senioridade.
    """
    atual = normalizar_texto(senioridade)
    if atual and atual != "nao informado":
        return str(senioridade).strip()
    # resposta_binaria absorve as variacoes de encoding (0/1, TRUE/FALSE) e os
    # nulos do pandas, cuja comparacao direta com 1 levantaria TypeError.
    if resposta_binaria(atua_como_gestor) == 1:
        return "Gestao"
    return "Nao informado"


def padronizar_forma_trabalho(valor: str | None) -> str:
    texto = normalizar_texto(valor)
    if not texto:
        return "Nao informado"
    if "hibrido" in texto:
        return "Hibrido"
    if "remoto" in texto or "home office" in texto:
        return "Remoto"
    if "presencial" in texto:
        return "Presencial"
    return "Outro"


def padronizar_genero(valor: str | None) -> str:
    texto = normalizar_texto(valor)
    if not texto:
        return "Nao informado"
    if texto.startswith("masculino") or texto == "homem":
        return "Masculino"
    if texto.startswith("feminino") or texto == "mulher":
        return "Feminino"
    if "prefiro nao informar" in texto:
        return "Nao informado"
    return "Outro"


def resposta_binaria(valor: str | None) -> int | None:
    """Converte respostas booleanas em 1/0.

    A pesquisa grava esses campos de forma inconsistente entre edicoes: 0/1 em
    2023 e 2025, TRUE/FALSE em 2024.
    """
    texto = normalizar_texto(valor)
    if not texto:
        return None
    if texto.startswith("sim") or texto in {"1", "1.0", "true", "verdadeiro"}:
        return 1
    if texto.startswith("nao") or texto in {"0", "0.0", "false", "falso"}:
        return 0
    return None


# --- Uso de IA generativa ---

def usa_ia(valor: str | None) -> int | None:
    """Indica se o respondente usa alguma solucao de IA generativa no trabalho.

    A questao e de multipla escolha, mas o texto de cada alternativa contem
    virgulas fora de parenteses (ex: "Utilizo apenas solucoes gratuitas (como
    por exemplo o ChatGPT), para me ajudar a ser mais produtivo"), o que impede
    a quebra por virgula. A classificacao e feita por presenca de trecho.
    """
    texto = normalizar_texto(valor)
    if not texto:
        return None
    if "nao utilizo nenhum tipo" in texto:
        return 0
    if "utilizo" in texto:
        return 1
    return None


def tipo_uso_ia(valor: str | None) -> str | None:
    """Classifica o tipo de uso de IA declarado, em categorias nao exclusivas.

    Retorna as categorias encontradas separadas por "|", ou None se a questao
    nao foi respondida. Um respondente pode declarar mais de um tipo de uso.
    """
    texto = normalizar_texto(valor)
    if not texto:
        return None
    if "nao utilizo nenhum tipo" in texto:
        return "Nenhuma"

    categorias = []
    if "solucoes pagas" in texto:
        categorias.append("Paga")
    if "apenas solucoes gratuitas" in texto or "solucoes gratuitas" in texto:
        categorias.append("Gratuita")
    if "copilot" in texto or "ai para codigo" in texto or "cursor" in texto:
        categorias.append("Assistente de codigo")

    return "|".join(categorias) if categorias else None


# --- Respostas de multipla escolha ---

def separar_multivalorado(valor: str | None) -> list[str]:
    """Quebra respostas de multipla escolha em itens individuais.

    A quebra ocorre SOMENTE por virgula fora de parenteses. Barra e ponto e
    virgula nao sao separadores: varios nomes de tecnologia os contem, como
    "SAS/Stata", "Salesforce/Einstein Analytics" e "Servidores On Premise/Nao
    utilizamos Cloud". Parenteses sao respeitados por causa de itens como
    "Amazon Web Services (AWS)" e "Google Cloud (GCP)".
    """
    if not normalizar_texto(valor):
        return []
    texto = str(valor).strip()

    itens: list[str] = []
    profundidade = 0
    atual = ""
    for char in texto:
        if char in "([":
            profundidade += 1
        elif char in ")]":
            profundidade = max(0, profundidade - 1)

        if char == "," and profundidade == 0:
            itens.append(atual)
            atual = ""
        else:
            atual += char
    itens.append(atual)

    return [item.strip() for item in itens if item.strip()]


def to_snake_case(valor: str) -> str:
    base = normalizar_texto(valor)
    base = re.sub(r"[^a-z0-9]+", "_", base)
    return re.sub(r"_+", "_", base).strip("_")
