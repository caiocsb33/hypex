from core.crud_base import CrudBase
from core.database import Database
from core.validator import Validator


# Classe responsável por representar e manipular produtos no sistema
class Produto(CrudBase):

    # Define a tabela associada no banco de dados
    table = "produto"

    # Define os campos utilizados em operações de INSERT e UPDATE
    fields = [
        "sku",
        "nome",
        "descricao",
        "categoria",
        "unidade_medida",
        "preco_custo",
        "preco_venda"
    ]


    # Construtor da classe Produto
    # Inicializa os atributos principais do produto
    def __init__(self, sku, nome, descricao, categoria, unidade_medida,
                 preco_custo, preco_venda):
        self.sku = sku
        self.nome = nome
        self.descricao = descricao
        self.categoria = categoria
        self.unidade_medida = unidade_medida
        self.preco_custo = preco_custo
        self.preco_venda = preco_venda


    # Valida os dados do produto antes de salvar
    def validate(self):
        erros = [
            Validator.required(self.sku, "sku"),
            Validator.required(self.nome, "nome"),
            Validator.non_negative(self.preco_custo, "preço de custo"),
            Validator.non_negative(self.preco_venda, "preço de venda")
        ]

        return [erro for erro in erros if erro]


    # Atualiza os dados de um produto existente
    @classmethod
    def update(cls, id, dados):
        conexao = Database.connect()
        cursor = conexao.cursor()

        try:
            sql = """
                UPDATE produto SET
                    sku = %s,
                    nome = %s,
                    descricao = %s,
                    categoria = %s,
                    unidade_medida = %s,
                    preco_custo = %s,
                    preco_venda = %s
                WHERE id = %s
            """

            valores = (
                dados["sku"],
                dados["nome"],
                dados["descricao"],
                dados["categoria"],
                dados["unidade_medida"],
                dados["preco_custo"],
                dados["preco_venda"],
                id
            )

            cursor.execute(sql, valores)
            conexao.commit()

        finally:
            cursor.close()
            conexao.close()


    # Retorna produtos com estoque abaixo ou igual ao mínimo definido
    @classmethod
    def low_stock(cls):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)
        try:
            sql = """
                SELECT p.*, e.quantidade, e.estoque_minimo
                FROM produto p
                JOIN estoque e ON p.id = e.produto_id
                WHERE e.quantidade <= e.estoque_minimo
                ORDER BY p.nome
            """

            cursor.execute(sql)
            return cursor.fetchall()

        finally:
            cursor.close()
            conexao.close()


    # Verifica se o produto possui registros relacionados em outras tabelas
    @classmethod
    def has_related_records(cls, id):
        conexao = Database.connect()
        cursor = conexao.cursor()
        try:
            queries = [
                "SELECT COUNT(*) FROM movimentacao WHERE produto_id = %s",
                "SELECT COUNT(*) FROM item_pedido_cliente WHERE produto_id = %s",
                "SELECT COUNT(*) FROM item_pedido_fornecedor WHERE produto_id = %s"
            ]

            total = 0

            for sql in queries:
                cursor.execute(sql, (id,))
                total += cursor.fetchone()[0]

            return total > 0

        finally:
            cursor.close()
            conexao.close()


    # Desativa um produto
    @classmethod
    def desativar(cls, id):
        conexao = Database.connect()
        cursor = conexao.cursor()
        try:
            cursor.execute(
                "UPDATE produto SET ativo = FALSE WHERE id = %s",
                (id,)
            )

            conexao.commit()

        finally:
            cursor.close()
            conexao.close()


    # Reativa um produto desativado
    @classmethod
    def reativar(cls, id):
        conexao = Database.connect()
        cursor = conexao.cursor()
        try:
            cursor.execute(
                "UPDATE produto SET ativo = TRUE WHERE id = %s",
                (id,)
            )

            conexao.commit()

        finally:
            cursor.close()
            conexao.close()


    # Exclui um produto com validações de segurança
    @classmethod
    def safe_delete(cls, id):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            # Busca o produto pelo ID
            cursor.execute("SELECT * FROM produto WHERE id = %s", (id,))
            produto = cursor.fetchone()

            if not produto:
                raise ValueError("Produto não encontrado.")

            if produto["ativo"]:
                raise ValueError("Desative o produto antes de excluir.")


            # Remove diretamente se não houver dependências
            if not cls.has_related_records(id):
                cursor.execute("DELETE FROM produto WHERE id = %s", (id,))
                conexao.commit()
                return


            # Remove registros relacionados antes de excluir o produto
            cursor.execute("DELETE FROM movimentacao WHERE produto_id = %s", (id,))
            cursor.execute("DELETE FROM item_pedido_cliente WHERE produto_id = %s", (id,))
            cursor.execute("DELETE FROM item_pedido_fornecedor WHERE produto_id = %s", (id,))
            cursor.execute("DELETE FROM produto WHERE id = %s", (id,))

            conexao.commit()

        except Exception:
            conexao.rollback()
            raise

        finally:
            cursor.close()
            conexao.close()


    # Retorna todos os produtos inativos
    @classmethod
    def find_inativos(cls):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)
        try:
            cursor.execute(
                "SELECT * FROM produto WHERE ativo = FALSE ORDER BY nome"
            )

            return cursor.fetchall()

        finally:
            cursor.close()
            conexao.close()


    # Retorna a soma total de itens em estoque
    @classmethod
    def total_estoque(cls):
        conexao = Database.connect()
        cursor = conexao.cursor()
        try:
            cursor.execute("SELECT SUM(quantidade) FROM estoque")

            resultado = cursor.fetchone()[0]
            return resultado if resultado else 0

        finally:
            cursor.close()
            conexao.close()