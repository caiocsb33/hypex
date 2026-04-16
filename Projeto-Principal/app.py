from flask import Flask, render_template, request, redirect, url_for, flash
from core.database import Database

from models.produto import Produto
from models.movimentacao import Movimentacao
from models.pedido_movimentacao import PedidoMovimentacao
from models.fornecedor import Fornecedor
from models.cliente import Cliente
from models.funcionario import Funcionario
from models.galpao import Galpao
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

# ---------------- DASHBOARD ---------------- #

@app.route("/")
def index():
    return render_template("index.html")

# ---------------- PRODUTOS ---------------- #

@app.route("/produtos")
def produtos():
    return render_template("produtos.html", produtos=Produto.find_all())

@app.route("/produto/novo")
def novo_produto():
    return render_template("formulario_produto.html", produto=None)

@app.route("/produto/salvar", methods=["POST"])
def salvar_produto():
    dados = {
        "sku": request.form.get("sku"),
        "nome": request.form.get("nome"),
        "descricao": request.form.get("descricao"),
        "categoria": request.form.get("categoria"),
        "unidade_medida": request.form.get("unidade_medida"),
        "preco_custo": to_float(request.form.get("preco_custo")),
        "preco_venda": to_float(request.form.get("preco_venda"))
    }

    produto = Produto(**dados)
    erros = produto.validate()

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return render_template("formulario_produto.html", produto=dados)

    try:
        produto_id = produto.insert()

        conexao = Database.connect()
        cursor = conexao.cursor()

        cursor.execute("""
            INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
            VALUES (%s, %s, 0, 0)
        """, (produto_id, 1))

        conexao.commit()
        conexao.close()

        flash("Produto cadastrado com sucesso!", "sucesso")
        return redirect(url_for("produtos"))

    except Exception as e:
        flash(f"Erro ao cadastrar produto: {e}", "erro")
        return render_template("formulario_produto.html", produto=dados)

@app.route("/produto/editar/<int:id>")
def editar_produto(id):
    produto = Produto.find_by_id(id)
    return render_template("formulario_produto.html", produto=produto)

@app.route("/produto/atualizar/<int:id>", methods=["POST"])
def atualizar_produto(id):
    dados = {
        "sku": request.form.get("sku"),
        "nome": request.form.get("nome"),
        "descricao": request.form.get("descricao"),
        "categoria": request.form.get("categoria"),
        "unidade_medida": request.form.get("unidade_medida"),
        "preco_custo": to_float(request.form.get("preco_custo")),
        "preco_venda": to_float(request.form.get("preco_venda"))
    }

    produto = Produto(**dados)
    erros = produto.validate()

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return render_template("formulario_produto.html", produto=produto)

    try:
        Produto.update(id, dados)
        flash("Produto atualizado com sucesso!", "sucesso")
        return redirect(url_for("produtos"))
    except Exception as e:
        flash(f"Erro ao atualizar produto: {e}", "erro")
        return render_template("formulario_produto.html", produto=produto)

