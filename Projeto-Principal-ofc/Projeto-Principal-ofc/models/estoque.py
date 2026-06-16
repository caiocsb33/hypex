from core.database import Database


# Classe responsável por controlar operações relacionadas ao estoque
class Estoque:


    # Busca todos os registros de estoque de um produto específico
    @staticmethod
    def find_by_produto(produto_id):
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT * FROM estoque 
                WHERE produto_id = %s
            """, (produto_id,))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()


    # Retorna a quantidade disponível de um produto em um galpão específico
    @staticmethod
    def get_quantidade(produto_id, galpao_id):
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT quantidade FROM estoque 
                WHERE produto_id = %s AND galpao_id = %s
            """, (produto_id, galpao_id))

            resultado = cursor.fetchone()
            return resultado[0] if resultado else 0

        finally:
            cursor.close()
            conn.close()


    # Cria um registro de estoque caso ele ainda não exista para o produto/galpão
    @staticmethod
    def criar_se_nao_existir(produto_id, galpao_id):
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                SELECT id FROM estoque 
                WHERE produto_id = %s AND galpao_id = %s
            """, (produto_id, galpao_id))

            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                    VALUES (%s, %s, 0, 0)
                """, (produto_id, galpao_id))

                conn.commit()

        finally:
            cursor.close()
            conn.close()


    # Atualiza diretamente a quantidade de um item no estoque
    @staticmethod
    def atualizar_quantidade(produto_id, galpao_id, nova_quantidade):
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE estoque 
                SET quantidade = %s 
                WHERE produto_id = %s AND galpao_id = %s
            """, (nova_quantidade, produto_id, galpao_id))

            conn.commit()

        finally:
            cursor.close()
            conn.close()


    # Realiza movimentação de entrada ou saída no estoque
    @staticmethod
    def movimentar(produto_id, galpao_id, quantidade, tipo):
        conn = Database.connect()
        cursor = conn.cursor()
        try:

            # Verifica se já existe registro de estoque para o produto/galpão
            cursor.execute("""
                SELECT quantidade FROM estoque 
                WHERE produto_id = %s AND galpao_id = %s
            """, (produto_id, galpao_id))

            resultado = cursor.fetchone()

            if resultado:
                atual = resultado[0]
            else:
                atual = 0

                # Cria registro inicial de estoque se não existir
                cursor.execute("""
                    INSERT INTO estoque (produto_id, galpao_id, quantidade)
                    VALUES (%s, %s, 0)
                """, (produto_id, galpao_id))


            # Calcula a nova quantidade com base no tipo de movimentação
            if tipo == "entrada":
                nova_qtd = atual + quantidade

            elif tipo == "saida":
                if atual < quantidade:
                    raise ValueError("Estoque insuficiente.")

                nova_qtd = atual - quantidade

            else:
                nova_qtd = atual


            # Atualiza a quantidade final no banco de dados
            cursor.execute("""
                UPDATE estoque 
                SET quantidade = %s 
                WHERE produto_id = %s AND galpao_id = %s
            """, (nova_qtd, produto_id, galpao_id))

            conn.commit()

        except Exception:
            conn.rollback()
            raise

        finally:
            cursor.close()
            conn.close()


    # Gera um resumo consolidado do estoque total por produto
    @staticmethod
    def resumo_geral():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT p.nome, SUM(e.quantidade) as total
                FROM estoque e
                JOIN produto p ON p.id = e.produto_id
                GROUP BY p.id
                ORDER BY p.nome
            """)

            return cursor.fetchall()

        finally:
            cursor.close()
            conn.close()