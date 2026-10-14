"""
ECOI2219 - Compiladores
Laboratorio 1 - Traducao Dirigida por Sintaxe com PLY

Integrantes:
    Aluno 1
    Aluno 2

Execucao: python lab1_tds.py exemplos/while.uc > mvpOutput.txt
Lexer:    python lab1_tds.py exemplos/expr.uc --tokens
"""

import argparse
import sys

import ply.lex as lex
import ply.yacc as yacc


# ============================================================
# ANALISADOR LEXICO
# ============================================================

reserved = {
    "if": "IF",
    "else": "ELSE",
    "while": "WHILE",
    "do": "DO",            # Desafio 4.1
    "read": "READ",        # Desafio 4.2
    "break": "BREAK",
    "print": "PRINT",
    "true": "TRUE",
    "false": "FALSE",
    "int": "INT",
    "float": "FLOAT",
}


tokens = [
    "ID",
    "NUM",
    "REAL",

    "EQ",
    "NE",
    "LE",
    "GE",

    "AND",
    "OR",
    "NOT",

    "LT",
    "GT",

    "ASSIGN",
] + list(reserved.values())


# Simbolos de um caractere tratados diretamente pelo PLY.
#
# Os operadores relacionais e de atribuicao foram mantidos como
# tokens nomeados porque o roteiro os apresenta explicitamente
# dessa forma.
literals = "{}();+-*/"


# ------------------------------------------------------------
# Operadores
# ------------------------------------------------------------

t_EQ = r"=="
t_NE = r"!="

t_LE = r"<="
t_GE = r">="

t_AND = r"&&"
t_OR = r"\|\|"

t_NOT = r"!"

t_LT = r"<"
t_GT = r">"

t_ASSIGN = r"="


# ------------------------------------------------------------
# Caracteres ignorados
# ------------------------------------------------------------

t_ignore = " \t\r"


# ------------------------------------------------------------
# Numeros reais
# ------------------------------------------------------------

def t_REAL(t):
    r"\d+\.\d+([eE][+-]?\d+)?|\d+[eE][+-]?\d+"

    t.value = float(t.value)

    return t



# ------------------------------------------------------------
# Numeros inteiros
# ------------------------------------------------------------

def t_NUM(t):
    r"\d+"

    t.value = int(t.value)

    return t


# ------------------------------------------------------------
# Identificadores e palavras reservadas
# ------------------------------------------------------------

def t_ID(t):
    r"[a-zA-Z_][a-zA-Z0-9_]*"

    # Caso o lexema seja palavra reservada, altera o tipo
    # do token. Caso contrario, permanece como ID.
    t.type = reserved.get(t.value, "ID")

    return t


# ------------------------------------------------------------
# Controle de linhas
# ------------------------------------------------------------

def t_newline(t):
    r"\n+"

    t.lexer.lineno += len(t.value)


# Comentarios usados nos exemplos e no compilador Java de referencia.
def t_COMMENT_LINE(t):
    r"//[^\n]*"
    pass


def t_COMMENT_BLOCK(t):
    r"/\*[\s\S]*?\*/"
    t.lexer.lineno += t.value.count("\n")


# ------------------------------------------------------------
# Erro lexico
# ------------------------------------------------------------

def t_error(t):

    print(
        (
            f"erro lexico na linha {t.lexer.lineno}: "
            f"caractere ilegal {t.value[0]!r}"
        ),
        file=sys.stderr,
    )

    # Descarta somente o caractere invalido e continua.
    t.lexer.skip(1)


# Constroi o analisador lexico.
lexer = lex.lex()


# ============================================================
# ESTADO DO GERADOR DE CODIGO
# ============================================================

# Codigo MEPA emitido durante as reducoes.
CODE = []

# Reservas ficam no prologo, pois uma declaracao num bloco dentro
# de while/if nao pode executar AMEM repetidamente por iteracao.
ALLOCATIONS = []


