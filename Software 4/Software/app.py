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
app.secret_key = "chave_secreta"

@app.context_processor
def dados_globais():
    empresa_nome = ""

    if "empresa_id" in session:
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT nome
                FROM empresa
                WHERE id = %s
            """, (session["empresa_id"],))

            empresa = cursor.fetchone()

            if empresa:
                empresa_nome = empresa["nome"]

        finally:
            cursor.close()
            conexao.close()

    return {
        "empresa_nome": empresa_nome
    }

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

# ------------VALIDAÇÃO CNPJ----------#

def validar_cnpj(cnpj):
    # Remove pontos, barras, traços e qualquer outro caractere
    cnpj = re.sub(r"\D", "", cnpj)

    # CNPJ precisa ter exatamente 14 números
    if len(cnpj) != 14:
        return False

    # Não aceita CNPJ com todos os números iguais
    if len(set(cnpj)) == 1:
        return False

    # Primeiro dígito verificador
    pesos_1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    soma = sum(
        int(cnpj[i]) * pesos_1[i]
        for i in range(12)
    )

    resto = soma % 11

    if resto < 2:
        digito_1 = 0
    else:
        digito_1 = 11 - resto

    if int(cnpj[12]) != digito_1:
        return False

    # Segundo dígito verificador
    pesos_2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    soma = sum(
        int(cnpj[i]) * pesos_2[i]
        for i in range(13)
    )

    resto = soma % 11

    if resto < 2:
        digito_2 = 0
    else:
        digito_2 = 11 - resto

    if int(cnpj[13]) != digito_2:
        return False

    return True
# ------------VALIDAÇÃO TELEFONE----------#

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

# ------------- LANDINGPAGE ------------- #

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/home')
def home():
    return render_template('home.html')

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
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("SELECT COUNT(*) AS total FROM fornecedor")
        total_fornecedores = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM cliente")
        total_clientes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM galpao")
        total_galpoes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM produto")
        total_produtos = cursor.fetchone()["total"]

        cursor.execute("""
            SELECT nome
            FROM empresa
            WHERE id = %s
        """, (session["empresa_id"],))

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
        total_produtos=total_produtos
    )
# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        print("===================================")
        print("TENTATIVA DE LOGIN")
        print("EMAIL:", email)
        print("SENHA INFORMADA:", bool(senha))
        print("===================================")

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

            print("USUARIO ENCONTRADO:", usuario)

            if not usuario:
                print("ERRO: usuário não encontrado.")
                flash("Email ou senha inválidos!", "erro")
                return render_template("login.html")

            print("ID:", usuario["id"])
            print("EMAIL BANCO:", usuario["email"])
            print("ATIVO:", usuario["ativo"])
            print("TIPO:", usuario["tipo"])
            print("EMPRESA:", usuario["empresa_id"])
            print("HASH:", usuario["senha"][:30] if usuario["senha"] else None)

            senha_correta = check_password_hash(
                usuario["senha"],
                senha
            )

            print("SENHA CORRETA:", senha_correta)

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

            print("LOGIN REALIZADO COM SUCESSO")
            print("SESSION:", dict(session))
            print("===================================")

            flash("Login realizado!", "sucesso")

            return redirect(url_for("dashboard"))

        except Exception as e:

            print("===================================")
            print("ERRO NO LOGIN")
            print(type(e).__name__)
            print(e)
            print("===================================")

            flash(f"Erro ao realizar login: {e}", "erro")

            return render_template("login.html")

        finally:
            cursor.close()
            conexao.close()

    return render_template("login.html")

# ---------------- REDEFINIR SENHA ---------------- #

@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):

    print("======================================")
    print("ACESSOU REDEFINIR SENHA")
    print("TOKEN:", token)
    print("======================================")

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT id, usuario_id, expira_em, usado
            FROM recuperacao_senha
            WHERE token = %s
        """, (token,))

        recuperacao = cursor.fetchone()

        print("RECUPERACAO ENCONTRADA:", recuperacao)

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

        print("======================================")
        print("ERRO AO REDEFINIR SENHA")
        print(type(e).__name__)
        print(e)
        print("======================================")

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

            print("ERRO AO GERAR TOKEN:", e)

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
    return render_template("config.html")

# ---------------- LOGOUT ---------------- #

@app.route('/logout')
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

            print("ERRO AO CADASTRAR EMPRESA:", e)

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
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                    p.*, 
                    COALESCE(SUM(e.quantidade), 0) AS quantidade,
                    COALESCE(MIN(e.estoque_minimo), 0) AS quantidade_minimo,
                    GROUP_CONCAT(DISTINCT f.nome ORDER BY f.nome SEPARATOR ', ') AS fornecedor
                FROM produto p
                LEFT JOIN estoque e ON p.id = e.produto_id
                LEFT JOIN fornecedor_produto fp ON p.id = fp.produto_id
                LEFT JOIN fornecedor f ON fp.fornecedor_id = f.id
                GROUP BY p.id
        """)
        produtos = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    lista = Estoque.find_all_consolidado()
    return render_template("estoque.html", produtos=lista, galpao=None)


@app.route("/estoque/<int:galpao_id>")
@login_obrigatorio
def estoque_galpao(galpao_id):
    galpao = Galpao.find_by_id(galpao_id)
    fornecedores = Fornecedor.find_all()

    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                p.*, 
                COALESCE(SUM(e.quantidade), 0) AS quantidade,
                COALESCE(MIN(e.estoque_minimo), 0) AS estoque_minimo,
                GROUP_CONCAT(DISTINCT f.nome ORDER BY f.nome SEPARATOR ', ') AS fornecedor
            FROM produto p
            JOIN estoque e ON p.id = e.produto_id
            LEFT JOIN fornecedor_produto fp ON p.id = fp.produto_id
            LEFT JOIN fornecedor f ON fp.fornecedor_id = f.id
            WHERE e.galpao_id = %s
            GROUP BY p.id
        """, (galpao_id,))
        produtos = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    produtos = Estoque.find_by_galpao(galpao_id)
    return render_template("estoque.html", produtos=produtos, galpao=galpao)

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
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("estoque", galpao_id=galpao_id))

