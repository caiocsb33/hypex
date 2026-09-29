import os

# Conexão com o banco. Os valores abaixo são o padrão para desenvolvimento;
# em outro ambiente (servidor, outra porta, outra senha) use variáveis de
# ambiente em vez de editar este arquivo: DB_HOST, DB_PORT, DB_USER,
# DB_PASSWORD e DB_NAME.
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "3306")),
    "user": os.environ.get("DB_USER", "root"),
    "password": os.environ.get("DB_PASSWORD", "123456"),
    "database": os.environ.get("DB_NAME", "sistema_estoque"),
}