# Tabela de simbolos.
#
# Formato:
#
# SYMBOLS["a"] = 0
# SYMBOLS["x"] = 4
#
# O valor corresponde ao deslocamento da variavel.
# Mantido como tabela historica de nomes (compatibilidade com Passo 3).
SYMBOLS = {}

# A pilha de escopos determina quais nomes estao acessiveis.
SCOPES = []

# Pilhas de rotulos para as acoes semanticas intermediarias.
LABEL_COUNTER = 0
IF_PENDING = []
WHILE_PENDING = []
DO_PENDING = []
LOOP_EXITS = []


# Proximo endereco de memoria disponivel.
OFFSET = 0


# ============================================================
# FUNCOES AUXILIARES
# ============================================================

def emit(instruction):
    """Acrescenta uma instrucao gerada ao codigo MEPA."""
    CODE.append(instruction)


def new_label():
    """Retorna rotulo unico, independente do aninhamento do comando."""
    global LABEL_COUNTER
    LABEL_COUNTER += 1
    return f"L{LABEL_COUNTER}"


def mark_label(label):
    """MEPA oficial exige rotulo e instrucao na mesma linha."""
    emit(f"{label}: NADA")


def enter_scope():
    SCOPES.append({})


def leave_scope():
    SCOPES.pop()


def declare_symbol(name, width, line):
    """Registra uma variavel e reserva offset global, inclusive em blocos."""
    global OFFSET
    if name in SCOPES[-1]:
        semantic_error(f"linha {line}: variavel {name!r} ja declarada no bloco")
    SCOPES[-1][name] = OFFSET
    SYMBOLS[name] = OFFSET
    ALLOCATIONS.append(f"AMEM {width}\t; {name} address: {OFFSET}")
    OFFSET += width


def lookup_symbol(name, line):
    """Busca a declaracao visivel mais proxima (permite sombreamento)."""
    for scope in reversed(SCOPES):
        if name in scope:
            return scope[name]
    semantic_error(f"linha {line}: variavel {name!r} nao declarada ou fora do escopo")


def semantic_error(message):
    """
    Exibe um erro semantico e encerra a compilacao.
    """

    print(
        f"erro semantico: {message}",
        file=sys.stderr,
    )

    raise SystemExit(1)


# ============================================================
# ANALISADOR SINTATICO
# ============================================================

# O else pertence ao if mais proximo (dangling else).
precedence = (
    ("nonassoc", "IFX"),
    ("nonassoc", "ELSE"),
)
start = "program"


# ============================================================
# PROGRAMA E BLOCO PRINCIPAL
# ============================================================

def p_program(p):
    """program : block"""
    # PARA encerra a execucao; FIM encerra o arquivo MEPA 5.0.
    emit("PARA")
    emit("FIM")


def p_block(p):
    """block : '{' enter_scope decls stmts '}'"""
    leave_scope()


def p_enter_scope(p):
    """enter_scope :"""
    # Acao intermediaria: escopo disponivel antes das declaracoes.
    enter_scope()


# ============================================================
# LISTA DE DECLARACOES
# ============================================================

def p_decls_many(p):
    """
    decls : decls decl
    """

    pass


def p_decls_empty(p):
    """
    decls : empty
    """

    pass


# ============================================================
# DECLARACAO DE INTEIRO
# ============================================================

def p_decl_int(p):
    """decl : INT ID ';'"""
    # Esta e a mesma declaracao do Passo 3; so delegamos a reserva
    # para o prologo, evitando AMEM dinamico dentro de um while.
    declare_symbol(p[2], 4, p.lineno(2))


# ============================================================
# DECLARACAO DE FLOAT
# ============================================================

def p_decl_float(p):
    """decl : FLOAT ID ';'"""
    declare_symbol(p[2], 8, p.lineno(2))


# ============================================================
# LISTA DE COMANDOS
# ============================================================