# ---------------- INFO GALPAO ---------------- #

@app.route("/galpao/atualizar/<int:galpao_id>", methods=["POST"])
@login_obrigatorio
def atualizar_galpao(galpao_id):
    try:

        telefone = request.form.get("telefone", "").strip()
        telefone = formatar_telefone(telefone)

        cep = request.form.get("cep", "").strip()

        # Validação do CEP
        if not cep:
            flash("O CEP é obrigatório.", "erro")
            return redirect(url_for("info_galpao", galpao_id=galpao_id))

        if not cep.isdigit():
            flash("O CEP deve conter apenas números.", "erro")
            return redirect(url_for("info_galpao", galpao_id=galpao_id))

        if len(cep) != 8:
            flash("O CEP deve conter exatamente 8 números.", "erro")
            return redirect(url_for("info_galpao", galpao_id=galpao_id))

        caixas_por_nivel = to_int(
            request.form.get("caixas_por_nivel")
        )

        niveis_por_prateleira = to_int(
            request.form.get("niveis_por_prateleira")
        )

        total_prateleiras = to_int(
            request.form.get("total_prateleiras")
        )

        capacidade_total = (
            caixas_por_nivel
            * niveis_por_prateleira
            * total_prateleiras
        )

        dados = {
            "nome_resp": request.form.get("nome_resp"),
            "email_resp": request.form.get("email_resp"),
            "telefone": telefone,
            "stats": request.form.get("stats"),
            "nome": request.form.get("nome"),
            "cep": cep,
            "endereco": request.form.get("endereco"),
            "referencia": request.form.get("referencia"),
            "area_total": to_float(
                request.form.get("area_total")
            ),
            "caixas_por_nivel": caixas_por_nivel,
            "niveis_por_prateleira": niveis_por_prateleira,
            "total_prateleiras": total_prateleiras,
            "capacidade_total": capacidade_total,
        }

        Galpao.update(galpao_id, dados)

        flash(
            "Galpão atualizado com sucesso!",
            "sucesso"
        )

    except Exception as e:

        flash(
            f"Erro: {e}",
            "erro"
        )

    return redirect(
        url_for(
            "info_galpao",
            galpao_id=galpao_id
        )
    )
    


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
            capacidade=request.form.get("capacidade"),
            galpao_id=request.form.get("galpao_id"),
            ativo=request.form.get("ativo")
        )
        empilhadeira.insert()
        flash("Empilhadeira cadastrada com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("info_galpao", galpao_id=request.form.get("galpao_id")))

@app.route("/empilhadeira/atualizar/<int:empilhadeira_id>", methods=["POST"])
@login_obrigatorio
def atualizar_empilhadeira(empilhadeira_id):
    galpao_id = request.form.get("galpao_id")
    try:
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE empilhadeira
            SET marca=%s, modelo=%s, ano_fabricacao=%s,
                tipo_combustivel=%s, capacidade=%s, ativo=%s
            WHERE id=%s
        """, (
            request.form["marca"],
            request.form["modelo"],
            request.form["ano_fabricacao"],
            request.form["tipo_combustivel"],
            request.form["capacidade"],
            request.form["ativo"],
            empilhadeira_id
        ))
        conn.commit()
        conn.close()
        flash("Empilhadeira atualizada com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
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
        flash(f"Erro: {e}", "erro")
    return redirect(url_for("info_galpao", galpao_id=galpao_id))

# ---------------- PRODUTOS ---------------- #

@app.route("/produtos")
@login_obrigatorio
def produtos():
    
    # Agora a rota /produtos faz a mesma busca agrupada
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT 
                p.*, 
                COALESCE(SUM(e.quantidade), 0) AS quantidade,
                COALESCE(MIN(e.estoque_minimo), 0) AS estoque_minimo,
                GROUP_CONCAT(DISTINCT f.nome ORDER BY f.nome SEPARATOR ', ') AS fornecedor
            FROM produto p
            LEFT JOIN estoque e ON p.id = e.produto_id
            LEFT JOIN fornecedor_produto fp ON p.id = fp.produto_id
            LEFT JOIN fornecedor f ON fp.fornecedor_id = f.id
            GROUP BY p.id
        """)
        lista = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
        
    lista = Estoque.find_all_consolidado()
    return render_template("estoque.html", produtos=lista, galpao=None)

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
        flash(f"Erro ao salvar produto: {e}", "erro")
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
        "codigo_barras": request.form.get("codigo_barras"),
        "item_por_caixa": to_int(request.form.get("item_por_caixa")),
        "estoque_minimo": to_int(request.form.get("estoque_minimo"))
    }

    try:
        Produto.update(id, dados)

        conn = Database.connect()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE estoque
            SET estoque_minimo = %s
            WHERE produto_id = %s
        """, (
            dados["estoque_minimo"],
            id
        ))

        conn.commit()

        cursor.close()
        conn.close()

        flash("Produto atualizado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro ao atualizar produto: {e}", "erro")

    return redirect(url_for("info_produtos", id=id))

@app.route("/produto/desativar/<int:id>")
@login_obrigatorio
def desativar_produto(id):
    try:
        Produto.desativar(id)
        flash("Produto desativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    return redirect(url_for("info_produtos", id=id))

@app.route("/produto/reativar/<int:id>")
@login_obrigatorio
def reativar_produto(id):
    try:
        Produto.reativar(id)
        flash("Produto reativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    return redirect(url_for("produtos_inativos"))

@app.route("/produtos/inativos")
@login_obrigatorio
def produtos_inativos():
    lista = Produto.find_inativos()
    return render_template("produtos_inativos.html", produtos=lista)

@app.route("/produto/excluir/<int:id>")
@login_obrigatorio
def excluir_produto(id):
    try:
        Produto.safe_delete(id)
        flash("Produto excluído com sucesso!", "sucesso")
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("info_produtos", id=id))
    except Exception as e:
        flash(f"Erro: {e}", "erro")
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

    finally:
        cursor.close()
        conn.close()

    return render_template("info_produto.html", produto=produto, produtos=produtos)

# ---------------- GALPÕES ---------------- #

@app.route("/galpao")
@login_obrigatorio
def galpao():
    return render_template("galpao.html", galpoes=Galpao.find_all())

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

@app.route("/galpao/novo")
@login_obrigatorio
def novo_galpao():
    return render_template("galpao.html")

@app.route("/galpao/salvar", methods=["POST"])
@login_obrigatorio
def salvar_galpao():
    try:
        # =========================
        # E-MAIL
        # =========================

        email = request.form.get("email_resp", "").strip()

        if not email_valido(email):
            flash("Informe um e-mail válido.", "erro")
            return redirect(url_for("galpao"))


        # =========================
        # NOME DO RESPONSÁVEL
        # =========================

        nome_resp = request.form.get("nome_resp", "").strip()

        if not nome_valido(nome_resp):
            flash(
                "O nome do responsável deve conter apenas letras.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # CEP
        # =========================

        cep = request.form.get("cep", "").strip()

        # Remove espaços e caracteres de formatação
        cep = cep.replace("-", "").replace(" ", "")

        if not cep:
            flash("O CEP é obrigatório.", "erro")
            return redirect(url_for("galpao"))

        if not cep.isdigit():
            flash("O CEP deve conter apenas números.", "erro")
            return redirect(url_for("galpao"))

        if len(cep) != 8:
            flash(
                "O CEP deve conter exatamente 8 números.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # ÁREA TOTAL
        # =========================

        area_total = request.form.get("area_total", "").strip()

        if not area_valida(area_total):
            flash(
                "A área total deve ser um número maior que zero.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # TELEFONE
        # =========================

        telefone = request.form.get("telefone", "").strip()

        if not telefone_valido(telefone):
            flash(
                "Informe um telefone válido com 10 ou 11 números.",
                "erro"
            )
            return redirect(url_for("galpao"))

        telefone = formatar_telefone(telefone)

        if not telefone_valido(telefone):
            flash(
                "Informe um telefone válido com 10 ou 11 números.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # CAPACIDADE DO GALPÃO
        # =========================

        caixas_por_nivel = to_int(
            request.form.get("caixas_por_nivel")
        )

        niveis_por_prateleira = to_int(
            request.form.get("niveis_por_prateleira")
        )

        total_prateleiras = to_int(
            request.form.get("total_prateleiras")
        )

        capacidade_total = (
            caixas_por_nivel
            * niveis_por_prateleira
            * total_prateleiras
        )


        # =========================
        # CRIAÇÃO DO GALPÃO
        # =========================

        g = Galpao(
            nome=request.form.get("nome"),
            stats=request.form.get("stats"),
            cep=cep,
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

        flash(
            "Galpão cadastrado com sucesso!",
            "sucesso"
        )

    except Exception as e:

        flash(
            f"Erro: {e}",
            "erro"
        )

    return redirect(url_for("galpao"))

@app.route("/galpao/deletar/<int:galpao_id>", methods=["POST"])
@login_obrigatorio
def deletar_galpao(galpao_id):
    try:
        Galpao.delete(galpao_id)

        flash(
            "Galpão excluído com sucesso!",
            "sucesso"
        )

    except Exception as e:

        flash(
            f"Erro ao excluir o galpão: {e}",
            "erro"
        )

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
        # ==============================
        # RECEBE OS DADOS
        # ==============================

        nome = request.form.get("nome", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        nome_ctt = request.form.get("nome_ctt", "").strip()
        telefone = request.form.get("telefone", "").strip()
        email = request.form.get("email", "").strip()
        ativo = request.form.get("ativo", "").strip()

        # ==============================
        # CAMPOS OBRIGATÓRIOS
        # ==============================

        if not nome:
            flash("O nome da empresa é obrigatório.", "erro")
            return redirect(url_for("fornecedores"))

        if not cnpj:
            flash("O CNPJ é obrigatório.", "erro")
            return redirect(url_for("fornecedores"))

        if not nome_ctt:
            flash("O nome do contato é obrigatório.", "erro")
            return redirect(url_for("fornecedores"))

        if not telefone:
            flash("O telefone é obrigatório.", "erro")
            return redirect(url_for("fornecedores"))

        if not email:
            flash("O e-mail é obrigatório.", "erro")
            return redirect(url_for("fornecedores"))

        # ==============================
        # NOME DA EMPRESA
        # ==============================

        if len(nome) < 3:
            flash("O nome da empresa deve possuir pelo menos 3 caracteres.", "erro")
            return redirect(url_for("fornecedores"))

        if nome.isdigit():
            flash("O nome da empresa não pode conter somente números.", "erro")
            return redirect(url_for("fornecedores"))

        # ==============================
        # NOME DO CONTATO
        # ==============================

        if len(nome_ctt) < 3:
            flash("O nome do contato deve possuir pelo menos 3 caracteres.", "erro")
            return redirect(url_for("fornecedores"))

        if nome_ctt.isdigit():
            flash("O nome do contato não pode conter somente números.", "erro")
            return redirect(url_for("fornecedores"))

        # ==============================
        # CNPJ
        # ==============================

        cnpj_numeros = re.sub(r"\D", "", cnpj)

        if len(cnpj_numeros) != 14:
            flash("O CNPJ deve possuir exatamente 14 números.", "erro")
            return redirect(url_for("fornecedores"))

        if not validar_cnpj(cnpj_numeros):
            flash("O CNPJ informado é inválido.", "erro")
            return redirect(url_for("fornecedores"))

        # ==============================
        # TELEFONE
        # ==============================

        telefone_numeros = re.sub(r"\D", "", telefone)

        if len(telefone_numeros) not in [10, 11]:
            flash("O telefone deve possuir 10 ou 11 números.", "erro")
            return redirect(url_for("fornecedores"))

        # Impede números todos iguais
        if len(set(telefone_numeros)) == 1:
            flash("Digite um telefone válido.", "erro")
            return redirect(url_for("fornecedores"))

        # ==============================
        # E-MAIL
        # ==============================

        email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"

        if not re.match(email_regex, email):
            flash("Digite um e-mail válido.", "erro")
            return redirect(url_for("fornecedores"))

        # ==============================
        # STATUS
        # ==============================

        if ativo not in ["ativo", "inativo"]:
            flash("Status do fornecedor inválido.", "erro")
            return redirect(url_for("fornecedores"))

        # ==============================
        # SALVA NO BANCO
        # ==============================

        fornecedor = Fornecedor(
            nome=nome,
            ativo=ativo,
            cnpj=cnpj_numeros,
            nome_ctt=nome_ctt,
            telefone=telefone_numeros,
            email=email
        )

        fornecedor.insert()

        flash("Fornecedor cadastrado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro ao cadastrar fornecedor: {e}", "erro")

    return redirect(url_for("fornecedores"))

@app.route("/fornecedor/atualizar/<int:fornecedor_id>", methods=["POST"])
@login_obrigatorio
def atualizar_fornecedor(fornecedor_id):

    conexao = None
    cursor = None

    try:
        # ==============================
        # RECEBE OS DADOS
        # ==============================

        nome = request.form.get("nome", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        nome_ctt = request.form.get("nome_ctt", "").strip()
        email = request.form.get("email", "").strip()
        telefone = request.form.get("telefone", "").strip()
        ativo = request.form.get("ativo", "").strip()

        # ==============================
        # CAMPOS OBRIGATÓRIOS
        # ==============================

        if not nome:
            flash("O nome da empresa é obrigatório.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if not cnpj:
            flash("O CNPJ é obrigatório.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if not nome_ctt:
            flash("O nome do contato é obrigatório.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if not telefone:
            flash("O telefone é obrigatório.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if not email:
            flash("O e-mail é obrigatório.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        # ==============================
        # NOME
        # ==============================

        if len(nome) < 3:
            flash("O nome da empresa deve possuir pelo menos 3 caracteres.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if nome.isdigit():
            flash("O nome da empresa não pode conter somente números.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        # ==============================
        # CONTATO
        # ==============================

        if len(nome_ctt) < 3:
            flash("O nome do contato deve possuir pelo menos 3 caracteres.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if nome_ctt.isdigit():
            flash("O nome do contato não pode conter somente números.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        # ==============================
        # CNPJ
        # ==============================

        cnpj_numeros = re.sub(r"\D", "", cnpj)

        if len(cnpj_numeros) != 14:
            flash("O CNPJ deve possuir exatamente 14 números.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if not validar_cnpj(cnpj_numeros):
            flash("O CNPJ informado é inválido.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        # ==============================
        # TELEFONE
        # ==============================

        telefone_numeros = re.sub(r"\D", "", telefone)

        if len(telefone_numeros) not in [10, 11]:
            flash("O telefone deve possuir 10 ou 11 números.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        if len(set(telefone_numeros)) == 1:
            flash("Digite um telefone válido.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        # ==============================
        # E-MAIL
        # ==============================

        email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"

        if not re.match(email_regex, email):
            flash("Digite um e-mail válido.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        # ==============================
        # STATUS
        # ==============================

        if ativo not in ["ativo", "inativo"]:
            flash("Status do fornecedor inválido.", "erro")
            return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

        # ==============================
        # ATUALIZA NO BANCO
        # ==============================

        conexao = Database.connect()
        cursor = conexao.cursor()

        cursor.execute("""
            UPDATE fornecedor
            SET nome=%s,
                cnpj=%s,
                nome_ctt=%s,
                email=%s,
                telefone=%s,
                ativo=%s
            WHERE id=%s
        """, (
            nome,
            cnpj_numeros,
            nome_ctt,
            email,
            telefone_numeros,
            ativo,
            fornecedor_id
        ))

        conexao.commit()

        flash("Fornecedor atualizado com sucesso!", "sucesso")

    except Exception as e:

        if conexao:
            conexao.rollback()

        flash(f"Erro ao atualizar fornecedor: {e}", "erro")

    finally:

        if cursor:
            cursor.close()

        if conexao:
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
        flash(f"Erro: {e}", "erro")

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
        flash(f"Erro: {e}", "erro")

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
        # =========================
        # RECEBER DADOS DO FORMULÁRIO
        # =========================

        nome = request.form.get("nome", "").strip()
        ativo = request.form.get("ativo", "").strip()
        cidade = request.form.get("cidade", "").strip()
        empresa = request.form.get("empresa", "").strip()
        estado = request.form.get("estado", "").strip()
        email = request.form.get("email", "").strip()

        cpf_cnpj = request.form.get("cpf", "").strip()
        telefone = request.form.get("telefone", "").strip()
        cep = request.form.get("cep", "").strip()

        # =========================
        # DEIXAR SOMENTE NÚMEROS
        # =========================

        cpf_cnpj = re.sub(r"\D", "", cpf_cnpj)
        telefone = re.sub(r"\D", "", telefone)
        cep = re.sub(r"\D", "", cep)

        # =========================
        # VALIDAÇÃO CPF / CNPJ
        # =========================

        if len(cpf_cnpj) not in (11, 14):
            flash(
                "CPF deve possuir exatamente 11 números ou CNPJ deve possuir exatamente 14 números.",
                "erro"
            )
            return redirect(url_for("cliente"))

        # =========================
        # VALIDAÇÃO TELEFONE
        # =========================

        if telefone and len(telefone) not in (10, 11):
            flash(
                "O telefone deve possuir DDD e ter 10 ou 11 números.",
                "erro"
            )
            return redirect(url_for("cliente"))

        # =========================
        # VALIDAÇÃO CEP
        # =========================

        if cep and len(cep) != 8:
            flash(
                "O CEP deve possuir exatamente 8 números.",
                "erro"
            )
            return redirect(url_for("cliente"))

        # =========================
        # CRIAR CLIENTE
        # =========================

        c = Cliente(
            nome=nome,
            ativo=ativo,
            cidade=cidade,
            empresa=empresa,
            cep=cep,
            estado=estado,
            cpf_cnpj=cpf_cnpj,
            email=email,
            telefone=telefone
        )
        c.insert()
        flash(
            "Cliente cadastrado!",
            "sucesso"
        )
    except Exception as e:

        flash(
            f"Erro: {e}",
            "erro"
        )
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
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("info_galpao", galpao_id=request.form.get("galpao_id")))

@app.route("/funcionario/atualizar", methods=["POST"])
@login_obrigatorio
def atualizar_funcionario():
    try:
        salario = request.form.get("salario")
        salario = float(salario) if salario else 0.00

        conn = Database.connect()
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE funcionario
            SET nome=%s, cpf=%s, salario=%s, email=%s,
                telefone=%s, cargo=%s, ativo=%s
            WHERE id=%s
        """, (
            request.form["nome"],
            request.form["cpf"],
            salario,
            request.form["email"],
            request.form["telefone"],
            request.form["cargo"],
            request.form["ativo"],
            request.form["id"]
        ))

        conn.commit()
        conn.close()
        flash("Funcionário atualizado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("info_galpao", galpao_id=request.form.get("galpao_id")))

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
    return render_template(
        "movimentacoes.html",
        movimentacoes=Movimentacao.find_all_with_product()
    )

@app.route("/movimentacao/nova")
@login_obrigatorio
def nova_movimentacao():
    lista = Produto.find_all()
    return render_template("form_movimentacao.html", produtos=lista)

@app.route("/movimentacao/salvar", methods=["POST"])
@login_obrigatorio
def salvar_movimentacao():
    produto_id = to_int(request.form.get("produto_id"))
    galpao_id = to_int(request.form.get("galpao_id"))
    funcionario_id = to_int(request.form.get("funcionario_id"))
    tipo = request.form.get("tipo").lower()
    quantidade = to_float(request.form.get("quantidade"))

    try:
        conexao = Database.connect()
        cursor = conexao.cursor()

        cursor.execute("""
            INSERT INTO movimentacao
            (produto_id, galpao_id, funcionario_id, tipo, quantidade)
            VALUES (%s, %s, %s, %s, %s)
        """, (produto_id, galpao_id, funcionario_id, tipo, quantidade))

        cursor.execute("""
            SELECT quantidade FROM estoque
            WHERE produto_id = %s AND galpao_id = %s
        """, (produto_id, galpao_id))

        resultado = cursor.fetchone()
        atual = resultado[0] if resultado else 0

        if tipo == "entrada":
            nova_qtd = atual + quantidade
        elif tipo == "saida":
            nova_qtd = atual - quantidade
        else:
            nova_qtd = atual

        cursor.execute("""
            UPDATE estoque SET quantidade = %s
            WHERE produto_id = %s AND galpao_id = %s
        """, (nova_qtd, produto_id, galpao_id))

        conexao.commit()
        conexao.close()
        flash("Movimentação registrada!", "sucesso")

    except Exception as e:
        flash(f"Erro: {e}", "erro")

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

        # =========================
        # RECEBER DADOS
        # =========================

        nome = request.form.get("nome", "").strip()
        empresa = request.form.get("empresa", "").strip()
        email = request.form.get("email", "").strip()
        telefone = request.form.get("telefone", "").strip()
        cep = request.form.get("cep", "").strip()
        cidade = request.form.get("cidade", "").strip()
        estado = request.form.get("estado", "").strip()
        ativo = request.form.get("ativo", "").strip()

        # =========================
        # DEIXAR SOMENTE NÚMEROS
        # =========================

        telefone = re.sub(r"\D", "", telefone)
        cep = re.sub(r"\D", "", cep)

        # =========================
        # VALIDAÇÃO TELEFONE
        # =========================

        if telefone and len(telefone) not in (10, 11):
            flash(
                "O telefone deve possuir DDD e ter 10 ou 11 números.",
                "erro"
            )
            return redirect(
                url_for(
                    "info_cliente",
                    cliente_id=cliente_id
                )
            )

        # =========================
        # VALIDAÇÃO CEP
        # =========================

        if cep and len(cep) != 8:
            flash(
                "O CEP deve possuir exatamente 8 números.",
                "erro"
            )
            return redirect(
                url_for(
                    "info_cliente",
                    cliente_id=cliente_id
                )
            )

        # =========================
        # DADOS PARA ATUALIZAÇÃO
        # =========================

        dados = {
            "nome": nome,
            "ativo": ativo,
            "empresa": empresa,
            "email": email,
            "telefone": telefone,
            "cep": cep,
            "cidade": cidade,
            "estado": estado
        }
        Cliente.update(
            cliente_id,
            dados
        )
        flash(
            "Cliente atualizado com sucesso!",
            "sucesso"
        )
    except Exception as e:

        flash(
            f"Erro: {e}",
            "erro"
        )
    return redirect(
        url_for(
            "info_cliente",
            cliente_id=cliente_id
        )
    )


@app.route("/cliente/deletar/<int:cliente_id>", methods=["POST"])
@login_obrigatorio
def deletar_cliente(cliente_id):
    try:
        Cliente.delete(cliente_id)
        flash("Cliente excluído com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    return redirect(url_for("cliente"))


# ------------------------------------------------------------------ #
# API — produtos disponíveis por galpão                               #
# ------------------------------------------------------------------ #

@app.route("/api/produtos_do_galpao/<int:galpao_id>")
@login_obrigatorio
def api_produtos_do_galpao(galpao_id):
    from flask import jsonify

    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT 
                p.id,
                p.sku,
                p.nome,
                COALESCE(p.preco_venda, 0) AS preco_venda,
                COALESCE(e.quantidade, 0) AS estoque_disponivel
            FROM estoque e
            INNER JOIN produto p
                ON e.produto_id = p.id
            WHERE e.galpao_id = %s
              AND e.quantidade > 0
              AND p.ativo = TRUE
            ORDER BY p.nome ASC
        """, (galpao_id,))

        produtos = cursor.fetchall()

        # Converte Decimal para float antes de enviar para o JavaScript
        for produto in produtos:
            produto["preco_venda"] = float(
                produto["preco_venda"] or 0
            )

            produto["estoque_disponivel"] = int(
                produto["estoque_disponivel"] or 0
            )

        print("========================================")
        print("GALPÃO:", galpao_id)
        print("PRODUTOS:", produtos)
        print("========================================")

        return jsonify(produtos)

    except Exception as e:

        print("ERRO API PRODUTOS:", e)

        return jsonify({
            "erro": str(e)
        }), 500

    finally:
        cursor.close()
        conn.close()
@app.route("/api/todos_produtos")
@login_obrigatorio
def api_todos_produtos():
    from flask import jsonify
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, sku, nome, preco_custo
            FROM produto
            WHERE ativo = TRUE
            ORDER BY nome ASC
        """)
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()

@app.route("/api/produtos_do_fornecedor/<int:fornecedor_id>")
@login_obrigatorio
def api_produtos_do_fornecedor(fornecedor_id):
    from flask import jsonify
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        # 1. Tenta buscar os produtos vinculados a este fornecedor
        cursor.execute("""
            SELECT
                p.id,
                p.sku,
                p.nome,
                fp.preco_custo,
                COALESCE(e_total.estoque_disponivel, 0) AS estoque_disponivel
            FROM fornecedor_produto fp
            JOIN produto p ON fp.produto_id = p.id
            LEFT JOIN (
                SELECT produto_id, SUM(quantidade) AS estoque_disponivel
                FROM estoque
                GROUP BY produto_id
            ) e_total ON e_total.produto_id = p.id
            WHERE fp.fornecedor_id = %s
              AND fp.ativo = 1
              AND p.ativo = TRUE
            ORDER BY p.nome ASC
        """, (fornecedor_id,))
        
        produtos = cursor.fetchall()

        # 2. FALLBACK: Se o fornecedor não tiver vínculos, retorna todos os produtos ativos do sistema
        if not produtos:
            cursor.execute("""
                SELECT
                    p.id,
                    p.sku,
                    p.nome,
                    p.preco_custo,
                    COALESCE(e_total.estoque_disponivel, 0) AS estoque_disponivel
                FROM produto p
                LEFT JOIN (
                    SELECT produto_id, SUM(quantidade) AS estoque_disponivel
                    FROM estoque
                    GROUP BY produto_id
                ) e_total ON e_total.produto_id = p.id
                WHERE p.ativo = TRUE
                ORDER BY p.nome ASC
            """)
            produtos = cursor.fetchall()

        return jsonify(produtos)
    finally:
        cursor.close()
        conn.close()
# ------------------------------------------------------------------ #
# PEDIDOS DE ENTRADA  (usa tabela: pedido_fornecedor)                 #
# ------------------------------------------------------------------ #
@app.route("/cadastro_pedido_entrada")
@login_obrigatorio
def cadastro_pedido_entrada():
    return render_template(
        "pedidos_fornecedor.html",
        galpoes=Galpao.find_all(),
        fornecedores=Fornecedor.find_all()
    )



@app.route("/cadastro_pedido/<int:cliente_id>")
@login_obrigatorio
def cadastro_pedido(cliente_id):
    cliente = Cliente.find_by_id(cliente_id)
    if not cliente:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("cliente"))
    return render_template(
        "cadastro_pedidos.html",
        galpoes=Galpao.find_all(),
        cliente=cliente
    )

