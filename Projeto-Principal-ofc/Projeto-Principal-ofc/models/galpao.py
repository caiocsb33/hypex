from core.database import Database


# Classe responsável por representar e manipular galpões no banco de dados
class Galpao:

    # Construtor da classe Galpao
    # Inicializa os atributos principais do galpão
    def __init__(self, nome, endereco_id):
        self.nome = nome
        self.endereco_id = endereco_id


    # Insere um novo galpão no banco de dados
    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO galpao (nome, endereco_id) VALUES (%s,%s)",
            (self.nome, self.endereco_id)
        )

        conn.commit()
        conn.close()


    # Busca e retorna todos os galpões cadastrados
    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM galpao")
        return cursor.fetchall()