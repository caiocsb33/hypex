from core.database import Database


# Classe responsável por representar e manipular fornecedores no banco de dados
class Fornecedor:

    # Construtor da classe Fornecedor
    # Inicializa os atributos principais do fornecedor
    def __init__(self, nome, telefone, email):
        self.nome = nome
        self.telefone = telefone
        self.email = email


    # Insere um novo fornecedor no banco de dados
    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO fornecedor (nome, telefone, email) VALUES (%s,%s,%s)",
            (self.nome, self.telefone, self.email)
        )

        conn.commit()
        conn.close()


    # Busca e retorna todos os fornecedores cadastrados
    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM fornecedor")
        return cursor.fetchall()