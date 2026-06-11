from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from core.database import Database

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


app = Flask(__name__)
app.secret_key = "chave_secreta"

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

# ------------- LANDINGPAGE ------------- #

@app.route('/')
def landing():
    return render_template('.html')

@app.route('/home')
def home():
    return render_template('home.html')

# ---------------- LOGIN OBRIGATÓRIO ---------------- #

def login_obrigatorio(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "usuario_logado" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrap

# ---------------- INDEX ---------------- #

@app.route("/index")
@login_obrigatorio
def index():
    return render_template("index.html")

# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        senha = request.form.get("senha")

        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            sql = "SELECT * FROM usuario WHERE email = %s"
            cursor.execute(sql, (email,))
            usuario = cursor.fetchone()

            if usuario and check_password_hash(usuario["senha"], senha):
                session["usuario_logado"] = usuario["email"]
                session["empresa_id"] = usuario["empresa_id"]

                flash("Login realizado!", "sucesso")
                return redirect(url_for("index"))
            else:
                flash("Email ou senha inválidos!", "erro")

        finally:
            cursor.close()
            conexao.close()

    return render_template("login.html")

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
        nome = request.form.get("nome")
        cpf = request.form.get("cnpj")
        email = request.form.get("email")
        telefone = request.form.get("telefone")
        senha = generate_password_hash(request.form.get("senha"))
        empresa_id = request.form.get("empresa_id")

        conexao = Database.connect()
        cursor = conexao.cursor()

        try:
            sql = """
            INSERT INTO empresa (nome, cnpj, email, telefone, senha)
            VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (nome, cpf, email, telefone, senha))
            conexao.commit()
            flash("Cadastro realizado com sucesso!", "sucesso")
            return redirect(url_for("login"))

        except Exception as e:
            flash("Erro ao cadastrar! Verifique os dados.", "erro")
            print(e)

        finally:
            cursor.close()
            conexao.close()

    return render_template("cadastro.html")

# ---------------- ESTOQUE ---------------- #

@app.route("/estoque")
@login_obrigatorio
def estoque():
    produtos = Estoque.resumo_geral()
    return render_template("estoque.html", produtos=produtos, galpao=None)

@app.route("/estoque/<int:galpao_id>")
@login_obrigatorio
def estoque_galpao(galpao_id):
    produtos = Estoque.find_by_galpao(galpao_id)
    galpao = Galpao.find_by_id(galpao_id)
    fornecedores = Fornecedor.find_all()

    return render_template(
        "estoque.html",
        produtos=produtos,
        galpao=galpao,
        fornecedores=fornecedores
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
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("estoque_galpao", galpao_id=galpao_id))

# ---------------- INFO GALPAO ---------------- #

@app.route("/info_galpao/<int:galpao_id>")
@login_obrigatorio
def info_galpao(galpao_id):
    galpao = Galpao.find_by_id(galpao_id)
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
        caixas_por_nivel      = to_int(request.form.get("caixas_por_nivel"))
        niveis_por_prateleira = to_int(request.form.get("niveis_por_prateleira"))
        total_prateleiras     = to_int(request.form.get("total_prateleiras"))
        capacidade_total      = caixas_por_nivel * niveis_por_prateleira * total_prateleiras

        dados = {
            "nome_resp":             request.form.get("nome_resp"),
            "email_resp":            request.form.get("email_resp"),
            "telefone":              request.form.get("telefone"),
            "stats":                 request.form.get("stats"),
            "nome":                  request.form.get("nome"),
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
        flash("Galpão atualizado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    return redirect(url_for("info_galpao", galpao_id=galpao_id))


@app.route("/galpao/deletar/<int:galpao_id>", methods=["POST"])
@login_obrigatorio
def deletar_galpao(galpao_id):
    try:
        Galpao.delete(galpao_id)
        flash("Galpão excluído com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
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
    lista = Produto.find_all_completo()
    return render_template("estoque.html", produtos=lista, galpao=None)

@app.route("/produto/salvar", methods=["POST"])
@login_obrigatorio
def salvar_produto():
    galpao_id = to_int(request.form.get("galpao_id"))
    try:
        produto = Produto(
            sku=request.form.get("sku"),
            nome=request.form.get("nome"),
            descricao=request.form.get("descricao"),
            categoria=request.form.get("categoria"),
            preco_custo=to_float(request.form.get("preco_custo")),
            preco_venda=to_float(request.form.get("preco_venda")),
            peso=to_float(request.form.get("peso")),
            volume=to_float(request.form.get("volume")),
            tipo=request.form.get("tipo"),
            codigo_barras=request.form.get("codigo_barras"),
        )

        erros = produto.validate()
        if erros:
            for erro in erros:
                flash(erro, "erro")
            return redirect(url_for("estoque_galpao", galpao_id=galpao_id))

        produto_id = produto.insert()

        quantidade = to_int(request.form.get("quantidade"))
        quantidade_minimo = to_int(request.form.get("quantidade_minimo"))

        if galpao_id:
            conn = Database.connect()
            cursor = conn.cursor()
            try:
                cursor.execute("""
                    INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        quantidade = VALUES(quantidade),
                        estoque_minimo = VALUES(estoque_minimo)
                """, (produto_id, galpao_id, quantidade, quantidade_minimo))
                conn.commit()
                # Adicionar logo após conn.commit() do estoque:
                fornecedor_id = to_int(request.form.get("fornecedor_id"))
                if fornecedor_id:
                    cursor.execute("""
                        INSERT INTO fornecedor_produto
                            (fornecedor_id, produto_id, preco_custo, ativo)
                        VALUES (%s, %s, %s, 1)
                        ON DUPLICATE KEY UPDATE ativo = 1
                    """, (fornecedor_id, produto_id, to_float(request.form.get("preco_custo"))))
            finally:
                cursor.close()
                conn.close()

        flash("Produto cadastrado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("estoque_galpao", galpao_id=galpao_id))

@app.route("/produto/editar/<int:id>")
@login_obrigatorio
def editar_produto(id):
    # Redireciona para info_produtos, que já exibe o formulário de edição
    return redirect(url_for("info_produtos", id=id))

@app.route("/produto/atualizar/<int:id>", methods=["POST"])
@login_obrigatorio
def atualizar_produto(id):
    dados = {
        "sku":           request.form.get("sku"),
        "nome":          request.form.get("nome"),
        "descricao":     request.form.get("descricao"),
        "categoria":     request.form.get("categoria"),
        "preco_custo":   to_float(request.form.get("preco_custo")),
        "preco_venda":   to_float(request.form.get("preco_venda")),
        "peso":          to_float(request.form.get("peso")),
        "volume":        to_float(request.form.get("volume")),
        "tipo":          request.form.get("tipo"),
        "codigo_barras": request.form.get("codigo_barras"),
    }

    produto = Produto(**dados)
    erros = produto.validate()

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return redirect(url_for("info_produtos", id=id))

    try:
        Produto.update(id, dados)
        flash("Produto atualizado com sucesso!", "sucesso")
        return redirect(url_for("info_produtos", id=id))

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

@app.route("/galpao/novo")
@login_obrigatorio
def novo_galpao():
    return render_template("galpao.html")

@app.route("/galpao/salvar", methods=["POST"])
@login_obrigatorio
def salvar_galpao():
    try:
        caixas_por_nivel = to_int(request.form.get("caixas_por_nivel"))
        niveis_por_prateleira = to_int(request.form.get("niveis_por_prateleira"))
        total_prateleiras = to_int(request.form.get("total_prateleiras"))
        capacidade_total = caixas_por_nivel * niveis_por_prateleira * total_prateleiras

        g = Galpao(
            nome=request.form.get("nome"),
            stats=request.form.get("stats"),
            cep=request.form.get("cep"),
            email_resp=request.form.get("email_resp"),
            nome_resp=request.form.get("nome_resp"),
            endereco=request.form.get("endereco"),
            referencia=request.form.get("referencia"),
            cidade=request.form.get("cidade"),
            estado=request.form.get("estado"),
            area_total=to_float(request.form.get("area_total")),
            telefone=request.form.get("telefone"),
            total_prateleiras=total_prateleiras,
            niveis_por_prateleira=niveis_por_prateleira,
            caixas_por_nivel=caixas_por_nivel,
            capacidade_total=capacidade_total
        )
        g.insert()
        flash("Galpão cadastrado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("galpao"))

# ---------------- FORNECEDORES ---------------- #

# ---------------- FORNECEDORES ---------------- #

@app.route("/fornecedores")
@login_obrigatorio
def fornecedores():
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        # Removido o WHERE ativo = 'ativo' — agora traz todos
        cursor.execute("""
            SELECT id, nome, nome_ctt, email, telefone, ativo, cnpj
            FROM fornecedor
            ORDER BY nome ASC
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
        flash(f"Erro: {e}", "erro")
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
        flash("Fornecedor atualizado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {e}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("fornecedores"))


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
    return render_template("cliente.html", clientes=Cliente.find_all())

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
        flash(f"Erro: {e}", "erro")
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
        dados = {
            "nome":     request.form.get("nome"),
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
        flash(f"Erro: {e}", "erro")
    return redirect(url_for("info_cliente", cliente_id=cliente_id))


@app.route("/cliente/deletar/<int:cliente_id>", methods=["POST"])
@login_obrigatorio
def deletar_cliente(cliente_id):
    try:
        Cliente.delete(cliente_id)
        flash("Cliente excluído com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")
    return redirect(url_for("cliente"))

# ---------------- Pedidos Clientes ---------------- #

@app.route("/cadastro_pedido/<int:cliente_id>")
@login_obrigatorio
def pedidos_cliente(cliente_id):
    c = Cliente.find_by_id(cliente_id)
    pedidos = PedidoCliente.find_by_cliente(cliente_id)
    galpoes = Galpao.find_all()
    lista_produtos = Produto.find_all()

    return render_template(
        "cadastro_pedidos.html",
        cliente=c,
        pedidos=pedidos,
        galpoes=galpoes,
        produtos=lista_produtos
    )

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
    finally:
        cursor.close()
        conexao.close()

@app.route("/salvar_pedido_cliente", methods=["POST"])
@login_obrigatorio
def salvar_pedido_cliente():
    conexao = Database.connect()
    cursor = conexao.cursor()
    cliente_id = request.form.get("cliente_id")

    try:
        cursor.execute("""
            INSERT INTO pedido_cliente
            (cliente_id, produto_id, produto_pedido, valor_total, status_pedido)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            cliente_id,
            request.form.get("produto_id"),
            request.form.get("produto_pedido"),
            request.form.get("valor_total") or 0,
            "pendente"
        ))
        conexao.commit()
        flash("Pedido criado com sucesso!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao criar pedido: {e}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("pedidos_clientes", cliente_id=cliente_id))

@app.route("/deletar_pedido/<int:pedido_id>")
@login_obrigatorio
def deletar_pedido(pedido_id):
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)
    cliente_id = None

    try:
        cursor.execute("SELECT cliente_id FROM pedido_cliente WHERE id = %s", (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("cliente"))

        cliente_id = pedido["cliente_id"]
        cursor.execute("DELETE FROM pedido_cliente WHERE id = %s", (pedido_id,))
        conexao.commit()
        flash("Pedido excluído com sucesso!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao excluir pedido: {e}", "erro")
        cliente_id = request.args.get("cliente_id")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("pedidos_clientes", cliente_id=cliente_id))

# ---------------- PEDIDOS ---------------- #

@app.route("/pedidos")
@login_obrigatorio
def pedidos():
    return render_template(
        "pedidos.html",
        pedidos=PedidoCliente.find_all_with_product()
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

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    app.run(debug=True)