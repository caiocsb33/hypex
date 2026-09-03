from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from core.database import Database
import json
from models.estoque import Estoque
from models.galpao import Galpao
from models.produto import Produto
from models.movimentacao import Movimentacao
from models.pedidocliente import PedidoCliente
from models.fornecedor import Fornecedor
from models.cliente import Cliente
from models.funcionario import Funcionario
from models.endereco import Endereco
from models.empilhadeira import Empilhadeira
import re
import secrets
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# Em produção defina FLASK_SECRET_KEY no ambiente. O valor gerado a cada
# inicialização serve só para desenvolvimento (derruba as sessões ao reiniciar).
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

@app.context_processor
def dados_globais():
    empresa_nome = ""
    empresa_imagem = None

    if "empresa_id" in session:
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT nome, imagem
                FROM empresa
                WHERE id = %s
            """, (session["empresa_id"],))

            empresa = cursor.fetchone()

            if empresa:
                empresa_nome = empresa["nome"]
                empresa_imagem = empresa["imagem"]

        finally:
            cursor.close()
            conexao.close()

    return {
        "empresa_nome": empresa_nome,
        # Foto que aparece no topo do menu lateral
        "empresa_imagem": empresa_imagem,
        # Preferências de interface guardadas na sessão. Antes ficavam no
        # localStorage e eram aplicadas por JavaScript depois que a página
        # carregava; agora chegam prontas no HTML.
        "tema": session.get("tema", "claro"),
        "sidebar_minimizada": session.get("sidebar_minimizada", False),
        # Usada como valor padrão nos campos de data dos formulários
        "hoje": datetime.now().strftime("%Y-%m-%d"),
        # Módulo atual, para o menu destacar o item certo
        "modulo_atual": modulo_do_endpoint(request.endpoint),
    }


# Cada item do menu cobre várias telas. Antes o destaque comparava o caminho
# exato ("/galpao"), então ao entrar em /estoque, /info_produto/1 ou
# /pedidos_cliente/1 nenhum item aparecia selecionado.
MODULOS = {
    "dashboard": {"dashboard"},

    "estoque": {
        "galpao", "novo_galpao", "salvar_galpao", "info_galpao",
        "atualizar_galpao", "deletar_galpao", "estoque", "estoque_galpao",
        "movimentar_estoque", "produtos", "produtos_inativos",
        "salvar_produto", "editar_produto", "atualizar_produto",
        "info_produtos", "desativar_produto", "reativar_produto",
        "excluir_produto", "ajustar_estoque_produto",
        "movimentacoes", "nova_movimentacao", "salvar_movimentacao",
        "salvar_empilhadeira", "atualizar_empilhadeira", "deletar_empilhadeira",
        "salvar_funcionario", "atualizar_funcionario", "deletar_funcionario",
    },

    "fornecedores": {
        "fornecedores", "novo_fornecedor", "salvar_fornecedor",
        "atualizar_fornecedor", "deletar_fornecedor", "info_fornecedor",
        "itens_fornecedor", "salvar_item_fornecedor",
        "vincular_fornecedor_produto",
    },

    "pedidos": {
        "pedidos", "listar_pedidos_entrada", "cadastro_pedido_entrada",
        "novo_pedido_entrada", "salvar_pedido_entrada",
        "visualizar_pedido_entrada", "editar_pedido", "deletar_pedido",
        "adicionar_item_entrada", "remover_item_entrada",
        "limpar_pedido_entrada",
    },

    "clientes": {
        "cliente", "novo_cliente", "salvar_cliente", "info_cliente",
        "atualizar_cliente", "deletar_cliente", "pedidos_clientes",
        "info_pedido_cliente", "cadastro_pedido", "cadastro_pedido_saida",
        "listar_pedidos_saida", "salvar_pedido_saida",
        "visualizar_pedido_saida", "deletar_pedido_saida",
        "adicionar_item_saida", "remover_item_saida", "limpar_pedido_saida",
    },
}


def modulo_do_endpoint(endpoint):
    for modulo, rotas in MODULOS.items():
        if endpoint in rotas:
            return modulo
    return None

# ---------------- PREFERÊNCIAS DE INTERFACE ---------------- #

def voltar_para(padrao="dashboard"):
    """Devolve o usuário para a página em que ele estava.

    O destino vem de um campo escondido do formulário. Só caminhos internos
    são aceitos: "//" e "http://" seriam redirecionamentos para fora do site.
    """
    destino = (request.form.get("voltar_para") or "").strip()

    if destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)

    return redirect(url_for(padrao))


@app.route("/tema/alternar", methods=["POST"])
def alternar_tema():
    session["tema"] = "claro" if session.get("tema") == "escuro" else "escuro"
    return voltar_para()


@app.route("/menu/alternar", methods=["POST"])
def alternar_menu():
    session["sidebar_minimizada"] = not session.get("sidebar_minimizada", False)
    return voltar_para()

# ---------------- FUNÇÕES AUXILIARES ---------------- #

def to_int(value, default=0):
    try:
        return int(value)
    except:
        return default

def to_float(value, default=0.0):
    try:
        return float(value)
    except:
        return default

# ------------VALIDAÇÕES----------#

def telefone_valido(telefone):
    numeros = re.sub(r'\D', '', telefone)
    return len(numeros) in (10, 11)

def formatar_telefone(telefone):
    numeros = re.sub(r'\D', '', telefone)

    if len(numeros) == 11:
        return f"({numeros[:2]}) {numeros[2:7]}-{numeros[7:]}"

    if len(numeros) == 10:
        return f"({numeros[:2]}) {numeros[2:6]}-{numeros[6:]}"

    return telefone

def area_valida(area):
    try:
        valor = float(area)
        return valor > 0
    except (ValueError, TypeError):
        return False

def nome_valido(nome):
    return nome.replace(" ", "").isalpha()

def email_valido(email):
    padrao = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return re.match(padrao, email) is not None

# ------------ VERIFICAÇÃO DO BANCO ----------#

# Estruturas criadas depois da primeira versão do banco.sql. Se o banco foi
# criado por uma versão anterior e a migração não foi aplicada, várias telas
# quebram com "Internal Server Error" sem explicar o motivo. A verificação
# abaixo troca esse erro por uma instrução clara.
ESTRUTURAS_NECESSARIAS = [
    ("coluna", "empilhadeira", "funcionario_id"),
    ("coluna", "produto", "imagem"),
    ("coluna", "fornecedor", "imagem"),
    ("coluna", "galpao", "imagem"),
    ("coluna", "empresa", "imagem"),
    ("tabela", "recuperacao_senha", None),
]

# Resultado guardado após a primeira checagem, para não consultar a cada request
_estruturas_faltando = None


def verificar_banco(forcar=False):
    """Devolve a lista de estruturas que faltam no banco."""
    global _estruturas_faltando

    if _estruturas_faltando is not None and not forcar:
        return _estruturas_faltando

    faltando = []

    try:
        conexao = Database.connect()
        cursor = conexao.cursor()

        try:
            for tipo, tabela, coluna in ESTRUTURAS_NECESSARIAS:
                if tipo == "tabela":
                    cursor.execute("SHOW TABLES LIKE %s", (tabela,))
                    if not cursor.fetchone():
                        faltando.append(f"tabela {tabela}")
                else:
                    cursor.execute(f"SHOW COLUMNS FROM {tabela} LIKE %s", (coluna,))
                    if not cursor.fetchone():
                        faltando.append(f"coluna {tabela}.{coluna}")

        finally:
            cursor.close()
            conexao.close()

    except Exception:
        # Banco fora do ar é outro problema; não é o caso de acusar migração
        return []

    _estruturas_faltando = faltando
    return faltando


@app.before_request
def avisar_banco_desatualizado():
    """Mostra o que fazer em vez de deixar a tela estourar com erro 500."""
    if request.endpoint in ("static", "banco_desatualizado"):
        return None

    if verificar_banco():
        return redirect(url_for("banco_desatualizado"))

    return None


@app.route("/banco-desatualizado")
def banco_desatualizado():
    faltando = verificar_banco()

    if not faltando:
        return redirect(url_for("landing"))

    return render_template("banco_desatualizado.html", faltando=faltando), 503


# ------------ IMAGENS ----------#

EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "webp", "gif"}

# Limite de tamanho do arquivo enviado
TAMANHO_MAXIMO_IMAGEM = 5 * 1024 * 1024  # 5 MB

PASTA_IMAGENS = os.path.join("static", "imagem")


def salvar_imagem(arquivo, prefixo, identificador):
    """Grava a imagem enviada e devolve o nome do arquivo.

    Devolve None quando nada foi enviado, e levanta ValueError quando o
    arquivo não serve. O nome inclui o tipo e o id (ex.: fornecedor_3.png),
    então trocar a imagem sobrescreve a anterior em vez de acumular lixo.
    """
    if not arquivo or not arquivo.filename:
        return None

    extensao = (arquivo.filename.rsplit(".", 1)[-1].lower()
                if "." in arquivo.filename else "")

    if extensao not in EXTENSOES_IMAGEM:
        raise ValueError(
            "Formato de imagem inválido. Use PNG, JPG, JPEG, WEBP ou GIF."
        )

    # O ponteiro precisa voltar ao início depois de medir o tamanho
    arquivo.seek(0, os.SEEK_END)
    tamanho = arquivo.tell()
    arquivo.seek(0)

    if tamanho > TAMANHO_MAXIMO_IMAGEM:
        raise ValueError("A imagem deve ter no máximo 5 MB.")

    nome_imagem = f"{prefixo}_{identificador}.{extensao}"
    pasta = os.path.join(app.root_path, PASTA_IMAGENS)
    os.makedirs(pasta, exist_ok=True)
    arquivo.save(os.path.join(pasta, nome_imagem))

    # Remove versões antigas com outra extensão, para não sobrar arquivo órfão
    for outra in EXTENSOES_IMAGEM:
        if outra == extensao:
            continue
        antigo = os.path.join(pasta, f"{prefixo}_{identificador}.{outra}")
        if os.path.exists(antigo):
            os.remove(antigo)

    return nome_imagem


def atualizar_imagem(tabela, registro_id, arquivo, prefixo):
    """Salva a imagem e grava o nome na coluna `imagem` da tabela."""
    nome_imagem = salvar_imagem(arquivo, prefixo, registro_id)

    if not nome_imagem:
        return None

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            f"UPDATE {tabela} SET imagem = %s WHERE id = %s",
            (nome_imagem, registro_id)
        )
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()

    return nome_imagem


@app.template_filter("imagem_ou")
def filtro_imagem_ou(nome_imagem, padrao="imagemproduto.png"):
    """Devolve o caminho da imagem do registro ou de uma imagem padrão.

    Se o arquivo tiver sumido da pasta, cai no padrão em vez de mostrar
    um ícone de imagem quebrada.
    """
    if nome_imagem:
        caminho = os.path.join(app.root_path, PASTA_IMAGENS, nome_imagem)
        if os.path.exists(caminho):
            return nome_imagem

    return padrao


# ------------ FORMATAÇÃO ----------#

@app.template_filter("moeda")
def formatar_moeda(valor):
    """Formata um número no padrão brasileiro: 1234.5 -> 1.234,50."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0

    # Formata no padrão americano e troca os separadores de posição
    texto = f"{numero:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


@app.template_filter("telefone")
def filtro_telefone(valor):
    """Exibe o telefone sempre no mesmo formato, esteja ele salvo como estiver."""
    return formatar_telefone(valor or "")


