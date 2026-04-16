from core.database import Database

class Empilhadeira:
    def __init__(self, modelo, capacidade, funcionario_id):
        self.modelo = modelo
        self.capacidade = capacidade
        self.funcionario_id = funcionario_id

    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO empilhadeira (modelo, capacidade, funcionario_id) VALUES (%s,%s,%s)",
                       (self.modelo, self.capacidade, self.funcionario_id))
        conn.commit()
        conn.close()

    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM empilhadeira")
        return cursor.fetchall()