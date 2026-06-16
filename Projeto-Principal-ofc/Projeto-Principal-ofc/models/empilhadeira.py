from core.database import Database


# Classe responsável por representar e manipular empilhadeiras no banco de dados
class Empilhadeira:

    # Construtor da classe Empilhadeira
    # Inicializa os atributos principais da empilhadeira
    def __init__(self, modelo, capacidade, funcionario_id):
        self.modelo = modelo
        self.capacidade = capacidade
        self.funcionario_id = funcionario_id


    # Insere uma nova empilhadeira no banco de dados
    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO empilhadeira (modelo, capacidade, funcionario_id) VALUES (%s,%s,%s)",
            (self.modelo, self.capacidade, self.funcionario_id)
        )

        conn.commit()
        conn.close()


    # Busca e retorna todas as empilhadeiras cadastradas
    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM empilhadeira")
        return cursor.fetchall()