@app.route("/pedidos_entrada")
@login_obrigatorio
def listar_pedidos_entrada():
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pf.*, f.nome AS fornecedor_nome, g.nome AS galpao_nome
            FROM pedido_fornecedor pf
            LEFT JOIN fornecedor f ON pf.fornecedor_id = f.id
            LEFT JOIN galpao     g ON pf.galpao_id     = g.id
            ORDER BY pf.id DESC
        """)
        pedidos = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template(
        "pedidos_fornecedor.html",
        pedidos=pedidos,
        galpoes=Galpao.find_all(),
        fornecedores=Fornecedor.find_all()
    )

@app.route("/salvar_pedido_entrada", methods=["POST"])
@login_obrigatorio
def salvar_pedido_entrada():
    fornecedor_id    = to_int(request.form.get("fornecedor_id"))
    galpao_id        = to_int(request.form.get("galpao_id"))
    numero_documento = request.form.get("numero_documento")
    data_prevista    = request.form.get("data_entrada")
    observacao       = request.form.get("observacao")

    try:
        itens = json.loads(request.form.get("itens_json", "[]"))
    except Exception:
        itens = []

    if not itens:
        flash("Adicione pelo menos um item ao pedido.", "erro")
        return redirect(url_for("novo_pedido_entrada"))

    if not fornecedor_id or not galpao_id:
        flash("Selecione o fornecedor e o galpão de destino.", "erro")
        return redirect(url_for("novo_pedido_entrada"))

    valor_total = sum(i["quantidade"] * i["preco_unitario"] for i in itens)

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

            # AUTO-VÍNCULO: Associa o produto ao fornecedor se ainda não estiver vinculado
            cursor.execute("""
                INSERT INTO fornecedor_produto
                    (fornecedor_id, produto_id, preco_custo, desconto, quantidade_minima, prazo_entrega_dias, ativo)
                VALUES (%s, %s, %s, 0, 1, 0, 1)
                ON DUPLICATE KEY UPDATE
                    preco_custo = VALUES(preco_custo),
                    ativo = 1
            """, (fornecedor_id, item["produto_id"], item["preco_unitario"]))

            # Incrementa estoque automaticamente
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
            """, (item["produto_id"], galpao_id, item["quantidade"]))

        conn.commit()
        flash("Pedido de entrada cadastrado com sucesso!", "sucesso")
        return redirect(url_for("listar_pedidos_entrada"))

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao cadastrar pedido de entrada: {e}", "erro")
        return redirect(url_for("novo_pedido_entrada"))
    finally:
        cursor.close()
        conn.close()
        