@app.template_filter("quantidade")
def formatar_quantidade(valor):
    """Mostra quantidades sem casas decimais desnecessárias: 3.000 -> 3."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0

    if numero == int(numero):
        return str(int(numero))

    return f"{numero:.3f}".rstrip("0").rstrip(".").replace(".", ",")


# ------------ MENSAGENS DE ERRO ----------#

# Rótulos amigáveis para as colunas com índice único no banco.
CAMPOS_UNICOS = {
    "cnpj":          "CNPJ",
    "cpf":           "CPF",
    "cpf_cnpj":      "CPF/CNPJ",
    "sku":           "SKU",
    "codigo_barras": "código de barras",
    "email":         "e-mail",
}


def mensagem_erro(e):
    """Converte exceções do banco em texto compreensível para o usuário.

    Sem isso, uma tentativa de cadastrar um CNPJ repetido mostrava na tela
    algo como "1062 (23000): Duplicate entry ... for key 'cnpj'".
    """
    texto = str(e)

    if "Duplicate entry" in texto:
        for coluna, rotulo in CAMPOS_UNICOS.items():
            if f"key '{coluna}'" in texto or f"key '{coluna}_" in texto:
                return f"Já existe um registro cadastrado com este {rotulo}."
        return "Já existe um registro cadastrado com estes dados."

    if "foreign key constraint fails" in texto.lower():
        return ("Não foi possível concluir: este registro está vinculado a "
                "outros dados do sistema.")

    if "cannot be null" in texto.lower():
        return "Preencha todos os campos obrigatórios."

    return texto


# ------------ LISTAGENS (filtro e agrupamento feitos no servidor) ----------#

def filtrar_produtos(produtos, busca):
    """Filtra a listagem de produtos pelo texto digitado na barra de pesquisa.

    A busca é resolvida aqui, no Python, e não no JavaScript da página:
    o formulário envia ?busca=... por GET e a rota devolve a lista já filtrada.
    """
    termo = (busca or "").strip().lower()

    if not termo:
        return produtos

    def combina(produto):
        campos = (
            produto.get("nome"),
            produto.get("sku"),
            produto.get("categoria"),
            produto.get("fornecedor"),
            produto.get("codigo_barras"),
        )
        return any(termo in str(campo).lower() for campo in campos if campo)

    return [produto for produto in produtos if combina(produto)]


def agrupar_produtos_por_id(produtos):
    """Soma as quantidades de linhas repetidas do mesmo produto.

    Um produto pode ocupar várias localizações dentro do mesmo galpão, o que
    gera uma linha por localização. Antes essa soma era feita no navegador;
    agora a lista já chega pronta ao template.
    """
    agrupados = {}

    for produto in produtos:
        chave = produto.get("id")
        atual = agrupados.get(chave)

        if atual is None:
            agrupado = dict(produto)
            agrupado["quantidade"] = to_float(produto.get("quantidade"))
            agrupado["quantidade_minimo"] = to_float(produto.get("quantidade_minimo"))
            agrupados[chave] = agrupado
            continue

        atual["quantidade"] += to_float(produto.get("quantidade"))
        atual["quantidade_minimo"] = min(
            atual["quantidade_minimo"],
            to_float(produto.get("quantidade_minimo"))
        )

    return list(agrupados.values())


# ------------- LANDINGPAGE ------------- #

@app.route('/')
def landing():
    return render_template('landing.html')

# Rota antiga mantida como atalho: "home.html" nunca existiu no projeto,
# então /home leva o usuário para o painel (ou para o login, se não houver sessão).
@app.route('/home')
def home():
    if "usuario_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("landing"))

# ---------------- LOGIN OBRIGATÓRIO ---------------- #

def login_obrigatorio(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Faça login para continuar.", "erro")
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return wrap

# ---------------- INDEX ---------------- #

@app.route("/dashboard")
@login_obrigatorio
def dashboard():
    """Painel inicial.

    Antes os cartões de ganhos, gastos, lucro, atividades e alertas eram
    textos fixos no HTML ("Entrada de 50 unidades - Produto A"). Agora todos
    os números vêm de consultas ao banco.
    """
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        # ---- Contagens gerais ----
        cursor.execute("SELECT COUNT(*) AS total FROM fornecedor")
        total_fornecedores = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM cliente")
        total_clientes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM galpao")
        total_galpoes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM produto WHERE ativo = TRUE")
        total_produtos = cursor.fetchone()["total"]

        # ---- Ganhos: pedidos de saída que não foram cancelados ----
        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_cliente
            WHERE status_pedido <> 'cancelado'
        """)
        ganhos = to_float(cursor.fetchone()["total"])

        # ---- Gastos: pedidos de entrada que não foram cancelados ----
        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_fornecedor
            WHERE status <> 'cancelado'
        """)
        gastos = to_float(cursor.fetchone()["total"])

        lucro = ganhos - gastos

        # ---- Comparação com o mês anterior, para a variação percentual ----
        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_cliente
            WHERE status_pedido <> 'cancelado'
              AND data_pedido >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
        """)
        ganhos_mes = to_float(cursor.fetchone()["total"])

        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_cliente
            WHERE status_pedido <> 'cancelado'
              AND data_pedido >= DATE_FORMAT(CURDATE() - INTERVAL 1 MONTH, '%Y-%m-01')
              AND data_pedido <  DATE_FORMAT(CURDATE(), '%Y-%m-01')
        """)
        ganhos_mes_anterior = to_float(cursor.fetchone()["total"])

        if ganhos_mes_anterior > 0:
            variacao = (ganhos_mes - ganhos_mes_anterior) / ganhos_mes_anterior * 100
        else:
            # Sem base de comparação não dá para calcular percentual
            variacao = None

        # ---- Valor imobilizado em estoque (preço de custo) ----
        cursor.execute("""
            SELECT COALESCE(SUM(e.quantidade * p.preco_custo), 0) AS total
            FROM estoque e
            JOIN produto p ON p.id = e.produto_id
            WHERE p.ativo = TRUE
        """)
        valor_estoque = to_float(cursor.fetchone()["total"])

        # ---- Produtos mais vendidos ----
        cursor.execute("""
            SELECT p.nome, p.sku,
                   SUM(ipc.quantidade) AS quantidade,
                   SUM(ipc.quantidade * ipc.preco_unitario_no_momento) AS receita
            FROM item_pedido_cliente ipc
            JOIN produto p        ON p.id = ipc.produto_id
            JOIN pedido_cliente pc ON pc.id = ipc.pedido_cliente_id
            WHERE pc.status_pedido <> 'cancelado'
            GROUP BY p.id
            ORDER BY quantidade DESC
            LIMIT 5
        """)
        mais_vendidos = cursor.fetchall()

        # ---- Últimas movimentações ----
        cursor.execute("""
            SELECT m.tipo, m.quantidade, m.data_movimentacao, m.observacao,
                   p.nome AS produto, g.nome AS galpao
            FROM movimentacao m
            JOIN produto p      ON p.id = m.produto_id
            LEFT JOIN galpao g  ON g.id = m.galpao_id
            ORDER BY m.data_movimentacao DESC, m.id DESC
            LIMIT 5
        """)
        atividades = cursor.fetchall()

        # ---- Alertas de estoque baixo ----
        cursor.execute("""
            SELECT p.nome, p.sku, g.nome AS galpao,
                   e.quantidade, e.estoque_minimo
            FROM estoque e
            JOIN produto p     ON p.id = e.produto_id
            LEFT JOIN galpao g ON g.id = e.galpao_id
            WHERE p.ativo = TRUE
              AND e.quantidade <= e.estoque_minimo
            ORDER BY (e.quantidade - e.estoque_minimo), p.nome
            LIMIT 5
        """)
        alertas = cursor.fetchall()

        cursor.execute("""
            SELECT COUNT(*) AS total
            FROM estoque e
            JOIN produto p ON p.id = e.produto_id
            WHERE p.ativo = TRUE
              AND e.quantidade <= e.estoque_minimo
        """)
        total_alertas = cursor.fetchone()["total"]

        cursor.execute("SELECT nome FROM empresa WHERE id = %s", (session["empresa_id"],))
        empresa = cursor.fetchone()
        empresa_nome = empresa["nome"] if empresa else ""

    finally:
        cursor.close()
        conexao.close()

    return render_template(
        "dashboard.html",
        empresa_nome=empresa_nome,
        total_fornecedores=total_fornecedores,
        total_clientes=total_clientes,
        total_galpoes=total_galpoes,
        total_produtos=total_produtos,
        ganhos=ganhos,
        gastos=gastos,
        lucro=lucro,
        variacao=variacao,
        valor_estoque=valor_estoque,
        mais_vendidos=mais_vendidos,
        atividades=atividades,
        alertas=alertas,
        total_alertas=total_alertas
    )

# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not email or not senha:
            flash("Informe o e-mail e a senha.", "erro")
            return render_template("login.html")

        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT id, nome, email, senha, empresa_id, tipo, ativo
                FROM usuario
                WHERE email = %s
            """, (email,))

            usuario = cursor.fetchone()

            if not usuario:
                flash("Email ou senha inválidos!", "erro")
                return render_template("login.html")

            senha_correta = check_password_hash(
                usuario["senha"],
                senha
            )

            if not senha_correta:
                flash("Email ou senha inválidos!", "erro")
                return render_template("login.html")

            if not usuario["ativo"]:
                flash("Usuário inativo.", "erro")
                return render_template("login.html")

            session.clear()

            session["usuario_logado"] = usuario["email"]
            session["usuario_id"] = usuario["id"]
            session["empresa_id"] = usuario["empresa_id"]
            session["tipo"] = usuario["tipo"]

            flash("Login realizado!", "sucesso")

            return redirect(url_for("dashboard"))

        except Exception as e:

            app.logger.exception("Falha ao autenticar usuário")

            flash(f"Erro ao realizar login: {e}", "erro")

            return render_template("login.html")

        finally:
            cursor.close()
            conexao.close()

    return render_template("login.html")

# ---------------- REDEFINIR SENHA ---------------- #

@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT id, usuario_id, expira_em, usado
            FROM recuperacao_senha
            WHERE token = %s
        """, (token,))

        recuperacao = cursor.fetchone()

        if not recuperacao:
            flash("Token de recuperação inválido.", "erro")
            return redirect(url_for("esqueci_senha"))

        if recuperacao["usado"] == 1:
            flash("Este link de recuperação já foi utilizado.", "erro")
            return redirect(url_for("esqueci_senha"))

        if recuperacao["expira_em"] < datetime.now():
            flash("Este link de recuperação expirou.", "erro")
            return redirect(url_for("esqueci_senha"))

        # ------------------------------------------------
        # GET
        # ------------------------------------------------

        if request.method == "GET":

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        # ------------------------------------------------
        # POST
        # ------------------------------------------------

        senha = request.form.get("senha", "").strip()
        confirmar_senha = request.form.get("confirmar_senha", "").strip()

        if not senha:
            flash("Digite uma nova senha.", "erro")

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        if not confirmar_senha:
            flash("Confirme sua nova senha.", "erro")

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        if senha != confirmar_senha:
            flash("As senhas não são iguais.", "erro")

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        # Criptografa a nova senha
        senha_hash = generate_password_hash(senha)

        # Atualiza a senha
        cursor.execute("""
            UPDATE usuario
            SET senha = %s
            WHERE id = %s
        """, (
            senha_hash,
            recuperacao["usuario_id"]
        ))

        # Marca o token como utilizado
        cursor.execute("""
            UPDATE recuperacao_senha
            SET usado = 1
            WHERE id = %s
        """, (
            recuperacao["id"],
        ))

        conexao.commit()

        flash(
            "Senha redefinida com sucesso! Faça login com sua nova senha.",
            "sucesso"
        )

        return redirect(url_for("login"))

    except Exception as e:

        conexao.rollback()

        app.logger.exception("Falha ao redefinir senha")

        flash(
            f"Erro ao redefinir senha: {e}",
            "erro"
        )

        return redirect(url_for("esqueci_senha"))

    finally:

        cursor.close()
        conexao.close()

# ---------------- RECUPERAÇÃO DE SENHA ---------------- #

@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Informe seu e-mail.", "erro")
            return redirect(url_for("esqueci_senha"))

        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:

            cursor.execute("""
                SELECT id, email
                FROM usuario
                WHERE email = %s
                  AND ativo = 1
            """, (email,))

            usuario = cursor.fetchone()

            if usuario:

                # Gera token seguro
                token = secrets.token_urlsafe(32)

                # Token válido por 30 minutos
                expira_em = datetime.now() + timedelta(minutes=30)

                # Salva no banco
                cursor.execute("""
                    INSERT INTO recuperacao_senha
                    (usuario_id, token, expira_em, usado)
                    VALUES (%s, %s, %s, 0)
                """, (
                    usuario["id"],
                    token,
                    expira_em
                ))

                conexao.commit()

                # Link para redefinir a senha
                link = url_for(
                    "redefinir_senha",
                    token=token,
                    _external=True
                )

                print("======================================")
                print("RECUPERAÇÃO DE SENHA")
                print("Usuário:", usuario["email"])
                print("Link:", link)
                print("Expira em:", expira_em)
                print("======================================")

            flash(
                "Se o e-mail estiver cadastrado, você receberá as instruções para recuperar a senha.",
                "sucesso"
            )

        except Exception as e:

            conexao.rollback()

            app.logger.exception("Falha ao gerar token de recuperação")

            flash(
                "Ocorreu um erro ao solicitar a recuperação da senha.",
                "erro"
            )

        finally:

            cursor.close()
            conexao.close()

        return redirect(url_for("esqueci_senha"))

    return render_template("esqueci_senha.html")

# ---------------- CONFIG ---------------- #

@app.route('/config')
@login_obrigatorio
def config():
    """Tela de configurações.

    Antes era um mockup: os campos vinham preenchidos com dados fixos
    ("Ricardo Souza"), nenhum formulário tinha destino e o botão de modo
    escuro não fazia nada. Agora tudo vem do banco e cada bloco tem rota.
    """
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT id, nome, email, cpf, telefone, tipo
            FROM usuario
            WHERE id = %s
        """, (session["usuario_id"],))
        usuario = cursor.fetchone()

        cursor.execute("""
            SELECT id, nome, cnpj
            FROM empresa
            WHERE id = %s
        """, (session["empresa_id"],))
        empresa = cursor.fetchone()

    finally:
        cursor.close()
        conexao.close()

    return render_template("config.html", usuario=usuario, empresa=empresa)


