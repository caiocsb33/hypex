from core.database import Database

class Fornecedor:
    def __init__(self, nome, telefone, email):
        self.nome = nome
        self.telefone = telefone
        self.email = email

    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO fornecedor (nome, telefone, email) VALUES (%s,%s,%s)",
                       (self.nome, self.telefone, self.email))
        conn.commit()
        conn.close()

    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM fornecedor")
        return cursor.fetchall()