from core.database import Database

class Funcionario:
    def __init__(self, nome, cargo):
        self.nome = nome
        self.cargo = cargo

    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO funcionario (nome, cargo) VALUES (%s,%s)",
                       (self.nome, self.cargo))
        conn.commit()
        conn.close()

    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM funcionario")
        return cursor.fetchall()