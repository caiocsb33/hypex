from core.database import Database
from core.empresa import empresa_atual


class Cliente:

    def __init__(self, nome, empresa, ativo, cidade, estado,
                 cpf_cnpj, cep, email, telefone):
        self.nome = nome
        self.empresa = empresa
        self.ativo = ativo
        self.cidade = cidade
        self.estado = estado
        self.cpf_cnpj = cpf_cnpj
        self.cep = cep
        self.email = email
        self.telefone = telefone

    def insert(self):
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO cliente
                (empresa_id, nome, empresa, ativo, cidade, estado, cpf_cnpj, cep, email, telefone)
                VALUES (%s, %s, %s, %s,%s, %s, %s, %s, %s, %s)
            """, (
                empresa_atual(), self.nome, self.empresa, self.ativo, self.cidade, self.estado,
                self.cpf_cnpj, self.cep, self.email, self.telefone
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def find_all():
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM cliente WHERE empresa_id = %s ORDER BY nome",
                           (empresa_atual(),))
            return cursor.fetchall()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def find_by_id(id):
        conn = Database.connect()
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute("SELECT * FROM cliente WHERE id = %s AND empresa_id = %s",
                           (id, empresa_atual()))
            return cursor.fetchone()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def update(cliente_id, dados):
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE cliente SET
                    nome = %s,
                    empresa = %s,
                    email = %s,
                    telefone = %s,
                    cep = %s,
                    cidade = %s,
                    estado = %s,
                    ativo = %s,
                    cpf_cnpj = %s
                WHERE id = %s AND empresa_id = %s
            """, (
                dados["nome"], dados["empresa"], dados["email"],
                dados["telefone"], dados["cep"], dados["cidade"],
                dados["estado"], dados["ativo"],
                # Documento vazio fica nulo: a coluna é única e o vazio
                # repetido bloquearia o segundo cliente sem documento.
                dados.get("cpf_cnpj") or None,
                cliente_id, empresa_atual()
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

    @staticmethod
    def delete(cliente_id):
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM cliente WHERE id = %s AND empresa_id = %s",
                           (cliente_id, empresa_atual()))
            conn.commit()
        finally:
            cursor.close()
            conn.close()