from core.database import Database

class Galpao:
    def __init__(self, nome, endereco_id):
        self.nome = nome
        self.endereco_id = endereco_id

    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO galpao (nome, endereco_id) VALUES (%s,%s)",
                       (self.nome, self.endereco_id))
        conn.commit()
        conn.close()

    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM galpao")
        return cursor.fetchall()