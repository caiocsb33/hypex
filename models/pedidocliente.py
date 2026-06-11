from datetime import datetime
from core.crud_base import CrudBase
from core.database import Database
from core.validator import Validator


# Classe responsável por gerenciar pedidos de clientes
class PedidoCliente(CrudBase):

    # Define a tabela associada no banco de dados
    table = "pedido_cliente"

    # CORREÇÃO 1: fields alinhados com as colunas reais da tabela pedido_cliente
    fields = [
        "cliente_id",
        "produto_id",
        "produto_pedido",
        "valor_total",
        "status_pedido",
    ]

    # Construtor da classe PedidoCliente
    def __init__(self, cliente_id, produto_id, produto_pedido, valor_total, status_pedido="pendente"):
        self.cliente_id = cliente_id
        self.produto_id = produto_id
        self.produto_pedido = produto_pedido
        self.valor_total = valor_total
        self.status_pedido = status_pedido

    # Valida os dados do pedido antes de processar
    def validate(self):
        erros = []

        erro_cliente = Validator.positive(self.cliente_id, "cliente")
        if erro_cliente:
            erros.append(erro_cliente)

        erro_produto = Validator.positive(self.produto_id, "produto")
        if erro_produto:
            erros.append(erro_produto)

        erro_valor = Validator.positive(self.valor_total, "valor_total")
        if erro_valor:
            erros.append(erro_valor)

        return erros

    # Cria um novo pedido cliente no banco
    @classmethod
    def create(cls, dados):
        conexao = Database.connect()
        cursor = conexao.cursor()

        try:
            sql = """
                INSERT INTO pedido_cliente
                (cliente_id, produto_id, produto_pedido, valor_total, status_pedido)
                VALUES (%s, %s, %s, %s, %s)
            """

            valores = (
                dados["cliente_id"],
                dados["produto_id"],
                dados.get("produto_pedido"),
                dados["valor_total"],
                "pendente",
            )

            cursor.execute(sql, valores)
            conexao.commit()

        except Exception as e:
            conexao.rollback()
            raise e

        finally:
            cursor.close()
            conexao.close()

    # CORREÇÃO 2: query com JOIN para trazer nome e email do cliente
    @classmethod
    def find_by_cliente(cls, cliente_id):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT
                    pc.*,
                    c.nome  AS cliente_nome,
                    c.email AS cliente_email
                FROM pedido_cliente pc
                JOIN cliente c ON pc.cliente_id = c.id
                WHERE pc.cliente_id = %s
                ORDER BY pc.data_pedido DESC
            """, (cliente_id,))

            return cursor.fetchall()

        finally:
            # CORREÇÃO 3: cursor fechado antes da conexão, sem duplicação
            cursor.close()
            conexao.close()

    # Busca todos os pedidos com produto e cliente
    @classmethod
    def find_all_with_product(cls):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            sql = """
                SELECT
                    pc.id,
                    c.nome  AS cliente_nome,
                    p.nome  AS produto,
                    ip.quantidade,
                    pc.valor_total,
                    pc.status_pedido,
                    pc.data_pedido
                FROM pedido_cliente pc
                JOIN cliente c              ON pc.cliente_id = c.id
                JOIN item_pedido_cliente ip ON pc.id = ip.pedido_cliente_id
                JOIN produto p              ON ip.produto_id = p.id
                ORDER BY pc.data_pedido DESC
            """

            cursor.execute(sql)
            return cursor.fetchall()

        finally:
            cursor.close()
            conexao.close()

    # Cancela um pedido pendente
    @classmethod
    def cancelar(cls, id):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            cursor.execute(
                "SELECT * FROM pedido_cliente WHERE id = %s",
                (id,)
            )
            pedido = cursor.fetchone()

            if not pedido:
                raise ValueError("Pedido não encontrado.")

            if pedido["status_pedido"] != "pendente":
                raise ValueError("Somente pedidos pendentes podem ser cancelados.")

            cursor.execute(
                """
                UPDATE pedido_cliente
                SET status_pedido = %s, updated_at = %s
                WHERE id = %s
                """,
                ("cancelado", datetime.now(), id)
            )

            conexao.commit()
            return "Pedido cancelado com sucesso."

        except Exception:
            conexao.rollback()
            raise

        finally:
            cursor.close()
            conexao.close()