def p_stmts_many(p):
    """
    stmts : stmts stmt
    """

    pass


def p_stmts_empty(p):
    """
    stmts : empty
    """

    pass


# ============================================================
# ATRIBUICAO
# ============================================================

def p_stmt_assign(p):
    """stmt : ID ASSIGN bool ';'"""
    address = lookup_symbol(p[1], p.lineno(1))
    emit(f"ARMZ 0,{address}\t; {p[1]}")


# ============================================================
# ESCRITA
# ============================================================

def p_stmt_print(p):
    """
    stmt : PRINT '(' bool ')' ';'
    """

    # A expressao ja deixou seu resultado no topo da pilha.
    emit("IMPR")


# ============================================================
# BOOL
# ============================================================

# A gramatica em niveis separa logicos, relacionais e aritmeticos.
# A avaliacao de && e || nao tem curto-circuito (ambos os operandos
# sao avaliados antes de CONJ/DISJ, como nas instrucoes MEPA).
def p_bool_or(p):
    """bool : bool OR bool_and"""
    emit("DISJ")


def p_bool_only(p):
    """bool : bool_and"""
    pass


def p_bool_and(p):
    """bool_and : bool_and AND bool_not"""
    emit("CONJ")


def p_bool_and_single(p):
    """bool_and : bool_not"""
    pass


def p_bool_not(p):
    """bool_not : NOT bool_not"""
    emit("NEGA")


def p_bool_relation(p):
    """bool_not : relation"""
    pass


def p_relation_cmp(p):
    """relation : expr relop expr"""
    instruction = {
        "EQ": "CMIG", "NE": "CMDG",
        "LT": "CMME", "GT": "CMMA",
        "LE": "CMEG", "GE": "CMAG",
    }[p[2]]
    emit(instruction)


def p_relation_expr(p):
    """relation : expr"""
    pass


def p_relop(p):
    """relop : EQ
             | NE
             | LT
             | GT
             | LE
             | GE"""
    p[0] = p.slice[1].type


# ============================================================
# EXPRESSOES
# ============================================================
#
# A gramatica em niveis implementa precedencia:
#
#     expr  -> term
#     term  -> unary
#     unary -> factor
#
# Portanto:
#
# * e / possuem precedencia maior que + e -.
#
# Isso evita a producao ambigua:
#
#     expr : expr '+' expr
#
# ============================================================


# ------------------------------------------------------------
# Soma
# ------------------------------------------------------------

def p_expr_plus(p):
    """
    expr : expr '+' term
    """

    # Os dois operandos ja estao na pilha quando esta
    # producao e reduzida.
    emit("SOMA")


# ------------------------------------------------------------
# Subtracao
# ------------------------------------------------------------

def p_expr_minus(p):
    """
    expr : expr '-' term
    """

    emit("SUBT")


# ------------------------------------------------------------
# expr -> term
# ------------------------------------------------------------

def p_expr_term(p):
    """
    expr : term
    """

    pass


# ------------------------------------------------------------
# Multiplicacao
# ------------------------------------------------------------

def p_term_times(p):
    """
    term : term '*' unary
    """

    emit("MULT")


# ------------------------------------------------------------
# Divisao
# ------------------------------------------------------------

def p_term_divide(p):
    """
    term : term '/' unary
    """

    emit("DIVI")


# ------------------------------------------------------------
# term -> unary
# ------------------------------------------------------------

def p_term_unary(p):
    """
    term : unary
    """

    pass


# ------------------------------------------------------------
# unary -> factor
# ------------------------------------------------------------

def p_unary_factor(p):
    """unary : factor"""
    pass


def p_unary_minus(p):
    """unary : '-' unary"""
    emit("INVR")


def p_unary_plus(p):
    """unary : '+' unary"""
    pass


# ============================================================
# FATORES
# ============================================================

# ------------------------------------------------------------
# Constante inteira
# ------------------------------------------------------------

