from core.database import Database


# Classe responsável por representar e manipular funcionários no banco de dados
class Funcionario:

    # Construtor da classe Funcionario
    # Inicializa os atributos principais do funcionário
    def __init__(self, nome, cargo):
        self.nome = nome
        self.cargo = cargo


    # Insere um novo funcionário no banco de dados
    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO funcionario (nome, cargo) VALUES (%s,%s)",
            (self.nome, self.cargo)
        )

        conn.commit()
        conn.close()


    # Busca e retorna todos os funcionários cadastrados
    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM funcionario")
        return cursor.fetchall()