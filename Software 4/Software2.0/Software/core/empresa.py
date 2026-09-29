from flask import session


def empresa_atual():
    """Empresa (cliente do SaaS) logada. Toda consulta de dados filtra por ela."""
    return session.get("empresa_id")