def p_factor_num(p):
    """
    factor : NUM
    """

    emit(
        f"CRCT {p[1]}"
    )


# ------------------------------------------------------------
# Constante real
# ------------------------------------------------------------

def p_factor_real(p):
    """
    factor : REAL
    """

    # O roteiro exige o reconhecimento de REAL pelo lexer.
    # A constante e emitida seguindo a mesma estrutura
    # CRCT utilizada para constantes literais.
    emit(
        f"CRCT {p[1]}"
    )


# ------------------------------------------------------------
# Variavel
# ------------------------------------------------------------

def p_factor_id(p):
    """factor : ID"""
    address = lookup_symbol(p[1], p.lineno(1))
    emit(f"CRVL 0,{address}\t; {p[1]}")


def p_factor_boolean_literal(p):
    """factor : TRUE
              | FALSE"""
    emit("CRCT 1" if p.slice[1].type == "TRUE" else "CRCT 0")


# ------------------------------------------------------------
# Parenteses
# ------------------------------------------------------------

def p_factor_group(p):
    """factor : '(' bool ')'"""
    # Tambem cobre parenteses em condicoes: (a>0 || b<2).
    pass


# ============================================================
# PASSO 4: CONDICIONAIS (ACOES INTERMEDIARIAS PLY)
# ============================================================

def p_if_head(p):
    """if_head : IF '(' bool ')'"""
    # Reduz apos a condicao, mas ANTES do corpo: DSVF deve vir aqui.
    false_label, end_label = new_label(), new_label()
    emit(f"DSVF {false_label}")
    IF_PENDING.append((false_label, end_label))


def p_stmt_if(p):
    """stmt : if_head stmt %prec IFX"""
    false_label, _ = IF_PENDING.pop()
    mark_label(false_label)


def p_else_mark(p):
    """else_mark :"""
    # O desvio e a marca precisam vir ENTRE os dois ramos.
    false_label, end_label = IF_PENDING[-1]
    emit(f"DSVS {end_label}")
    mark_label(false_label)


def p_stmt_if_else(p):
    """stmt : if_head stmt ELSE else_mark stmt"""
    _, end_label = IF_PENDING.pop()
    mark_label(end_label)


# ============================================================
# PASSO 5: WHILE E BREAK
# ============================================================

def p_while_start(p):
    """while_start :"""
    start_label, exit_label = new_label(), new_label()
    mark_label(start_label)
    WHILE_PENDING.append((start_label, exit_label))
    LOOP_EXITS.append(exit_label)


def p_while_head(p):
    """while_head : WHILE '(' while_start bool ')'"""
    _, exit_label = WHILE_PENDING[-1]
    emit(f"DSVF {exit_label}")


def p_stmt_while(p):
    """stmt : while_head stmt"""
    start_label, exit_label = WHILE_PENDING.pop()
    LOOP_EXITS.pop()
    emit(f"DSVS {start_label}")
    mark_label(exit_label)


def p_stmt_break(p):
    """stmt : BREAK ';'"""
    if not LOOP_EXITS:
        semantic_error(f"linha {p.lineno(1)}: break fora de um laco")
    emit(f"DSVS {LOOP_EXITS[-1]}\t; break")


# ============================================================
# DESAFIOS 4.1 E 4.2: DO-WHILE, READ E BLOCOS ANINHADOS
# ============================================================

def p_do_head(p):
    """do_head : DO"""
    start_label, exit_label = new_label(), new_label()
    mark_label(start_label)
    DO_PENDING.append((start_label, exit_label))
    LOOP_EXITS.append(exit_label)


def p_stmt_do(p):
    """stmt : do_head stmt WHILE '(' bool ')' ';'"""
    start_label, exit_label = DO_PENDING.pop()
    LOOP_EXITS.pop()
    emit(f"DSVF {exit_label}")
    emit(f"DSVS {start_label}")
    mark_label(exit_label)


