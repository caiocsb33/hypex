from datetime import datetime
from core.crud_base import CrudBase
from core.database import Database
from core.validator import Validator
from models.produto import Produto
from models.movimentacao import Movimentacao

class PedidoMovimentacao(CrudBase):
    table = "pedido_movimentacao"
    fields = [
        "produto_id",
        "tipo",
        "quantidade",
        "status",
        "observacao",
        "data_pedido",
        "data_processamento"
    ]

    def __init__(self, produto_id, tipo, quantidade, status="PENDENTE",
                 observacao="", data_pedido=None, data_processamento=None):
        self.produto_id = produto_id
        self.tipo = tipo
        self.quantidade = quantidade
        self.status = status
        self.observacao = observacao
        self.data_pedido = data_pedido or datetime.now()
        self.data_processamento = data_processamento

    def validate(self):
        erros = []

        erro_produto = Validator.positive(self.produto_id, "produto")
        if erro_produto:
            erros.append(erro_produto)

        erro_qtd = Validator.positive(self.quantidade, "quantidade")
        if erro_qtd:
            erros.append(erro_qtd)

        if self.tipo not in ["ENTRADA", "SAIDA"]:
            erros.append("O tipo deve ser ENTRADA ou SAIDA.")

        return erros

    @classmethod
    def create(cls, dados):
        conexao = Database.connect()
        cursor = conexao.cursor()

        try:
            sql = """
                INSERT INTO pedido_movimentacao 
                (produto_id, tipo, quantidade, status, observacao, data_pedido)
                VALUES (%s, %s, %s, %s, %s, %s)
            """

            valores = (
                dados["produto_id"],
                dados["tipo"],
                dados["quantidade"],
                "PENDENTE",
                dados["observacao"],
                datetime.now()
            )

            cursor.execute(sql, valores)
            conexao.commit()

        except Exception as e:
            conexao.rollback()
            raise e

        finally:
            cursor.close()
            conexao.close()

    @classmethod
    def find_all_with_product(cls):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)
        try:
            sql = """
            SELECT pm.*, p.nome AS produto
            FROM pedido_movimentacao pm
            INNER JOIN produto p ON pm.produto_id = p.id
            ORDER BY pm.data_pedido DESC
            """
            cursor.execute(sql)
            return cursor.fetchall()
        finally:
            cursor.close()
            conexao.close()

    @classmethod
    def processar(cls, id):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            conexao.start_transaction()

            cursor.execute("SELECT * FROM pedido_movimentacao WHERE id = %s FOR UPDATE", (id,))
            pedido = cursor.fetchone()

            if not pedido:
                raise ValueError("Pedido não encontrado.")

            if pedido["status"] != "PENDENTE":
                raise ValueError("Somente pedidos pendentes podem ser processados.")

            cursor.execute("SELECT * FROM produto WHERE id = %s FOR UPDATE", (pedido["produto_id"],))
            produto = cursor.fetchone()

            if not produto:
                raise ValueError("Produto não encontrado.")

            quantidade = int(pedido["quantidade"])

            if pedido["tipo"] == "ENTRADA":
                nova_quantidade = produto["quantidade"] + quantidade

            elif pedido["tipo"] == "SAIDA":
                if quantidade > produto["quantidade"]:
                    raise ValueError("Estoque insuficiente para saída.")
                nova_quantidade = produto["quantidade"] - quantidade

            else:
                raise ValueError("Tipo inválido.")

            Produto.update_quantity(produto["id"], nova_quantidade, connection=conexao)

            cursor.execute(
                """
                INSERT INTO movimentacao (produto_id, tipo_movimentacao, quantidade, data_movimentacao)
                VALUES (%s, %s, %s, %s)
                """,
                (produto["id"], pedido["tipo"], quantidade, datetime.now())
            )

            cursor.execute(
                """
                UPDATE pedido_movimentacao
                SET status = %s, data_processamento = %s
                WHERE id = %s
                """,
                ("PROCESSADO", datetime.now(), id)
            )

            conexao.commit()

        except Exception as e:
            conexao.rollback()
            raise e

        finally:
            cursor.close()
            conexao.close()

    @classmethod
    def cancelar(cls, id):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM pedido_movimentacao WHERE id = %s", (id,))
            pedido = cursor.fetchone()
            if not pedido:
                raise ValueError("Pedido não encontrado.")
            if pedido["status"] != "PENDENTE":
                raise ValueError("Somente pedidos pendentes podem ser cancelados.")

            cursor = conexao.cursor()
            cursor.execute(
                """
                UPDATE pedido_movimentacao
                SET status = %s, data_processamento = %s
                WHERE id = %s
                """,
                ("CANCELADO", datetime.now(), id)
            )
            conexao.commit()
            return "Pedido cancelado com sucesso."

        except Exception:
            conexao.rollback()
            raise
        finally:
            cursor.close()
            conexao.close()