@app.route('/config/perfil', methods=["POST"])
@login_obrigatorio
def salvar_perfil():
    nome     = (request.form.get("nome") or "").strip()
    email    = (request.form.get("email") or "").strip().lower()
    telefone = (request.form.get("telefone") or "").strip()

    if not nome:
        flash("Informe o nome do responsável.", "erro")
        return redirect(url_for("config"))

    if not email_valido(email):
        flash("Informe um e-mail válido.", "erro")
        return redirect(url_for("config"))

    if telefone and not telefone_valido(telefone):
        flash("Telefone inválido. Use DDD + número.", "erro")
        return redirect(url_for("config"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE usuario
            SET nome = %s, email = %s, telefone = %s
            WHERE id = %s
        """, (nome, email, formatar_telefone(telefone) if telefone else None,
              session["usuario_id"]))

        conexao.commit()

        # O e-mail é usado para exibir quem está logado
        session["usuario_logado"] = email
        flash("Perfil atualizado com sucesso!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao salvar o perfil: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("config"))


@app.route('/config/senha', methods=["POST"])
@login_obrigatorio
def alterar_senha():
    senha_atual = request.form.get("senha_atual") or ""
    nova_senha  = request.form.get("nova_senha") or ""
    confirmar   = request.form.get("confirmar_senha") or ""

    if len(nova_senha) < 6:
        flash("A nova senha deve ter pelo menos 6 caracteres.", "erro")
        return redirect(url_for("config"))

    if nova_senha != confirmar:
        flash("A confirmação não confere com a nova senha.", "erro")
        return redirect(url_for("config"))

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT senha FROM usuario WHERE id = %s", (session["usuario_id"],)
        )
        usuario = cursor.fetchone()

        # A senha atual é conferida para ninguém trocar a senha de uma
        # sessão deixada aberta.
        if not usuario or not check_password_hash(usuario["senha"], senha_atual):
            flash("A senha atual está incorreta.", "erro")
            return redirect(url_for("config"))

        cursor.execute("""
            UPDATE usuario SET senha = %s WHERE id = %s
        """, (generate_password_hash(nova_senha), session["usuario_id"]))

        conexao.commit()
        flash("Senha alterada com sucesso!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao alterar a senha: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("config"))


@app.route('/config/empresa', methods=["POST"])
@login_obrigatorio
def salvar_empresa():
    nome = (request.form.get("nome") or "").strip()
    cnpj = (request.form.get("cnpj") or "").strip() or None

    if not nome:
        flash("Informe a razão social da empresa.", "erro")
        return redirect(url_for("config"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE empresa SET nome = %s, cnpj = %s WHERE id = %s
        """, (nome, cnpj, session["empresa_id"]))

        conexao.commit()

        # A imagem da empresa é a que aparece no topo do menu lateral
        atualizar_imagem("empresa", session["empresa_id"],
                         request.files.get("imagem"), "empresa")

        flash("Dados da empresa atualizados!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao salvar a empresa: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("config"))


# ---------------- LOGOUT ---------------- #

# Sair é uma mudança de estado, então exige POST: um link GET podia ser
# disparado por pré-carregamento do navegador e derrubar a sessão sozinho.
@app.route('/logout', methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu da conta.", "sucesso")
    return redirect(url_for('login'))

# ---------------- CADASTRO DE EMPRESA ---------------- #

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro_emp():

    if request.method == "POST":

        nome = request.form.get("nome", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefone = request.form.get("telefone", "").strip()
        senha = request.form.get("senha", "")

        if not nome:
            flash("Informe o nome da empresa.", "erro")
            return render_template("cadastro.html")

        if not cnpj:
            flash("Informe o CNPJ.", "erro")
            return render_template("cadastro.html")

        if not email_valido(email):
            flash("Informe um e-mail válido.", "erro")
            return render_template("cadastro.html")

        if not senha:
            flash("Informe uma senha.", "erro")
            return render_template("cadastro.html")

        senha_hash = generate_password_hash(senha)

        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:

            # Verifica se o CNPJ já existe
            cursor.execute("""
                SELECT id
                FROM empresa
                WHERE cnpj = %s
                LIMIT 1
            """, (cnpj,))

            if cursor.fetchone():
                flash("Este CNPJ já está cadastrado.", "erro")
                return render_template("cadastro.html")

            # Verifica se o e-mail já existe
            cursor.execute("""
                SELECT id
                FROM usuario
                WHERE email = %s
                LIMIT 1
            """, (email,))

            if cursor.fetchone():
                flash("Este e-mail já está cadastrado.", "erro")
                return render_template("cadastro.html")

            # Cria a empresa
            cursor.execute("""
                INSERT INTO empresa (nome, cnpj)
                VALUES (%s, %s)
            """, (nome, cnpj))

            empresa_id = cursor.lastrowid

            # Cria o usuário administrador
            cursor.execute("""
                INSERT INTO usuario
                (nome, telefone, email, senha, empresa_id, tipo, ativo)
                VALUES (%s, %s, %s, %s, %s, 'admin', 1)
            """, (
                nome,
                telefone,
                email,
                senha_hash,
                empresa_id
            ))

            conexao.commit()

            flash("Cadastro realizado com sucesso!", "sucesso")

            return redirect(url_for("login"))

        except Exception as e:

            conexao.rollback()

            app.logger.exception("Falha ao cadastrar empresa")

            flash(
                f"Erro ao cadastrar empresa: {e}",
                "erro"
            )

        finally:
            cursor.close()
            conexao.close()

    return render_template("cadastro.html")


# ---------------- ESTOQUE ---------------- #

@app.route("/estoque")
@login_obrigatorio
def estoque():
    # Visão consolidada: soma o estoque do produto em todos os galpões.
    busca = (request.args.get("busca") or "").strip()

    return render_template(
        "estoque.html",
        produtos=filtrar_produtos(Estoque.find_all_consolidado(), busca),
        fornecedores=Fornecedor.find_all(),
        galpao=None,
        galpoes=Galpao.find_all(),
        busca=busca
    )


@app.route("/estoque/<int:galpao_id>")
@login_obrigatorio
def estoque_galpao(galpao_id):
    galpao = Galpao.find_by_id(galpao_id)

    if not galpao:
        flash("Galpão não encontrado.", "erro")
        return redirect(url_for("galpao"))

    busca = (request.args.get("busca") or "").strip()

    # A consolidação por produto é feita aqui, no Python, e não mais no
    # JavaScript da página: um produto guardado em várias localizações do
    # mesmo galpão aparece em uma única linha com a quantidade somada.
    produtos = agrupar_produtos_por_id(Estoque.find_by_galpao(galpao_id))

    return render_template(
        "estoque.html",
        produtos=filtrar_produtos(produtos, busca),
        fornecedores=Fornecedor.find_all(),
        galpao=galpao,
        galpoes=Galpao.find_all(),
        busca=busca
    )


@app.route("/estoque/movimentar", methods=["POST"])
@login_obrigatorio
def movimentar_estoque():
    galpao_id = to_int(request.form.get("galpao_id"))
    try:
        produto_id = to_int(request.form.get("produto_id"))
        quantidade = to_int(request.form.get("quantidade"))
        tipo = request.form.get("tipo")

        Estoque.movimentar(produto_id, galpao_id, quantidade, tipo)
        flash("Movimentação realizada com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("estoque", galpao_id=galpao_id))

# ---------------- INFO GALPAO ---------------- #

@app.route("/info_galpao/<int:galpao_id>")
@login_obrigatorio
def info_galpao(galpao_id):
    galpao = Galpao.find_by_id(galpao_id)

    if not galpao:
        flash("Galpão não encontrado.", "erro")
        return redirect(url_for("galpao"))

    funcionarios = Funcionario.find_by_galpao(galpao_id)
    empilhadeiras = Empilhadeira.find_by_galpao(galpao_id)

    return render_template(
        "info_galpao.html",
        galpao=galpao,
        funcionarios=funcionarios,
        empilhadeiras=empilhadeiras
    )

@app.route("/galpao/atualizar/<int:galpao_id>", methods=["POST"])
@login_obrigatorio
def atualizar_galpao(galpao_id):
    try:

        nome = request.form.get("nome", "").strip()
        if not nome:
            flash("O nome do galpão é obrigatório.", "erro")
            return redirect(url_for("info_galpao", galpao_id=galpao_id))

        telefone = formatar_telefone(request.form.get("telefone", "").strip())

        caixas_por_nivel      = to_int(request.form.get("caixas_por_nivel"))
        niveis_por_prateleira = to_int(request.form.get("niveis_por_prateleira"))
        total_prateleiras     = to_int(request.form.get("total_prateleiras"))
        capacidade_total      = caixas_por_nivel * niveis_por_prateleira * total_prateleiras

        dados = {
            "nome_resp":             request.form.get("nome_resp"),
            "email_resp":            request.form.get("email_resp"),
            "telefone":              telefone,
            "stats":                 request.form.get("stats"),
            "nome":                  nome,
            "cep":                   request.form.get("cep"),
            "endereco":              request.form.get("endereco"),
            "referencia":            request.form.get("referencia"),
            "area_total":            to_float(request.form.get("area_total")),
            "caixas_por_nivel":      caixas_por_nivel,
            "niveis_por_prateleira": niveis_por_prateleira,
            "total_prateleiras":     total_prateleiras,
            "capacidade_total":      capacidade_total,
        }
        Galpao.update(galpao_id, dados)

        # Troca da imagem do galpão, quando enviada
        atualizar_imagem("galpao", galpao_id,
                         request.files.get("imagem"), "galpao")

        flash("Galpão atualizado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("info_galpao", galpao_id=galpao_id))



@app.route("/galpao/deletar/<int:galpao_id>", methods=["POST"])
@login_obrigatorio
def deletar_galpao(galpao_id):
    try:
        Galpao.delete(galpao_id)
        flash("Galpão excluído com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("galpao"))
    


# ---------------- EMPILHADEIRAS ---------------- #

@app.route("/empilhadeira/salvar", methods=["POST"])
@login_obrigatorio
def salvar_empilhadeira():
    try:
        empilhadeira = Empilhadeira(
            marca=request.form.get("marca"),
            modelo=request.form.get("modelo"),
            ano_fabricacao=request.form.get("ano_fabricacao"),
            tipo_combustivel=request.form.get("tipo_combustivel"),
            capacidade=to_int(request.form.get("capacidade")),
            galpao_id=to_int(request.form.get("galpao_id")) or None,
            funcionario_id=to_int(request.form.get("funcionario_id")) or None,
            ativo=request.form.get("ativo")
        )
        empilhadeira.insert()
        flash("Empilhadeira cadastrada com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("info_galpao", galpao_id=request.form.get("galpao_id")))

@app.route("/empilhadeira/atualizar/<int:empilhadeira_id>", methods=["POST"])
@login_obrigatorio
def atualizar_empilhadeira(empilhadeira_id):
    galpao_id = to_int(request.form.get("galpao_id"))

    dados = {
        "marca":            request.form.get("marca"),
        "modelo":           request.form.get("modelo"),
        "ano_fabricacao":   request.form.get("ano_fabricacao"),
        "tipo_combustivel": request.form.get("tipo_combustivel"),
        "capacidade":       to_int(request.form.get("capacidade")),
        # Operador responsável: vazio significa "sem operador atribuído"
        "funcionario_id":   to_int(request.form.get("funcionario_id")) or None,
        "ativo":            request.form.get("ativo"),
    }

    try:
        Empilhadeira.update(empilhadeira_id, dados)
        flash("Empilhadeira atualizada com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("info_galpao", galpao_id=galpao_id))


@app.route("/empilhadeira/deletar/<int:empilhadeira_id>", methods=["POST"])
@login_obrigatorio
def deletar_empilhadeira(empilhadeira_id):
    galpao_id = request.form.get("galpao_id")
    try:
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM empilhadeira WHERE id = %s", (empilhadeira_id,))
        conn.commit()
        conn.close()
        flash("Empilhadeira removida com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("info_galpao", galpao_id=galpao_id))

# ---------------- PRODUTOS ---------------- #

@app.route("/produtos")
@login_obrigatorio
def produtos():
    # Mesma listagem consolidada de /estoque, mantida como rota separada
    # porque vários redirecionamentos apontam para "produtos".
    busca = (request.args.get("busca") or "").strip()

    return render_template(
        "estoque.html",
        produtos=filtrar_produtos(Estoque.find_all_consolidado(), busca),
        fornecedores=Fornecedor.find_all(),
        galpao=None,
        galpoes=Galpao.find_all(),
        busca=busca
    )

@app.route("/produto/salvar", methods=["POST"])
@login_obrigatorio
def salvar_produto():
    sku = request.form.get("sku", "").strip()
    nome = request.form.get("nome", "").strip()
    galpao_id = to_int(request.form.get("galpao_id"))
    quantidade = to_int(request.form.get("quantidade", 1))
    estoque_minimo = to_int(request.form.get("quantidade_minimo", 0))

    if not sku or not nome:
        flash("SKU e Nome são obrigatórios.", "erro")
        return redirect(url_for("produtos"))

    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Verifica se o produto já existe pelo SKU
        cursor.execute("SELECT id FROM produto WHERE sku = %s LIMIT 1", (sku,))
        produto_existente = cursor.fetchone()

        if produto_existente:
            produto_id = produto_existente["id"]
        else:
            # 2. Se não existir, insere o novo produto
            dados_produto = (
                sku,
                nome,
                request.form.get("descricao"),
                request.form.get("categoria"),
                to_float(request.form.get("preco_custo")),
                to_float(request.form.get("preco_venda")),
                to_float(request.form.get("peso")),
                to_float(request.form.get("volume")),
                request.form.get("tipo"),
                request.form.get("codigo_barras"),
                to_int(request.form.get("item_por_caixa"))
            )
            
            cursor.execute("""
                INSERT INTO produto 
                (sku, nome, descricao, categoria, preco_custo, preco_venda, peso, volume, tipo, codigo_barras, item_por_caixa, ativo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """, dados_produto)
            
            produto_id = cursor.lastrowid

        # 3. Trata o upload da imagem (se enviada)
        imagem = request.files.get("imagem")
        if imagem and imagem.filename:
            extensaovalida = {"png", "jpg", "jpeg", "webp"}
            extensao = imagem.filename.rsplit(".", 1)[-1].lower() if "." in imagem.filename else ""
            
            if extensao in extensaovalida:
                nome_imagem = f"produto_{produto_id}.{extensao}"
                pasta_imagem = os.path.join(app.root_path, "static", "imagem")
                os.makedirs(pasta_imagem, exist_ok=True)
                imagem.save(os.path.join(pasta_imagem, nome_imagem))
                
                cursor.execute("UPDATE produto SET imagem = %s WHERE id = %s", (nome_imagem, produto_id))

        # 4. Atualiza ou insere a quantidade no estoque do galpão (evita duplicar linhas)
        if galpao_id:
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    quantidade = quantidade + VALUES(quantidade),
                    estoque_minimo = VALUES(estoque_minimo)
            """, (produto_id, galpao_id, quantidade, estoque_minimo))

        conn.commit()
        flash("Produto e estoque processados com sucesso!", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao salvar produto: {mensagem_erro(e)}", "erro")
    finally:
        cursor.close()
        conn.close()

    if galpao_id:
        return redirect(url_for("estoque_galpao", galpao_id=galpao_id))
    return redirect(url_for("produtos"))


@app.route("/produto/editar/<int:id>")
@login_obrigatorio
def editar_produto(id):
    # Redireciona para info_produtos, que já exibe o formulário de edição
    return redirect(url_for("info_produtos", id=id))

@app.route("/produto/atualizar/<int:id>", methods=["POST"])
@login_obrigatorio
def atualizar_produto(id):
    produto = Produto.find_by_id(id)

    if not produto:
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("produtos"))

    # O formulário envia "quantidade_minimo"; antes a rota lia "estoque_minimo",
    # então o mínimo era gravado como 0 a cada salvamento.
    estoque_minimo = to_int(request.form.get("quantidade_minimo"))

    dados = {
        "sku": request.form.get("sku"),
        "nome": request.form.get("nome"),
        "descricao": request.form.get("descricao"),
        "categoria": request.form.get("categoria"),
        "preco_custo": to_float(request.form.get("preco_custo")),
        "preco_venda": to_float(request.form.get("preco_venda")),
        "peso": to_float(request.form.get("peso")),
        "volume": to_float(request.form.get("volume")),
        "tipo": request.form.get("tipo"),
        "codigo_barras": request.form.get("codigo_barras") or None,
        "item_por_caixa": to_int(request.form.get("item_por_caixa")),
        # Produto.update grava a coluna `imagem` sempre. Sem este valor a
        # imagem atual era apagada toda vez que o produto era editado.
        "imagem": produto.get("imagem"),
    }

    if not dados["sku"] or not dados["nome"]:
        flash("SKU e Nome são obrigatórios.", "erro")
        return redirect(url_for("info_produtos", id=id))

    try:
        # Troca da imagem, quando uma nova for enviada
        imagem = request.files.get("imagem")

        if imagem and imagem.filename:
            extensoes_validas = {"png", "jpg", "jpeg", "webp"}
            extensao = (imagem.filename.rsplit(".", 1)[-1].lower()
                        if "." in imagem.filename else "")

            if extensao not in extensoes_validas:
                flash("Formato de imagem inválido. Use PNG, JPG, JPEG ou WEBP.", "erro")
                return redirect(url_for("info_produtos", id=id))

            nome_imagem = f"produto_{id}.{extensao}"
            pasta_imagem = os.path.join(app.root_path, "static", "imagem")
            os.makedirs(pasta_imagem, exist_ok=True)
            imagem.save(os.path.join(pasta_imagem, nome_imagem))
            dados["imagem"] = nome_imagem

        Produto.update(id, dados)

        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE estoque
                SET estoque_minimo = %s
                WHERE produto_id = %s
            """, (estoque_minimo, id))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        flash("Produto atualizado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro ao atualizar produto: {mensagem_erro(e)}", "erro")

    return redirect(url_for("info_produtos", id=id))


@app.route("/produto/ajustar_estoque/<int:id>", methods=["POST"])
@login_obrigatorio
def ajustar_estoque_produto(id):
    """Corrige o saldo de um produto em um galpão.

    A quantidade não é editada junto com os dados do produto porque o saldo é
    por galpão e precisa ficar registrado: todo acerto vira uma movimentação
    do tipo "ajuste_inventario".
    """
    galpao_id  = to_int(request.form.get("galpao_id"))
    quantidade = to_float(request.form.get("quantidade"))
    observacao = (request.form.get("observacao") or "").strip() or "Ajuste de inventário"

    if not galpao_id:
        flash("Selecione o galpão do ajuste.", "erro")
        return redirect(url_for("info_produtos", id=id))

    if quantidade < 0:
        flash("A quantidade não pode ser negativa.", "erro")
        return redirect(url_for("info_produtos", id=id))

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
            VALUES (%s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE quantidade = VALUES(quantidade)
        """, (id, galpao_id, quantidade))

        cursor.execute("""
            INSERT INTO movimentacao
                (produto_id, galpao_id, tipo, quantidade, observacao)
            VALUES (%s, %s, 'ajuste_inventario', %s, %s)
        """, (id, galpao_id, quantidade, observacao))

        conn.commit()
        flash("Saldo ajustado e movimentação registrada.", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao ajustar o saldo: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("info_produtos", id=id))

@app.route("/produto/desativar/<int:id>", methods=["POST"])
@login_obrigatorio
def desativar_produto(id):
    try:
        Produto.desativar(id)
        flash("Produto desativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("info_produtos", id=id))

@app.route("/produto/reativar/<int:id>", methods=["POST"])
@login_obrigatorio
def reativar_produto(id):
    try:
        Produto.reativar(id)
        flash("Produto reativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("produtos_inativos"))

@app.route("/produtos/inativos")
@login_obrigatorio
def produtos_inativos():
    lista = Produto.find_inativos()
    return render_template("produtos_inativos.html", produtos=lista)

@app.route("/produto/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_produto(id):
    try:
        Produto.safe_delete(id)
        flash("Produto excluído com sucesso!", "sucesso")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("info_produtos", id=id))
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
        return redirect(url_for("info_produtos", id=id))

    return redirect(url_for("produtos"))

# ---------------- INFO PRODUTO ---------------- #

@app.route("/info_produto/<int:id>")
@login_obrigatorio
def info_produtos(id):
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                p.*,
                COALESCE(SUM(e.quantidade), 0)      AS quantidade,
                COALESCE(MIN(e.estoque_minimo), 0)  AS estoque_minimo,
                GROUP_CONCAT(DISTINCT f.nome ORDER BY f.nome SEPARATOR ', ')
                                                    AS fornecedor
            FROM produto p
            LEFT JOIN estoque e              ON p.id = e.produto_id
            LEFT JOIN fornecedor_produto fp  ON p.id = fp.produto_id
            LEFT JOIN fornecedor f           ON fp.fornecedor_id = f.id
            WHERE p.id = %s
            GROUP BY p.id
        """, (id,))
        produto = cursor.fetchone()

        if not produto:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("produtos"))

        produtos = Produto.find_all_completo()

        # Saldo por galpão: o total exibido no topo é a soma destes valores,
        # e cada linha permite ajustar o estoque daquele galpão.
        cursor.execute("""
            SELECT e.galpao_id, g.nome AS galpao_nome,
                   e.quantidade, e.estoque_minimo
            FROM estoque e
            JOIN galpao g ON g.id = e.galpao_id
            WHERE e.produto_id = %s
            ORDER BY g.nome
        """, (id,))
        saldos = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        "info_produto.html",
        produto=produto,
        produtos=produtos,
        saldos=saldos,
        galpoes=Galpao.find_all()
    )

# ---------------- GALPÕES ---------------- #

@app.route("/galpao")
@login_obrigatorio
def galpao():
    return render_template("galpao.html", galpoes=Galpao.find_all())

@app.route("/galpao/novo")
@login_obrigatorio
def novo_galpao():
    return render_template("galpao.html")

@app.route("/galpao/salvar", methods=["POST"])
@login_obrigatorio
def salvar_galpao():
    try:
        email = request.form.get("email_resp", "").strip()

        if not email_valido(email):
            flash("Informe um e-mail válido.", "erro")
            return redirect(url_for("galpao"))

        nome_resp = request.form.get("nome_resp", "").strip()

        if not nome_valido(nome_resp):
            flash("O nome do responsável deve conter apenas letras.", "erro")
            return redirect(url_for("galpao"))

        area_total = request.form.get("area_total", "").strip()

        if not area_valida(area_total):
            flash("A área total deve ser um número maior que zero.", "erro")
            return redirect(url_for("galpao"))


        telefone = request.form.get("telefone", "").strip()

        if not telefone_valido(telefone):
            flash("Informe um telefone válido com 10 ou 11 números.", "erro")
            return redirect(url_for("info_galpao", galpao_id=galpao_id))

        telefone = formatar_telefone(telefone)

        if not telefone_valido(telefone):
            flash("Informe um telefone válido com 10 ou 11 números.", "erro")
            return redirect(url_for("galpao"))

        caixas_por_nivel = to_int(request.form.get("caixas_por_nivel"))

        caixas_por_nivel = to_int(request.form.get("caixas_por_nivel"))
        niveis_por_prateleira = to_int(request.form.get("niveis_por_prateleira"))
        total_prateleiras = to_int(request.form.get("total_prateleiras"))
        capacidade_total = caixas_por_nivel * niveis_por_prateleira * total_prateleiras

        g = Galpao(
            nome=request.form.get("nome"),
            stats=request.form.get("stats"),
            cep=request.form.get("cep"),
            email_resp=email,
            nome_resp=nome_resp,
            endereco=request.form.get("endereco"),
            referencia=request.form.get("referencia"),
            cidade=request.form.get("cidade"),
            estado=request.form.get("estado"),
            area_total=float(area_total),
            telefone=telefone,
            total_prateleiras=total_prateleiras,
            niveis_por_prateleira=niveis_por_prateleira,
            caixas_por_nivel=caixas_por_nivel,
            capacidade_total=capacidade_total
        )
        g.insert()
        flash("Galpão cadastrado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("galpao"))

# ---------------- FORNECEDORES ---------------- #

@app.route("/fornecedores")
@login_obrigatorio
def fornecedores():
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        # Removido o WHERE ativo = 'ativo' — agora traz todos
        cursor.execute("""
            SELECT
                f.id,
                f.nome,
                f.nome_ctt,
                f.email,
                f.telefone,
                f.ativo,
                f.cnpj,
                COUNT(fp.produto_id) AS total_produtos

            FROM fornecedor f

            LEFT JOIN fornecedor_produto fp
                ON fp.fornecedor_id = f.id

            GROUP BY
                f.id,
                f.nome,
                f.nome_ctt,
                f.email,
                f.telefone,
                f.ativo,
                f.cnpj

            ORDER BY f.nome ASC
        """)

        lista_fornecedores = cursor.fetchall()
        

        cursor.execute("SELECT id, nome, sku FROM produto ORDER BY nome ASC")
        lista_produtos = cursor.fetchall()

        cursor.execute("""
            SELECT
                fp.produto_id,
                fp.fornecedor_id,
                p.nome AS produto_nome,
                p.sku,
                f.nome AS fornecedor_nome,
                fp.preco_custo,
                fp.desconto,
                fp.quantidade_minima,
                fp.prazo_entrega_dias,
                fp.ativo
            FROM fornecedor_produto fp
            JOIN produto p ON fp.produto_id = p.id
            JOIN fornecedor f ON fp.fornecedor_id = f.id
            ORDER BY f.nome ASC, p.nome ASC
        """)
        fornecedores_produtos = cursor.fetchall()

    finally:
        cursor.close()
        conexao.close()

    return render_template(
        "fornecedores.html",
        fornecedores=lista_fornecedores,
        lista_fornecedores=lista_fornecedores,
        lista_produtos=lista_produtos,
        fornecedores_produtos=fornecedores_produtos
    )


@app.route("/fornecedor/novo")
@login_obrigatorio
def novo_fornecedor():
    return render_template("form_fornecedor.html")


@app.route("/fornecedor/salvar", methods=["POST"])
@login_obrigatorio
def salvar_fornecedor():
    try:
        fornecedor = Fornecedor(
            nome=request.form.get("nome"),
            ativo=request.form.get("ativo"),
            cnpj=request.form.get("cnpj"),
            nome_ctt=request.form.get("nome_ctt"),
            telefone=request.form.get("telefone"),
            email=request.form.get("email")
        )
        fornecedor.insert()
        flash("Fornecedor cadastrado!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("fornecedores"))


@app.route("/fornecedor/atualizar/<int:fornecedor_id>", methods=["POST"])
@login_obrigatorio
def atualizar_fornecedor(fornecedor_id):
    try:
        conexao = Database.connect()
        cursor = conexao.cursor()

        cursor.execute("""
            UPDATE fornecedor
            SET nome=%s, cnpj=%s, nome_ctt=%s, email=%s, telefone=%s, ativo=%s
            WHERE id=%s
        """, (
            request.form.get("nome"),
            request.form.get("cnpj"),
            request.form.get("nome_ctt"),
            request.form.get("email"),
            request.form.get("telefone"),
            request.form.get("ativo"),
            fornecedor_id
        ))

        conexao.commit()

        # Troca da imagem do fornecedor, quando enviada
        atualizar_imagem("fornecedor", fornecedor_id,
                         request.files.get("imagem"), "fornecedor")

        flash("Fornecedor atualizado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))


@app.route("/fornecedor/deletar/<int:fornecedor_id>", methods=["POST"])
@login_obrigatorio
def deletar_fornecedor(fornecedor_id):
    try:
        conexao = Database.connect()
        cursor = conexao.cursor()

        cursor.execute("DELETE FROM fornecedor WHERE id = %s", (fornecedor_id,))
        conexao.commit()
        flash("Fornecedor removido com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("fornecedores"))


@app.route("/fornecedores/vincular_produto", methods=["POST"])
@login_obrigatorio
def vincular_fornecedor_produto():
    fornecedor_id = to_int(request.form.get("fornecedor_id"))
    produto_id = to_int(request.form.get("produto_id"))
    preco_custo = to_float(request.form.get("preco_custo"))
    desconto = to_float(request.form.get("desconto"))
    quantidade_minima = to_int(request.form.get("quantidade_minima"))
    prazo_entrega_dias = to_int(request.form.get("prazo_entrega_dias"))

    conexao = Database.connect()
    cursor = conexao.cursor()

    try:
        sql = """
            INSERT INTO fornecedor_produto
            (fornecedor_id, produto_id, preco_custo, desconto, quantidade_minima, prazo_entrega_dias, ativo)
            VALUES (%s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                preco_custo = VALUES(preco_custo),
                desconto = VALUES(desconto),
                quantidade_minima = VALUES(quantidade_minima),
                prazo_entrega_dias = VALUES(prazo_entrega_dias),
                ativo = 1
        """
        cursor.execute(sql, (fornecedor_id, produto_id, preco_custo, desconto, quantidade_minima, prazo_entrega_dias))
        conexao.commit()
        flash("Produto associado ao fornecedor com sucesso!", "sucesso")
    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao salvar vínculo comercial: {e}", "erro")
    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("fornecedores"))

# ---------------- INFO FORNECEDOR ---------------- #
@app.route("/info_fornecedor/<int:fornecedor_id>")
@login_obrigatorio
def info_fornecedor(fornecedor_id):
    fornecedor = Fornecedor.find_by_id(fornecedor_id)

    if not fornecedor:
        flash("Fornecedor não encontrado.", "erro")
        return redirect(url_for("fornecedores"))

    produtos = Fornecedor.find_produtos(fornecedor_id)
    lista_produtos = Produto.find_all()

    return render_template(
        "info_fornecedor.html",
        fornecedor=fornecedor,
        produtos=produtos,
        lista_produtos=lista_produtos,
        historico=[]   # FIX: evita erro no template enquanto a tabela de log não existe
    )

# ---------------- ITENS FORNECEDOR ---------------- #

@app.route("/itens_fornecedores/<int:fornecedor_id>")
@login_obrigatorio
def itens_fornecedor(fornecedor_id):
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM fornecedor WHERE id = %s", (fornecedor_id,))
        fornecedor = cursor.fetchone()

        if not fornecedor:
            flash("Fornecedor não encontrado.", "erro")
            return redirect(url_for("fornecedores"))

        # Busca os produtos vinculados com todas as colunas que o template precisa
        cursor.execute("""
            SELECT
                p.id            AS produto_id,
                p.nome          AS produto_nome,
                p.sku,
                fp.preco_custo,
                fp.desconto,
                fp.quantidade_minima,
                fp.prazo_entrega_dias,
                fp.ativo,
                f.nome          AS fornecedor_nome
            FROM fornecedor_produto fp
            JOIN produto   p ON p.id  = fp.produto_id
            JOIN fornecedor f ON f.id = fp.fornecedor_id
            WHERE fp.fornecedor_id = %s
            ORDER BY p.nome ASC
        """, (fornecedor_id,))
        fornecedores_produtos = cursor.fetchall()

        return render_template(
            "itens_fornecedores.html",
            fornecedor=fornecedor,
            fornecedores_produtos=fornecedores_produtos
        )
    finally:
        cursor.close()
        conexao.close()


# Rota nova: cria o produto E já vincula ao fornecedor em uma só ação
@app.route("/fornecedor/<int:fornecedor_id>/salvar_item", methods=["POST"])
@login_obrigatorio
def salvar_item_fornecedor(fornecedor_id):
    try:
        produto = Produto(
            sku=request.form.get("sku"),
            nome=request.form.get("nome"),
            descricao=request.form.get("descricao"),
            categoria=request.form.get("categoria"),
            preco_custo=to_float(request.form.get("preco_custo")),
            preco_venda=0.0,
            peso=to_float(request.form.get("peso")),
            volume=to_float(request.form.get("volume")),
            tipo=request.form.get("tipo"),
            codigo_barras=request.form.get("codigo_barras") or None,
        )

        erros = produto.validate()
        if erros:
            for erro in erros:
                flash(erro, "erro")
            return redirect(url_for("itens_fornecedor", fornecedor_id=fornecedor_id))

        produto_id = produto.insert()

        # Salva campos extras que não estão no __init__ padrão
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE produto
                SET unidade_medida = %s, item_por_caixa = %s
                WHERE id = %s
            """, (
                request.form.get("unidade_medida", "un"),
                to_int(request.form.get("item_por_caixa")),
                produto_id
            ))

            # Vincula ao fornecedor
            cursor.execute("""
                INSERT INTO fornecedor_produto
                    (fornecedor_id, produto_id, preco_custo, desconto,
                     quantidade_minima, prazo_entrega_dias, ativo)
                VALUES (%s, %s, %s, 0, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    preco_custo       = VALUES(preco_custo),
                    quantidade_minima = VALUES(quantidade_minima),
                    prazo_entrega_dias = VALUES(prazo_entrega_dias),
                    ativo             = 1
            """, (
                fornecedor_id,
                produto_id,
                to_float(request.form.get("preco_custo")),
                to_int(request.form.get("pedido_minimo")),
                to_int(request.form.get("tempo_entrega")),
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        flash("Produto cadastrado e vinculado ao fornecedor!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("itens_fornecedor", fornecedor_id=fornecedor_id))

# ---------------- CLIENTES ---------------- #

@app.route("/clientes")
@login_obrigatorio
def cliente():

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    sql = """
        SELECT
            c.*,
            COUNT(pc.id) AS total_pedidos,
            COALESCE(SUM(pc.valor_total), 0) AS total_gasto
        FROM cliente c
        LEFT JOIN pedido_cliente pc
            ON pc.cliente_id = c.id
        GROUP BY c.id
        ORDER BY c.empresa
    """

    cursor.execute(sql)
    clientes = cursor.fetchall()

    cursor.close()
    conexao.close()

    return render_template(
        "cliente.html",
        clientes=clientes
    )

@app.route("/cliente/novo")
@login_obrigatorio
def novo_cliente():
    return render_template("cliente.html")

@app.route("/cliente/salvar", methods=["POST"])
@login_obrigatorio
def salvar_cliente():
    try:
        c = Cliente(
            nome=request.form.get("nome"),
            ativo=request.form.get("ativo"),
            cidade=request.form.get("cidade"),
            empresa=request.form.get("empresa"),
            cep=request.form.get("cep"),
            estado=request.form.get("estado"),
            cpf_cnpj=request.form.get("cpf"),
            email=request.form.get("email"),
            telefone=request.form.get("telefone")
        )
        c.insert()
        flash("Cliente cadastrado!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("cliente"))

# ---------------- FUNCIONÁRIOS ---------------- #

@app.route("/funcionario/salvar", methods=["POST"])
@login_obrigatorio
def salvar_funcionario():
    try:
        salario = request.form.get("salario")
        salario = float(salario) if salario else 0.00

        funcionario = Funcionario(
            nome=request.form.get("nome"),
            cpf=request.form.get("cpf"),
            salario=salario,
            data_nascimento=request.form.get("data_nascimento"),
            data_admissao=request.form.get("data_admissao"),
            email=request.form.get("email"),
            telefone=request.form.get("telefone"),
            ativo=request.form.get("ativo"),
            cargo=request.form.get("cargo"),
            galpao_id=request.form.get("galpao_id")
        )
        funcionario.insert()
        flash("Funcionário cadastrado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("info_galpao", galpao_id=request.form.get("galpao_id")))

@app.route("/funcionario/atualizar", methods=["POST"])
@login_obrigatorio
def atualizar_funcionario():
    funcionario_id = to_int(request.form.get("id"))
    galpao_id      = to_int(request.form.get("galpao_id"))
    nome           = request.form.get("nome", "").strip()

    if not funcionario_id or not nome:
        flash("Informe o funcionário e o nome.", "erro")
        return redirect(url_for("info_galpao", galpao_id=galpao_id))

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE funcionario
            SET nome=%s, cpf=%s, salario=%s, email=%s,
                telefone=%s, cargo=%s, ativo=%s
            WHERE id=%s
        """, (
            nome,
            request.form.get("cpf"),
            to_float(request.form.get("salario")),
            request.form.get("email"),
            formatar_telefone(request.form.get("telefone", "").strip()),
            request.form.get("cargo"),
            request.form.get("ativo"),
            funcionario_id
        ))

        conn.commit()
        flash("Funcionário atualizado com sucesso!", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar funcionário: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("info_galpao", galpao_id=galpao_id))

@app.route("/funcionario/deletar/<int:funcionario_id>", methods=["POST"])
@login_obrigatorio
def deletar_funcionario(funcionario_id):
    galpao_id = request.form.get("galpao_id")
    try:
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM funcionario WHERE id = %s", (funcionario_id,))
        conn.commit()
        conn.close()
        flash("Funcionário removido com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao remover funcionário: {e}", "erro")
    return redirect(url_for("info_galpao", galpao_id=galpao_id))

# ---------------- MOVIMENTAÇÕES ---------------- #

@app.route("/movimentacoes")
@login_obrigatorio
def movimentacoes():
    # Os filtros são resolvidos aqui, no servidor, via query string (?produto_id=&galpao_id=&tipo=).
    produto_id = to_int(request.args.get("produto_id")) or None
    galpao_id  = to_int(request.args.get("galpao_id")) or None
    tipo       = (request.args.get("tipo") or "").strip().lower() or None

    return render_template(
        "movimentacoes.html",
        movimentacoes=Movimentacao.find_all_with_product(produto_id, galpao_id, tipo),
        produtos=Produto.find_all(),
        galpoes=Galpao.find_all(),
        tipos=Movimentacao.TIPOS,
        filtro_produto_id=produto_id,
        filtro_galpao_id=galpao_id,
        filtro_tipo=tipo
    )

@app.route("/movimentacao/nova")
@login_obrigatorio
def nova_movimentacao():
    return render_template(
        "form_movimentacao.html",
        produtos=Produto.find_all(),
        galpoes=Galpao.find_all(),
        funcionarios=Funcionario.find_all(),
        tipos=Movimentacao.TIPOS
    )

@app.route("/movimentacao/salvar", methods=["POST"])
@login_obrigatorio
def salvar_movimentacao():
    produto_id        = to_int(request.form.get("produto_id")) or None
    galpao_id         = to_int(request.form.get("galpao_id")) or None
    galpao_destino_id = to_int(request.form.get("galpao_destino_id")) or None
    funcionario_id    = to_int(request.form.get("funcionario_id")) or None
    tipo              = (request.form.get("tipo") or "").strip().lower()
    quantidade        = to_float(request.form.get("quantidade"))
    observacao        = (request.form.get("observacao") or "").strip() or None

    movimentacao = Movimentacao(
        produto_id=produto_id,
        galpao_id=galpao_id,
        tipo=tipo,
        quantidade=quantidade,
        galpao_destino_id=galpao_destino_id,
        funcionario_id=funcionario_id,
        observacao=observacao
    )

    erros = movimentacao.validate()
    if erros:
        for erro in erros:
            flash(erro, "erro")
        return redirect(url_for("nova_movimentacao"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        # Saldo atual na origem
        cursor.execute("""
            SELECT quantidade FROM estoque
            WHERE produto_id = %s AND galpao_id = %s
        """, (produto_id, galpao_id))

        resultado = cursor.fetchone()
        atual = float(resultado[0]) if resultado else 0.0

        if tipo in ("saida", "transferencia") and atual < quantidade:
            raise ValueError(
                f"Estoque insuficiente no galpão de origem (disponível: {atual:g})."
            )

        cursor.execute("""
            INSERT INTO movimentacao
                (produto_id, galpao_id, galpao_destino_id,
                 funcionario_id, tipo, quantidade, observacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (produto_id, galpao_id, galpao_destino_id,
              funcionario_id, tipo, quantidade, observacao))

        if tipo == "entrada":
            delta_origem = quantidade
        elif tipo in ("saida", "transferencia"):
            delta_origem = -quantidade
        else:  # ajuste_inventario define o saldo absoluto
            delta_origem = None

        if delta_origem is None:
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = VALUES(quantidade)
            """, (produto_id, galpao_id, quantidade))
        else:
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
            """, (produto_id, galpao_id, delta_origem))

        # Na transferência o estoque sai da origem e entra no destino
        if tipo == "transferencia":
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
            """, (produto_id, galpao_destino_id, quantidade))

        conexao.commit()
        flash("Movimentação registrada!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao registrar movimentação: {mensagem_erro(e)}", "erro")
        return redirect(url_for("nova_movimentacao"))

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("movimentacoes"))

# ---------------- INFO CLIENTES ---------------- #

@app.route("/info_cliente/<int:cliente_id>")
@login_obrigatorio
def info_cliente(cliente_id):
    c = Cliente.find_by_id(cliente_id)
    if not c:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("cliente"))
    pedidos = PedidoCliente.find_by_cliente(cliente_id)
    return render_template("info_cliente.html", cliente=c, pedidos=pedidos)


@app.route("/cliente/atualizar/<int:cliente_id>", methods=["POST"])
@login_obrigatorio
def atualizar_cliente(cliente_id):
    try:
        dados = {
            "nome":     request.form.get("nome"),
            "ativo":   request.form.get("ativo"),
            "empresa":  request.form.get("empresa"),
            "email":    request.form.get("email"),
            "telefone": request.form.get("telefone"),
            "cep":      request.form.get("cep"),
            "cidade":   request.form.get("cidade"),
            "estado":   request.form.get("estado"),
        }
        Cliente.update(cliente_id, dados)
        flash("Cliente atualizado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("info_cliente", cliente_id=cliente_id))


@app.route("/cliente/deletar/<int:cliente_id>", methods=["POST"])
@login_obrigatorio
def deletar_cliente(cliente_id):
    try:
        Cliente.delete(cliente_id)
        flash("Cliente excluído com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("cliente"))


# ------------------------------------------------------------------ #
# API — produtos disponíveis por galpão                               #
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# CONSULTAS DE PEDIDOS                                                #
# ------------------------------------------------------------------ #

def buscar_pedidos_entrada(busca=""):
    """Pedidos de fornecedor, opcionalmente filtrados por fornecedor/documento."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = """
            SELECT pf.*, f.nome AS fornecedor_nome, g.nome AS galpao_nome
            FROM pedido_fornecedor pf
            LEFT JOIN fornecedor f ON pf.fornecedor_id = f.id
            LEFT JOIN galpao     g ON pf.galpao_id     = g.id
        """
        valores = ()

        if busca:
            sql += " WHERE f.nome LIKE %s OR pf.numero_documento LIKE %s"
            valores = (f"%{busca}%", f"%{busca}%")

        sql += " ORDER BY pf.id DESC"

        cursor.execute(sql, valores)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def buscar_pedidos_saida(busca=""):
    """Pedidos de cliente, opcionalmente filtrados por cliente/documento."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = """
            SELECT pc.*, c.nome AS cliente_nome, g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c ON pc.cliente_id = c.id
            LEFT JOIN galpao  g ON pc.galpao_id  = g.id
        """
        valores = ()

        if busca:
            sql += " WHERE c.nome LIKE %s OR pc.numero_documento LIKE %s"
            valores = (f"%{busca}%", f"%{busca}%")

        sql += " ORDER BY pc.id DESC"

        cursor.execute(sql, valores)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ------------------------------------------------------------------ #
# CARRINHO DE PEDIDOS (mantido na sessão, sem JavaScript)             #
# ------------------------------------------------------------------ #
# Antes os itens do pedido eram montados no navegador e enviados em um
# campo escondido "itens_json". Agora cada item é adicionado por um POST
# normal, guardado na sessão do Flask e renderizado direto no template.

def carrinho_obter(chave):
    return session.get(chave, [])


def carrinho_salvar(chave, itens):
    session[chave] = itens
    session.modified = True


def carrinho_limpar(chave):
    session.pop(chave, None)
    session.modified = True


def carrinho_total(itens):
    return sum(item["quantidade"] * item["preco_unitario"] for item in itens)


def carrinho_adicionar(chave, produto, quantidade, preco_unitario):
    """Adiciona (ou soma, se já existir) um produto ao carrinho da sessão."""
    itens = carrinho_obter(chave)

    for item in itens:
        if item["produto_id"] == produto["id"]:
            item["quantidade"] += quantidade
            item["preco_unitario"] = preco_unitario
            break
    else:
        itens.append({
            "produto_id":     produto["id"],
            "sku":            produto.get("sku") or "—",
            "nome":           produto.get("nome") or "",
            "quantidade":     quantidade,
            "preco_unitario": preco_unitario,
        })

    carrinho_salvar(chave, itens)


def carrinho_remover(chave, indice):
    itens = carrinho_obter(chave)

    if 0 <= indice < len(itens):
        itens.pop(indice)
        carrinho_salvar(chave, itens)


def produtos_por_galpao():
    """Todos os produtos com saldo, com o galpão a que pertencem.

    A tela recebe a lista inteira e mostra só os do galpão escolhido, então
    trocar de galpão não precisa recarregar a página.
    """
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                e.galpao_id,
                p.id,
                p.sku,
                p.nome,
                COALESCE(p.preco_venda, 0) AS preco_venda,
                COALESCE(e.quantidade, 0)  AS estoque_disponivel
            FROM estoque e
            INNER JOIN produto p ON e.produto_id = p.id
            WHERE e.quantidade > 0 AND p.ativo = TRUE
            ORDER BY p.nome
        """)
        produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_venda"] = to_float(produto["preco_venda"])
            produto["estoque_disponivel"] = to_float(produto["estoque_disponivel"])

        return produtos
    finally:
        cursor.close()
        conn.close()


def produtos_por_fornecedor():
    """Produtos ativos com os fornecedores a que estão vinculados.

    `fornecedor_id` vazio marca os produtos sem vínculo, que continuam
    disponíveis para qualquer fornecedor (mesma regra do fallback anterior).
    """
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                fp.fornecedor_id,
                p.id,
                p.sku,
                p.nome,
                COALESCE(fp.preco_custo, p.preco_custo, 0) AS preco_custo
            FROM produto p
            LEFT JOIN fornecedor_produto fp
                   ON fp.produto_id = p.id AND fp.ativo = 1
            WHERE p.ativo = TRUE
            ORDER BY p.nome
        """)
        produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_custo"] = to_float(produto["preco_custo"])

        return produtos
    finally:
        cursor.close()
        conn.close()


def produtos_do_fornecedor(fornecedor_id):
    """Produtos vinculados ao fornecedor (ou todos os ativos, se não houver vínculo)."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT p.id, p.sku, p.nome, fp.preco_custo
            FROM fornecedor_produto fp
            JOIN produto p ON fp.produto_id = p.id
            WHERE fp.fornecedor_id = %s AND fp.ativo = 1 AND p.ativo = TRUE
            ORDER BY p.nome
        """, (fornecedor_id,))
        produtos = cursor.fetchall()

        if not produtos:
            cursor.execute("""
                SELECT p.id, p.sku, p.nome, p.preco_custo
                FROM produto p
                WHERE p.ativo = TRUE
                ORDER BY p.nome
            """)
            produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_custo"] = to_float(produto["preco_custo"])

        return produtos
    finally:
        cursor.close()
        conn.close()


def produtos_do_galpao(galpao_id):
    """Produtos com saldo disponível no galpão informado."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                p.id,
                p.sku,
                p.nome,
                COALESCE(p.preco_venda, 0)  AS preco_venda,
                COALESCE(e.quantidade, 0)   AS estoque_disponivel
            FROM estoque e
            INNER JOIN produto p ON e.produto_id = p.id
            WHERE e.galpao_id = %s AND e.quantidade > 0 AND p.ativo = TRUE
            ORDER BY p.nome
        """, (galpao_id,))
        produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_venda"] = to_float(produto["preco_venda"])
            produto["estoque_disponivel"] = to_float(produto["estoque_disponivel"])

        return produtos
    finally:
        cursor.close()
        conn.close()


# ------------------------------------------------------------------ #
# PEDIDOS DE ENTRADA  (usa tabela: pedido_fornecedor)                 #
# ------------------------------------------------------------------ #

CARRINHO_ENTRADA = "carrinho_entrada"


@app.route("/cadastro_pedido_entrada")
@login_obrigatorio
def cadastro_pedido_entrada():
    # O fornecedor escolhido volta pela query string, então a lista de
    # produtos é montada aqui no servidor — sem chamada AJAX.
    fornecedor_id = to_int(request.args.get("fornecedor_id")) or None
    galpao_id     = to_int(request.args.get("galpao_id")) or None
    produto_id    = to_int(request.args.get("produto_id")) or None
    itens         = carrinho_obter(CARRINHO_ENTRADA)
    # A lista completa vai para a tela, que mostra só os produtos do
    # fornecedor escolhido. Sem recarregar a página para trocar de fornecedor.
    produtos = produtos_por_fornecedor()

    return render_template(
        "pedidos_fornecedor.html",
        galpoes=Galpao.find_all(),
        fornecedores=Fornecedor.find_all(),
        produtos=produtos,
        fornecedor_id=fornecedor_id,
        galpao_id=galpao_id,
        produto_id=produto_id,
        itens=itens,
        total=carrinho_total(itens)
    )


@app.route("/pedido_entrada/item/adicionar", methods=["POST"])
@login_obrigatorio
def adicionar_item_entrada():
    fornecedor_id = to_int(request.form.get("fornecedor_id")) or None
    galpao_id     = to_int(request.form.get("galpao_id")) or None
    produto_id    = to_int(request.form.get("produto_id"))
    quantidade    = to_float(request.form.get("quantidade"))
    preco         = to_float(request.form.get("preco_unitario"))

    destino = url_for("cadastro_pedido_entrada",
                      fornecedor_id=fornecedor_id, galpao_id=galpao_id)

    if not fornecedor_id:
        flash("Selecione o fornecedor antes de adicionar produtos.", "erro")
        return redirect(destino)

    if not produto_id:
        flash("Selecione o produto.", "erro")
        return redirect(destino)

    if quantidade <= 0:
        flash("A quantidade deve ser maior que zero.", "erro")
        return redirect(destino)

    produto = Produto.find_by_id(produto_id)
    if not produto:
        flash("Produto não encontrado.", "erro")
        return redirect(destino)

    carrinho_adicionar(CARRINHO_ENTRADA, produto, quantidade, preco)
    flash(f"{produto['nome']} adicionado ao pedido.", "sucesso")
    return redirect(destino)


@app.route("/pedido_entrada/item/remover/<int:indice>", methods=["POST"])
@login_obrigatorio
def remover_item_entrada(indice):
    carrinho_remover(CARRINHO_ENTRADA, indice)
    return redirect(url_for(
        "cadastro_pedido_entrada",
        fornecedor_id=to_int(request.form.get("fornecedor_id")) or None,
        galpao_id=to_int(request.form.get("galpao_id")) or None
    ))


@app.route("/pedido_entrada/limpar", methods=["POST"])
@login_obrigatorio
def limpar_pedido_entrada():
    carrinho_limpar(CARRINHO_ENTRADA)
    flash("Itens do pedido removidos.", "sucesso")
    return redirect(url_for("cadastro_pedido_entrada"))


@app.route("/pedidos_entrada")
@login_obrigatorio
def listar_pedidos_entrada():
    return redirect(url_for("pedidos", busca=request.args.get("busca") or None))


# Mantida por compatibilidade: os redirecionamentos antigos apontavam para cá.
@app.route("/pedidos_entrada/novo")
@login_obrigatorio
def novo_pedido_entrada():
    return redirect(url_for("cadastro_pedido_entrada"))


@app.route("/salvar_pedido_entrada", methods=["POST"])
@login_obrigatorio
def salvar_pedido_entrada():
    fornecedor_id    = to_int(request.form.get("fornecedor_id")) or None
    galpao_id        = to_int(request.form.get("galpao_id")) or None
    numero_documento = (request.form.get("numero_documento") or "").strip() or None
    data_prevista    = (request.form.get("data_entrada") or "").strip() or None
    observacao       = (request.form.get("observacao") or "").strip() or None

    itens = carrinho_obter(CARRINHO_ENTRADA)

    destino = url_for("cadastro_pedido_entrada",
                      fornecedor_id=fornecedor_id, galpao_id=galpao_id)

    if not fornecedor_id or not galpao_id:
        flash("Selecione o fornecedor e o galpão de destino.", "erro")
        return redirect(destino)

    if not itens:
        flash("Adicione pelo menos um item ao pedido.", "erro")
        return redirect(destino)

    valor_total = carrinho_total(itens)

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO pedido_fornecedor
                (fornecedor_id, galpao_id, numero_documento,
                 data_prevista, observacao, status, valor_total)
            VALUES (%s, %s, %s, %s, %s, 'recebido', %s)
        """, (fornecedor_id, galpao_id, numero_documento,
              data_prevista, observacao, valor_total))
        pedido_id = cursor.lastrowid

        for item in itens:
            cursor.execute("""
                INSERT INTO item_pedido_fornecedor
                    (pedido_fornecedor_id, produto_id, quantidade, preco_unitario)
                VALUES (%s, %s, %s, %s)
            """, (pedido_id, item["produto_id"],
                  item["quantidade"], item["preco_unitario"]))

            # AUTO-VÍNCULO: associa o produto ao fornecedor, se ainda não estiver
            cursor.execute("""
                INSERT INTO fornecedor_produto
                    (fornecedor_id, produto_id, preco_custo, desconto,
                     quantidade_minima, prazo_entrega_dias, ativo)
                VALUES (%s, %s, %s, 0, 1, 0, 1)
                ON DUPLICATE KEY UPDATE
                    preco_custo = VALUES(preco_custo),
                    ativo = 1
            """, (fornecedor_id, item["produto_id"], item["preco_unitario"]))

            # Entrada de estoque no galpão de destino
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
            """, (item["produto_id"], galpao_id, item["quantidade"]))

            # Registra a movimentação correspondente
            cursor.execute("""
                INSERT INTO movimentacao
                    (produto_id, galpao_id, tipo, quantidade, observacao)
                VALUES (%s, %s, 'entrada', %s, %s)
            """, (item["produto_id"], galpao_id, item["quantidade"],
                  f"Pedido de entrada #{pedido_id}"))

        conn.commit()
        carrinho_limpar(CARRINHO_ENTRADA)
        flash("Pedido de entrada cadastrado com sucesso!", "sucesso")
        return redirect(url_for("visualizar_pedido_entrada", pedido_id=pedido_id))

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao cadastrar pedido de entrada: {mensagem_erro(e)}", "erro")
        return redirect(destino)
    finally:
        cursor.close()
        conn.close()


@app.route("/pedidos_entrada/visualizar/<int:pedido_id>")
@login_obrigatorio
def visualizar_pedido_entrada(pedido_id):
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pf.*, f.nome AS fornecedor_nome, g.nome AS galpao_nome
            FROM pedido_fornecedor pf
            LEFT JOIN fornecedor f ON pf.fornecedor_id = f.id
            LEFT JOIN galpao     g ON pf.galpao_id     = g.id
            WHERE pf.id = %s
        """, (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("listar_pedidos_entrada"))

        cursor.execute("""
            SELECT ipf.*, p.nome AS produto_nome, p.sku
            FROM item_pedido_fornecedor ipf
            JOIN produto p ON ipf.produto_id = p.id
            WHERE ipf.pedido_fornecedor_id = %s
        """, (pedido_id,))
        pedido["itens"] = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template("pedidos_entrada/visualizar.html", pedido=pedido)


# ------------------------------------------------------------------ #
# PEDIDOS DE SAÍDA  (usa tabela: pedido_cliente)                      #
# ------------------------------------------------------------------ #

CARRINHO_SAIDA = "carrinho_saida"


@app.route("/cadastro_pedido/<int:cliente_id>")
@login_obrigatorio
def cadastro_pedido(cliente_id):
    cliente = Cliente.find_by_id(cliente_id)

    if not cliente:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("cliente"))

    # Assim como na entrada, o galpão volta pela query string e os produtos
    # disponíveis são carregados aqui no servidor.
    galpao_id  = to_int(request.args.get("galpao_id")) or None
    produto_id = to_int(request.args.get("produto_id")) or None
    itens      = carrinho_obter(CARRINHO_SAIDA)
    # Lista completa; a tela filtra pelo galpão escolhido
    produtos = produtos_por_galpao()

    return render_template(
        "cadastro_pedidos.html",
        cliente=cliente,
        clientes=Cliente.find_all(),
        galpoes=Galpao.find_all(),
        produtos=produtos,
        galpao_id=galpao_id,
        produto_id=produto_id,
        itens=itens,
        total=carrinho_total(itens)
    )


@app.route("/cadastro_pedido_saida")
@login_obrigatorio
def cadastro_pedido_saida():
    # Sem cliente definido: mostra a tela com o seletor de clientes.
    galpao_id  = to_int(request.args.get("galpao_id")) or None
    produto_id = to_int(request.args.get("produto_id")) or None
    itens      = carrinho_obter(CARRINHO_SAIDA)
    produtos = produtos_por_galpao()

    return render_template(
        "cadastro_pedidos.html",
        cliente=None,
        clientes=Cliente.find_all(),
        galpoes=Galpao.find_all(),
        produtos=produtos,
        galpao_id=galpao_id,
        produto_id=produto_id,
        itens=itens,
        total=carrinho_total(itens)
    )


def destino_pedido_saida(cliente_id, galpao_id):
    if cliente_id:
        return url_for("cadastro_pedido", cliente_id=cliente_id, galpao_id=galpao_id)
    return url_for("cadastro_pedido_saida", galpao_id=galpao_id)


@app.route("/pedido_saida/item/adicionar", methods=["POST"])
@login_obrigatorio
def adicionar_item_saida():
    cliente_id = to_int(request.form.get("cliente_id")) or None
    galpao_id  = to_int(request.form.get("galpao_id")) or None
    produto_id = to_int(request.form.get("produto_id"))
    quantidade = to_float(request.form.get("quantidade"))

    destino = destino_pedido_saida(cliente_id, galpao_id)

    if not galpao_id:
        flash("Selecione o galpão de retirada antes de adicionar produtos.", "erro")
        return redirect(destino)

    if not produto_id:
        flash("Selecione o produto.", "erro")
        return redirect(destino)

    if quantidade <= 0:
        flash("A quantidade deve ser maior que zero.", "erro")
        return redirect(destino)

    # O preço e a disponibilidade vêm do banco, não do formulário.
    disponiveis = {p["id"]: p for p in produtos_do_galpao(galpao_id)}
    produto = disponiveis.get(produto_id)

    if not produto:
        flash("Este produto não está disponível no galpão selecionado.", "erro")
        return redirect(destino)

    ja_no_carrinho = sum(
        item["quantidade"] for item in carrinho_obter(CARRINHO_SAIDA)
        if item["produto_id"] == produto_id
    )

    if ja_no_carrinho + quantidade > produto["estoque_disponivel"]:
        flash(
            f"Estoque insuficiente para {produto['nome']} "
            f"(disponível: {produto['estoque_disponivel']:g}).",
            "erro"
        )
        return redirect(destino)

    carrinho_adicionar(CARRINHO_SAIDA, produto, quantidade, produto["preco_venda"])
    flash(f"{produto['nome']} adicionado ao pedido.", "sucesso")
    return redirect(destino)


@app.route("/pedido_saida/item/remover/<int:indice>", methods=["POST"])
@login_obrigatorio
def remover_item_saida(indice):
    carrinho_remover(CARRINHO_SAIDA, indice)
    return redirect(destino_pedido_saida(
        to_int(request.form.get("cliente_id")) or None,
        to_int(request.form.get("galpao_id")) or None
    ))


@app.route("/pedido_saida/limpar", methods=["POST"])
@login_obrigatorio
def limpar_pedido_saida():
    carrinho_limpar(CARRINHO_SAIDA)
    flash("Itens do pedido removidos.", "sucesso")
    return redirect(destino_pedido_saida(
        to_int(request.form.get("cliente_id")) or None, None
    ))


@app.route("/pedidos_saida")
@login_obrigatorio
def listar_pedidos_saida():
    # Cada pedido de saída pertence a um cliente, então a consulta começa
    # pela lista de clientes em vez de uma listagem geral.
    flash("Escolha o cliente para ver os pedidos de saída.", "sucesso")
    return redirect(url_for("cliente"))


@app.route("/salvar_pedido_saida", methods=["POST"])
@login_obrigatorio
def salvar_pedido_saida():
    cliente_id       = to_int(request.form.get("cliente_id")) or None
    galpao_id        = to_int(request.form.get("galpao_id")) or None
    numero_documento = (request.form.get("numero_documento") or "").strip() or None
    data_saida       = (request.form.get("data_saida") or "").strip() or None
    observacao       = (request.form.get("observacao") or "").strip() or None

    itens = carrinho_obter(CARRINHO_SAIDA)

    destino = destino_pedido_saida(cliente_id, galpao_id)

    if not cliente_id:
        flash("Selecione o cliente do pedido.", "erro")
        return redirect(destino)

    if not galpao_id:
        flash("Selecione o galpão de retirada.", "erro")
        return redirect(destino)

    if not itens:
        flash("Adicione pelo menos um item ao pedido.", "erro")
        return redirect(destino)

    valor_total = carrinho_total(itens)

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        # Sem data informada o banco usa a data/hora atual (DEFAULT do campo)
        if data_saida:
            cursor.execute("""
                INSERT INTO pedido_cliente
                    (cliente_id, galpao_id, numero_documento,
                     observacao, valor_total, status_pedido, data_pedido)
                VALUES (%s, %s, %s, %s, %s, 'pendente', %s)
            """, (cliente_id, galpao_id, numero_documento, observacao,
                  valor_total, data_saida))
        else:
            cursor.execute("""
                INSERT INTO pedido_cliente
                    (cliente_id, galpao_id, numero_documento,
                     observacao, valor_total, status_pedido)
                VALUES (%s, %s, %s, %s, %s, 'pendente')
            """, (cliente_id, galpao_id, numero_documento, observacao, valor_total))
        pedido_id = cursor.lastrowid

        for item in itens:
            # Confere o saldo dentro da transação, para não deixar estoque negativo
            cursor.execute("""
                SELECT quantidade FROM estoque
                WHERE produto_id = %s AND galpao_id = %s
            """, (item["produto_id"], galpao_id))

            saldo = cursor.fetchone()
            disponivel = float(saldo[0]) if saldo else 0.0

            if disponivel < item["quantidade"]:
                raise ValueError(
                    f"Estoque insuficiente para {item['nome']} "
                    f"(disponível: {disponivel:g})."
                )

            cursor.execute("""
                INSERT INTO item_pedido_cliente
                    (pedido_cliente_id, produto_id, quantidade, preco_unitario_no_momento)
                VALUES (%s, %s, %s, %s)
            """, (pedido_id, item["produto_id"],
                  item["quantidade"], item["preco_unitario"]))

            cursor.execute("""
                UPDATE estoque SET quantidade = quantidade - %s
                WHERE produto_id = %s AND galpao_id = %s
            """, (item["quantidade"], item["produto_id"], galpao_id))

            cursor.execute("""
                INSERT INTO movimentacao
                    (produto_id, galpao_id, tipo, quantidade, observacao)
                VALUES (%s, %s, 'saida', %s, %s)
            """, (item["produto_id"], galpao_id, item["quantidade"],
                  f"Pedido de saída #{pedido_id}"))

        conn.commit()
        carrinho_limpar(CARRINHO_SAIDA)
        flash("Pedido de saída cadastrado com sucesso!", "sucesso")
        return redirect(url_for("visualizar_pedido_saida", pedido_id=pedido_id))

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao cadastrar pedido de saída: {mensagem_erro(e)}", "erro")
        return redirect(destino)
    finally:
        cursor.close()
        conn.close()


@app.route("/pedidos_saida/visualizar/<int:pedido_id>")
@login_obrigatorio
def visualizar_pedido_saida(pedido_id):
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pc.*, c.nome AS cliente_nome, g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c ON pc.cliente_id = c.id
            LEFT JOIN galpao  g ON pc.galpao_id  = g.id
            WHERE pc.id = %s
        """, (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("listar_pedidos_saida"))

        cursor.execute("""
            SELECT ipc.*, p.nome AS produto_nome, p.sku
            FROM item_pedido_cliente ipc
            JOIN produto p ON ipc.produto_id = p.id
            WHERE ipc.pedido_cliente_id = %s
        """, (pedido_id,))
        pedido["itens"] = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template("pedidos_saida/visualizar.html", pedido=pedido)

@app.route("/editar_pedido/<int:id>")
@login_obrigatorio
def editar_pedido(id):
    # A edição de um pedido já recebido mexeria no saldo de estoque, então
    # a tela é somente leitura: mostra o pedido e seus itens.
    return redirect(url_for("visualizar_pedido_entrada", pedido_id=id))

@app.route("/deletar_pedido/<int:id>", methods=["POST"])
@login_obrigatorio
def deletar_pedido(id):
    """Exclui um pedido de ENTRADA (fornecedor) e desfaz a entrada de estoque."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT galpao_id FROM pedido_fornecedor WHERE id = %s", (id,))
        pedido = cursor.fetchone()

        if not pedido:
            raise ValueError("Pedido de entrada não encontrado.")

        # Devolve o estoque que este pedido havia somado ao galpão
        cursor.execute("""
            SELECT produto_id, quantidade
            FROM item_pedido_fornecedor
            WHERE pedido_fornecedor_id = %s
        """, (id,))

        for item in cursor.fetchall():
            cursor.execute("""
                UPDATE estoque SET quantidade = quantidade - %s
                WHERE produto_id = %s AND galpao_id = %s
            """, (item["quantidade"], item["produto_id"], pedido["galpao_id"]))

        cursor.execute(
            "DELETE FROM item_pedido_fornecedor WHERE pedido_fornecedor_id = %s", (id,)
        )
        cursor.execute("DELETE FROM pedido_fornecedor WHERE id = %s", (id,))

        conn.commit()
        flash("Pedido de entrada excluído e estoque ajustado.", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pedido: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("listar_pedidos_entrada"))


@app.route("/deletar_pedido_saida/<int:id>", methods=["POST"])
@login_obrigatorio
def deletar_pedido_saida(id):
    """Exclui um pedido de SAÍDA (cliente) e devolve o estoque ao galpão.

    Antes a tela de pedidos do cliente chamava "deletar_pedido", que apaga
    pedidos de fornecedor — ou seja, excluía o registro errado.
    """
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT cliente_id, galpao_id, status_pedido FROM pedido_cliente WHERE id = %s",
            (id,)
        )
        pedido = cursor.fetchone()

        if not pedido:
            raise ValueError("Pedido de saída não encontrado.")

        # Um pedido cancelado já teve o estoque devolvido
        if pedido["status_pedido"] != "cancelado":
            cursor.execute("""
                SELECT produto_id, quantidade
                FROM item_pedido_cliente
                WHERE pedido_cliente_id = %s
            """, (id,))

            for item in cursor.fetchall():
                cursor.execute("""
                    UPDATE estoque SET quantidade = quantidade + %s
                    WHERE produto_id = %s AND galpao_id = %s
                """, (item["quantidade"], item["produto_id"], pedido["galpao_id"]))

        cliente_id = pedido["cliente_id"]

        cursor.execute(
            "DELETE FROM item_pedido_cliente WHERE pedido_cliente_id = %s", (id,)
        )
        cursor.execute("DELETE FROM pedido_cliente WHERE id = %s", (id,))

        conn.commit()
        flash("Pedido de saída excluído e estoque ajustado.", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pedido: {mensagem_erro(e)}", "erro")
        return redirect(url_for("listar_pedidos_saida"))

    finally:
        cursor.close()
        conn.close()

    if cliente_id:
        return redirect(url_for("pedidos_clientes", cliente_id=cliente_id))
    return redirect(url_for("listar_pedidos_saida"))


# ---------------- PEDIDOS CLIENTES ---------------- #

@app.route("/pedidos_cliente/<int:cliente_id>")
@login_obrigatorio
def pedidos_clientes(cliente_id):
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM cliente WHERE id = %s", (cliente_id,))
        c = cursor.fetchone()

        if not c:
            flash("Cliente não encontrado.", "erro")
            return redirect(url_for("cliente"))

        busca = (request.args.get("busca") or "").strip()

        sql = """
            SELECT pc.*, c.nome AS cliente_nome, c.email AS cliente_email
            FROM pedido_cliente pc
            JOIN cliente c ON pc.cliente_id = c.id
            WHERE pc.cliente_id = %s
        """
        valores = [cliente_id]

        if busca:
            sql += " AND pc.numero_documento LIKE %s"
            valores.append(f"%{busca}%")

        sql += " ORDER BY pc.data_pedido DESC"

        cursor.execute(sql, tuple(valores))
        pedidos = cursor.fetchall()

        return render_template(
            "pedidos_cliente.html",
            cliente=c,
            pedidos=pedidos,
            galpoes=Galpao.find_all(),
            produtos=Produto.find_all(),
            busca=busca
        )
    except Exception as e:
        app.logger.exception("Falha ao carregar pedidos do cliente")
        flash(f"Erro ao carregar pedidos do cliente: {e}", "erro")
        return redirect(url_for("cliente"))
    finally:
        cursor.close()
        conexao.close()
        
# ---------------- INFO PEDIDOS ------------#

@app.route("/pedido-cliente/<int:pedido_id>")
@login_obrigatorio
def info_pedido_cliente(pedido_id):

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        # Dados do pedido
        sql = """
            SELECT
                pc.*,
                c.nome AS cliente_nome,
                c.email AS cliente_email,
                c.telefone AS cliente_telefone,
                c.cidade,
                c.estado,
                g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c
                ON pc.cliente_id = c.id
            LEFT JOIN galpao g
                ON pc.galpao_id = g.id
            WHERE pc.id = %s
        """

        cursor.execute(sql, (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("cliente"))

        # Itens do pedido
        sql_itens = """
            SELECT
                ipc.*,
                p.nome,
                p.sku,
                p.codigo_barras
            FROM item_pedido_cliente ipc
            INNER JOIN produto p
                ON ipc.produto_id = p.id
            WHERE ipc.pedido_cliente_id = %s
        """

        cursor.execute(sql_itens, (pedido_id,))
        itens = cursor.fetchall()

        return render_template(
            "info_pedido_cliente.html",
            pedido=pedido,
            itens=itens
        )

    except Exception as e:
        flash(f"Erro ao carregar pedido: {mensagem_erro(e)}", "erro")
        return redirect(url_for("cliente"))

    finally:
        cursor.close()
        conexao.close()
# ---------------- PEDIDOS ---------------- #

@app.route("/pedidos")
@login_obrigatorio
def pedidos():
    """Pedidos de entrada (compras de fornecedor).

    As saídas não aparecem aqui: elas pertencem ao cliente e ficam em
    /pedidos_cliente/<cliente_id>.
    """
    busca = (request.args.get("busca") or "").strip()

    return render_template(
        "pedidos.html",
        pedidos=buscar_pedidos_entrada(busca),
        busca=busca
    )

@app.route("/pedido/processar/<int:id>", methods=["POST"])
@login_obrigatorio
def processar_pedido(id):
    # Conclui um pedido de saída pendente. A baixa de estoque já ocorreu no
    # fechamento do pedido, então aqui só o status muda.
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT status_pedido FROM pedido_cliente WHERE id = %s", (id,))
        pedido = cursor.fetchone()

        if not pedido:
            raise ValueError("Pedido não encontrado.")

        if pedido["status_pedido"] != "pendente":
            raise ValueError("Só é possível processar pedidos pendentes.")

        cursor.execute("""
            UPDATE pedido_cliente
            SET status_pedido = 'concluido'
            WHERE id = %s
        """, (id,))

        conn.commit()
        flash("Pedido processado com sucesso!", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao processar pedido: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("pedidos"))

@app.route("/pedido/cancelar/<int:id>", methods=["POST"])
@login_obrigatorio
def cancelar_pedido(id):
    # PedidoCliente.cancelar devolve o estoque e marca o pedido como cancelado.
    try:
        PedidoCliente.cancelar(id)
        flash("Pedido cancelado e estoque devolvido.", "sucesso")
    except Exception as e:
        flash(f"Erro ao cancelar pedido: {mensagem_erro(e)}", "erro")
    return redirect(url_for("pedidos"))

# ---------------- ERRO 404 ---------------- #

@app.errorhandler(404)
def pagina_nao_encontrada(error):
    return render_template("404.html"), 404

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    # Ative o modo debug apenas em desenvolvimento: FLASK_DEBUG=1 python app.py
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")