@app.route("/pedidos_entrada/novo", methods=["GET", "POST"])
@login_obrigatorio
def novo_pedido_entrada():
    fornecedores = Fornecedor.find_all()
    produtos     = Produto.find_all()
    galpoes      = Galpao.find_all()

    if request.method == "POST":
        fornecedor_id    = to_int(request.form.get("fornecedor_id"))
        galpao_id        = to_int(request.form.get("galpao_id"))
        numero_documento = request.form.get("numero_documento")
        data_prevista    = request.form.get("data_entrada")   # campo "data_entrada" no form
        observacao       = request.form.get("observacao")

        produtos_form    = request.form.getlist("produto_id[]")
        quantidades_form = request.form.getlist("quantidade[]")
        valores_form     = request.form.getlist("valor_unitario[]")

        itens = []
        for i in range(len(produtos_form)):
            if produtos_form[i] and quantidades_form[i]:
                itens.append({
                    "produto_id":    to_int(produtos_form[i]),
                    "quantidade":    to_float(quantidades_form[i]),
                    "preco_unitario": to_float(valores_form[i]) if i < len(valores_form) else 0.0
                })

        if not itens:
            flash("Adicione pelo menos um item ao pedido.", "erro")
            return redirect(url_for("novo_pedido_entrada"))

        conn = Database.connect()
        cursor = conn.cursor()
        try:
            valor_total = sum(i["quantidade"] * i["preco_unitario"] for i in itens)

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

                # Incrementa o estoque automaticamente
                cursor.execute("""
                    INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                    VALUES (%s, %s, %s, 0)
                    ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
                """, (item["produto_id"], galpao_id, item["quantidade"]))

            conn.commit()
            flash("Pedido de entrada cadastrado com sucesso!", "sucesso")
            return redirect(url_for("listar_pedidos_entrada"))

        except Exception as e:
            conn.rollback()
            flash(f"Erro ao cadastrar pedido de entrada: {e}", "erro")
        finally:
            cursor.close()
            conn.close()

    return render_template(
        "pedidos_entrada/form.html",
        fornecedores=fornecedores,
        produtos=produtos,
        galpoes=galpoes
    )


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