def p_stmt_read(p):
    """stmt : READ '(' ID ')' ';'"""
    address = lookup_symbol(p[3], p.lineno(3))
    emit("LEIT")
    emit(f"ARMZ 0,{address}\t; {p[3]}")


def p_stmt_block(p):
    """stmt : block"""
    pass


def p_stmt_empty(p):
    """stmt : ';'"""
    pass


# ============================================================
# PRODUCAO VAZIA
# ============================================================

def p_empty(p):
    """
    empty :
    """

    pass


# ============================================================
# ERRO SINTATICO
# ============================================================

def p_error(p):

    if p is None:

        print(
            "erro sintatico: fim inesperado do arquivo",
            file=sys.stderr,
        )

    else:

        print(
            (
                f"erro sintatico na linha {p.lineno}: "
                f"token {p.type}, valor {p.value!r}"
            ),
            file=sys.stderr,
        )

    raise SystemExit(1)


# Constroi o parser LALR.
parser = yacc.yacc(
    debug=False,
    write_tables=False,
)


# ============================================================
# COMPILACAO
# ============================================================

def compile_source(source):
    """Compila para lista de instrucoes, preservando API do arquivo original."""
    global CODE, ALLOCATIONS, SYMBOLS, SCOPES, OFFSET
    global LABEL_COUNTER, IF_PENDING, WHILE_PENDING, DO_PENDING, LOOP_EXITS

    CODE = ["INPP"]
    ALLOCATIONS = []
    SYMBOLS = {}
    SCOPES = []
    OFFSET = 0
    LABEL_COUNTER = 0
    IF_PENDING = []
    WHILE_PENDING = []
    DO_PENDING = []
    LOOP_EXITS = []
    lexer.lineno = 1

    parser.parse(source, lexer=lexer, tracking=True)

    # A montagem do prologo ordena reservas e codigo, sem reprocessar
    # expressoes: toda instrucao de expressao foi emitida nas reducoes.
    return CODE[:1] + ALLOCATIONS + CODE[1:]


# ============================================================
# MODO DE TESTE DO LEXER
# ============================================================

def show_tokens(source):
    """
    Exibe todos os tokens reconhecidos pelo lexer.
    """

    lexer.lineno = 1
    lexer.input(source)

    for tok in lexer:

        print(
            f"{tok.lineno:3} "
            f"{tok.type:10} "
            f"{tok.value!r}"
        )


# ============================================================
# LEITURA DO ARQUIVO
# ============================================================

def read_source(filename):

    try:

        with open(
            filename,
            "r",
            encoding="utf-8",
        ) as file:

            return file.read()

    except OSError as error:

        print(
            f"erro ao abrir {filename!r}: {error}",
            file=sys.stderr,
        )

        raise SystemExit(1)



# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    argument_parser = argparse.ArgumentParser(
        description=(
            "Compilador completo do laboratorio de uC para MEPA, "
            "baseado no arquivo da equipe."
        )
    )

    argument_parser.add_argument(
        "source",
        help="arquivo .uc que sera processado",
    )

    argument_parser.add_argument(
        "--tokens",
        action="store_true",
        help=(
            "executa apenas o analisador lexico "
            "e exibe os tokens"
        ),
    )

    argument_parser.add_argument(
        "-o", "--output", help="salva as instrucoes em arquivo (opcional)"
    )

    args = argument_parser.parse_args()

    source = read_source(
        args.source
    )

    # --------------------------------------------------------
    # Modo lexer
    # --------------------------------------------------------

    if args.tokens:

        show_tokens(source)

        return

    # --------------------------------------------------------
    # Compilacao
    # --------------------------------------------------------

    generated_code = compile_source(
        source
    )

    # Somente as instrucoes sao enviadas para stdout
    if args.output:
        from pathlib import Path
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(generated_code) + "\n", encoding="utf-8")
    else:
        for instruction in generated_code:
            print(instruction)


if __name__ == "__main__":
    main()