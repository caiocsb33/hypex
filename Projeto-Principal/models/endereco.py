from core.database import Database

class Endereco:
    def __init__(self, rua, cidade, estado, cep):
        self.rua = rua
        self.cidade = cidade
        self.estado = estado
        self.cep = cep

    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO endereco (rua, cidade, estado, cep) VALUES (%s,%s,%s,%s)",
                       (self.rua, self.cidade, self.estado, self.cep))
        conn.commit()
        conn.close()

    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM endereco")
        return cursor.fetchall()