@app.route("/cadastro_pedido_saida")
@login_obrigatorio
def cadastro_pedido_saida():
    return render_template(
        "cadastro_pedidos.html",
        galpoes=Galpao.find_all(),
        clientes=Cliente.find_all()
    )


@app.route("/pedidos_saida")
@login_obrigatorio
def listar_pedidos_saida():
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pc.*, c.nome AS cliente_nome, g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c ON pc.cliente_id = c.id
            LEFT JOIN galpao  g ON pc.galpao_id  = g.id
            WHERE pc.galpao_id IS NOT NULL
            ORDER BY pc.data_pedido DESC
        """)
        pedidos = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()
    return render_template(
    "cliente.html",
    cliente=cliente,
    pedidos=pedidos,
    galpoes=galpao,
    produtos=lista_produtos,
)


@app.route("/salvar_pedido_saida", methods=["POST"])
@login_obrigatorio
def salvar_pedido_saida():
    cliente_id       = to_int(request.form.get("cliente_id"))
    galpao_id        = to_int(request.form.get("galpao_id"))
    numero_documento = request.form.get("numero_documento")
    data_saida       = request.form.get("data_saida")
    observacao       = request.form.get("observacao")

    try:
        itens = json.loads(request.form.get("itens_json", "[]"))
    except Exception:
        itens = []

    if not itens:
        flash("Adicione pelo menos um item ao pedido.", "erro")
        return redirect(url_for("cadastro_pedido", cliente_id=cliente_id))

    valor_total = sum(i["quantidade"] * i["preco_unitario"] for i in itens)

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO pedido_cliente
                    (cliente_id, galpao_id, numero_documento, data_pedido,
                    observacao, valor_total, status_pedido)
                VALUES (%s, %s, %s, %s, %s, %s, 'pendente')
            """, (cliente_id, galpao_id, numero_documento, data_saida, observacao, valor_total))
        pedido_id = cursor.lastrowid

        for item in itens:
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

        conn.commit()
        flash("Pedido de saída cadastrado com sucesso!", "sucesso")
        return redirect(url_for("pedidos_clientes", cliente_id=cliente_id))

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao cadastrar pedido de saída: {e}", "erro")
        return redirect(url_for("cadastro_pedido", cliente_id=cliente_id))
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
    # buscar pedido + itens, renderizar formulário de edição
    pass

