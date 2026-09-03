from datetime import datetime
from core.crud_base import CrudBase
from core.database import Database


# Classe responsável por representar e manipular movimentações de estoque
class Movimentacao(CrudBase):

    # Define a tabela associada no banco de dados
    table = "movimentacao"

    # Define os campos utilizados em operações de INSERT e UPDATE
    # Os nomes seguem exatamente as colunas da tabela `movimentacao` (banco.sql)
    fields = [
        "produto_id",
        "galpao_id",
        "galpao_destino_id",
        "funcionario_id",
        "tipo",
        "quantidade",
        "data_movimentacao",
        "observacao",
    ]

    # Tipos aceitos pelo ENUM da coluna `tipo`
    TIPOS = ("entrada", "saida", "transferencia", "ajuste_inventario")

    # Construtor da classe Movimentacao
    # Inicializa os atributos da movimentação
    def __init__(self, produto_id, galpao_id, tipo, quantidade,
                 galpao_destino_id=None, funcionario_id=None,
                 data_movimentacao=None, observacao=None):
        self.produto_id = produto_id
        self.galpao_id = galpao_id
        self.galpao_destino_id = galpao_destino_id or None
        self.funcionario_id = funcionario_id or None
        self.tipo = tipo
        self.quantidade = quantidade
        self.observacao = observacao

        # Usa a data/hora atual caso nenhuma seja informada
        self.data_movimentacao = data_movimentacao or datetime.now()

    # Valida os dados antes de gravar no banco
    def validate(self):
        erros = []

        if not self.produto_id:
            erros.append("Selecione o produto.")

        if not self.galpao_id:
            erros.append("Selecione o galpão de origem.")

        if self.tipo not in self.TIPOS:
            erros.append("Tipo de movimentação inválido.")

        try:
            if float(self.quantidade) <= 0:
                erros.append("A quantidade deve ser maior que zero.")
        except (TypeError, ValueError):
            erros.append("A quantidade deve ser numérica.")

        if self.tipo == "transferencia" and not self.galpao_destino_id:
            erros.append("Informe o galpão de destino da transferência.")

        if self.tipo == "transferencia" and self.galpao_destino_id == self.galpao_id:
            erros.append("O galpão de destino deve ser diferente do de origem.")

        return erros

    # Busca todas as movimentações já com os nomes relacionados resolvidos,
    # para que o template não precise fazer consultas extras.
    @classmethod
    def find_all_with_product(cls, produto_id=None, galpao_id=None, tipo=None):
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)
        try:
            sql = """
            SELECT
                m.id,
                m.tipo,
                m.quantidade,
                m.data_movimentacao,
                m.observacao,
                p.nome        AS produto,
                p.sku         AS produto_sku,
                g.nome        AS galpao,
                gd.nome       AS galpao_destino,
                fu.nome       AS funcionario
            FROM movimentacao m
            INNER JOIN produto p  ON m.produto_id        = p.id
            LEFT  JOIN galpao g   ON m.galpao_id         = g.id
            LEFT  JOIN galpao gd  ON m.galpao_destino_id = gd.id
            LEFT  JOIN funcionario fu ON m.funcionario_id = fu.id
            WHERE 1 = 1
            """
            valores = []

            if produto_id:
                sql += " AND m.produto_id = %s"
                valores.append(produto_id)

            if galpao_id:
                sql += " AND (m.galpao_id = %s OR m.galpao_destino_id = %s)"
                valores.extend([galpao_id, galpao_id])

            if tipo in cls.TIPOS:
                sql += " AND m.tipo = %s"
                valores.append(tipo)

            sql += " ORDER BY m.data_movimentacao DESC, m.id DESC"

            cursor.execute(sql, tuple(valores))
            return cursor.fetchall()

        finally:
            cursor.close()
            conexao.close()