@app.route("/produto/desativar/<int:id>")
def desativar_produto(id):
    try:
        Produto.desativar(id)
        flash("Produto desativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("produtos"))

@app.route("/produto/reativar/<int:id>")
def reativar_produto(id):
    try:
        Produto.reativar(id)
        flash("Produto reativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("produtos_inativos"))

@app.route("/produtos/inativos")
def produtos_inativos():
    produtos = Produto.find_inativos()
    return render_template("produtos_inativos.html", produtos=produtos)

@app.route("/produto/excluir/<int:id>")
def excluir_produto(id):
    try:
        Produto.safe_delete(id)
        flash("Produto excluído com sucesso!", "sucesso")
    except ValueError as e:
        flash(str(e), "erro")
    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("produtos"))

# ---------------- ESTOQUE ---------------- #

@app.route("/estoque")
def estoque():
    return render_template("estoque.html")

# ---------------- FORNECEDORES ---------------- #

@app.route("/fornecedores")
def fornecedores():
    return render_template("fornecedores.html", fornecedores=Fornecedor.find_all())

@app.route("/fornecedor/novo")
def novo_fornecedor():
    return render_template("form_fornecedor.html")

@app.route("/fornecedor/salvar", methods=["POST"])
def salvar_fornecedor():
    try:
        fornecedor = Fornecedor(
            nome=request.form.get("nome"),
            telefone=request.form.get("telefone"),
            email=request.form.get("email")
        )
        fornecedor.insert()
        flash("Fornecedor cadastrado!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("fornecedores"))

# ---------------- CLIENTES ---------------- #

@app.route("/clientes")
def clientes():
    return render_template("clientes.html", clientes=Cliente.find_all())

@app.route("/cliente/novo")
def novo_cliente():
    return render_template("form_cliente.html")

@app.route("/cliente/salvar", methods=["POST"])
def salvar_cliente():
    try:
        cliente = Cliente(
            nome=request.form.get("nome"),
            cpf_cnpj=request.form.get("cpf"),
            email=request.form.get("email")
        )
        cliente.insert()
        flash("Cliente cadastrado!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("clientes"))

# ---------------- FUNCIONÁRIOS ---------------- #

@app.route("/funcionarios")
def funcionarios():
    return render_template("funcionarios.html", funcionarios=Funcionario.find_all())

@app.route("/funcionario/novo")
def novo_funcionario():
    return render_template("form_funcionario.html")

@app.route("/funcionario/salvar", methods=["POST"])
def salvar_funcionario():
    try:
        funcionario = Funcionario(
            nome=request.form.get("nome"),
            cargo=request.form.get("cargo")
        )
        funcionario.insert()
        flash("Funcionário cadastrado!", "sucesso")
    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("funcionarios"))

# ---------------- MOVIMENTAÇÕES ---------------- #

@app.route("/movimentacoes")
def movimentacoes():
    return render_template(
        "movimentacoes.html",
        movimentacoes=Movimentacao.find_all_with_product()
    )

@app.route("/movimentacao/nova")
def nova_movimentacao():
    produtos = Produto.find_all()
    return render_template("form_movimentacao.html", produtos=produtos)

@app.route("/movimentacao/salvar", methods=["POST"])
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

        if resultado:
            atual = resultado[0]
        else:
            atual = 0
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade)
                VALUES (%s, %s, 0)
            """, (produto_id, galpao_id))

        if tipo == "entrada":
            nova_qtd = atual + quantidade
        elif tipo == "saida":
            nova_qtd = atual - quantidade
        else:
            nova_qtd = atual

        cursor.execute("""
            UPDATE estoque 
            SET quantidade = %s 
            WHERE produto_id = %s AND galpao_id = %s
        """, (nova_qtd, produto_id, galpao_id))

        conexao.commit()
        conexao.close()

        flash("Movimentação registrada!", "sucesso")

    except Exception as e:
        flash(f"Erro: {e}", "erro")

    return redirect(url_for("movimentacoes"))

# ---------------- PEDIDOS ---------------- #

@app.route("/pedidos")
def pedidos():
    return render_template(
        "pedidos.html",
        pedidos=PedidoMovimentacao.find_all_with_product()
    )

@app.route("/pedido/novo/<int:produto_id>/<tipo>")
def novo_pedido(produto_id, tipo):
    produto = Produto.find_by_id(produto_id)
    return render_template("formulario_pedido.html", produto=produto, tipo=tipo)

@app.route("/pedido/salvar", methods=["POST"])
def salvar_pedido():
    dados = {
        "produto_id": int(request.form.get("produto_id")),
        "tipo": request.form.get("tipo").upper(),
        "quantidade": int(request.form.get("quantidade")),
        "observacao": request.form.get("observacao")
    }

    try:
        PedidoMovimentacao.create(dados)
        flash("Pedido criado com sucesso!", "sucesso")
        return redirect(url_for("pedidos"))
    except Exception as e:
        flash(f"Erro ao criar pedido: {e}", "erro")
        return redirect(url_for("produtos"))

@app.route("/pedido/processar/<int:id>")
def processar_pedido(id):
    try:
        PedidoMovimentacao.processar(id)
        flash("Pedido processado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao processar pedido: {e}", "erro")

    return redirect(url_for("pedidos"))

@app.route("/pedido/cancelar/<int:id>")
def cancelar_pedido(id):
    try:
        PedidoMovimentacao.cancelar(id)
        flash("Pedido cancelado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao cancelar pedido: {e}", "erro")

    return redirect(url_for("pedidos"))

# ---------------- LOGIN ---------------- #

@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/login", methods=["POST"])
def autenticar():
    usuario = request.form.get("usuario")
    senha = request.form.get("senha")

    if usuario == "admin" and senha == "123":
        flash("Login realizado!", "sucesso")
        return redirect(url_for("index"))

    flash("Login inválido!", "erro")
    return redirect(url_for("login"))

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    app.run(debug=True)