@app.route("/deletar_pedido/<int:id>")
@login_obrigatorio
def deletar_pedido(id):
    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM item_pedido_fornecedor WHERE pedido_fornecedor_id = %s", (id,))
        cursor.execute("DELETE FROM pedido_fornecedor WHERE id = %s", (id,))
        conn.commit()
        flash("Pedido excluído com sucesso!", "sucesso")
    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pedido: {e}", "erro")
    finally:
        cursor.close()
        conn.close()
    return redirect(url_for("listar_pedidos_entrada"))

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

        cursor.execute("""
            SELECT pc.*, c.nome AS cliente_nome, c.email AS cliente_email
            FROM pedido_cliente pc
            JOIN cliente c ON pc.cliente_id = c.id
            WHERE pc.cliente_id = %s
            ORDER BY pc.data_pedido DESC
        """, (cliente_id,))
        pedidos = cursor.fetchall()

        galpoes = Galpao.find_all()
        lista_produtos = Produto.find_all()

        return render_template(
            "pedidos_cliente.html",
            cliente=c,
            pedidos=pedidos,
            galpoes=galpoes,
            produtos=lista_produtos
        )
    except Exception as e:
        print("ERRO REAL:", e)
        flash(f"Erro ao carregar pedidos do cliente: {e}", "erro")
        return redirect(url_for("cliente"))
    finally:
        cursor.close()
        conexao.close()
        
