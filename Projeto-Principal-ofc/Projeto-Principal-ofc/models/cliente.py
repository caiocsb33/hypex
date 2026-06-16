from core.database import Database


# Classe responsável por representar e manipular clientes no banco de dados
class Cliente:

    # Construtor da classe Cliente
    # Inicializa os atributos principais do cliente
    def __init__(self, nome, cpf_cnpj, email):
        self.nome = nome
        self.cpf_cnpj = cpf_cnpj
        self.email = email


    # Insere um novo cliente no banco de dados
    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO cliente (nome, cpf_cnpj, email) VALUES (%s,%s,%s)",
            (self.nome, self.cpf_cnpj, self.email)
        )

        conn.commit()
        conn.close()


    # Busca e retorna todos os clientes cadastrados
    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM cliente")
        data = cursor.fetchall()

        conn.close()
        return data