# ---------------- INFO PEDIDOS ------------#

@app.route("/pedido-cliente/<int:pedido_id>")
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
            flash("Pedido não encontrado.", "danger")
            return redirect(url_for("clientes"))

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
        flash(f"Erro ao carregar pedido: {e}", "danger")
        return redirect(url_for("pedidos_clientes"))

    finally:
        cursor.close()
        conexao.close()
# ---------------- PEDIDOS ---------------- #

@app.route("/pedidos")
@login_obrigatorio
def pedidos():
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pf.*, f.nome AS fornecedor_nome, g.nome AS galpao_nome
            FROM pedido_fornecedor pf
            LEFT JOIN fornecedor f ON pf.fornecedor_id = f.id
            LEFT JOIN galpao     g ON pf.galpao_id     = g.id
            ORDER BY pf.id DESC
        """)
        pedidos = cursor.fetchall()
    finally:
        cursor.close()
        conn.close()

    return render_template(
        "pedidos.html",
        pedidos=pedidos,
        galpoes=Galpao.find_all(),
        fornecedores=Fornecedor.find_all(),
        produtos=Produto.find_all()
    )

@app.route("/pedido/salvar", methods=["POST"])
@login_obrigatorio
def salvar_pedido():
    dados = {
        "produto_id": to_int(request.form.get("produto_id")),
        "tipo": request.form.get("tipo").upper(),
        "quantidade": to_int(request.form.get("quantidade")),
        "observacao": request.form.get("observacao")
    }
    try:
        PedidoCliente.create(dados)
        flash("Pedido criado com sucesso!", "sucesso")
        return redirect(url_for("pedidos"))
    except Exception as e:
        flash(f"Erro ao criar pedido: {e}", "erro")
        return redirect(url_for("produtos"))

@app.route("/pedido/processar/<int:id>")
@login_obrigatorio
def processar_pedido(id):
    try:
        PedidoCliente.processar(id)
        flash("Pedido processado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao processar pedido: {e}", "erro")
    return redirect(url_for("pedidos"))

@app.route("/pedido/cancelar/<int:id>")
@login_obrigatorio
def cancelar_pedido(id):
    try:
        PedidoCliente.cancelar(id)
        flash("Pedido cancelado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao cancelar pedido: {e}", "erro")
    return redirect(url_for("pedidos"))

# ---------------- ERRO 404 ---------------- #

@app.errorhandler(404)
def pagina_nao_encontrada(error):
    return render_template("404.html"), 404

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    app.run(debug=True)