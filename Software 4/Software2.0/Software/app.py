
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from core.database import Database
import json
from models.estoque import Estoque
from models.galpao import Galpao
from models.produto import Produto
from models.movimentacao import Movimentacao
from models.pedidocliente import PedidoCliente
from models.fornecedor import Fornecedor
from models.cliente import Cliente
from models.funcionario import Funcionario
from models.endereco import Endereco
from models.empilhadeira import Empilhadeira
import re
import secrets
from datetime import datetime, timedelta
import os
import io

app = Flask(__name__)

def carregar_chave_secreta():
    """Chave que assina a sessão.

    Uma chave aleatória a cada inicialização derrubava o login de todo mundo
    sempre que o servidor reiniciava (e não funciona com mais de um processo).
    Sem FLASK_SECRET_KEY no ambiente, a chave é gerada uma vez e guardada em
    instance/secret_key, fora do versionamento.
    """
    chave = os.environ.get("FLASK_SECRET_KEY")
    if chave:
        return chave

    pasta = os.path.join(os.path.dirname(os.path.abspath(__file__)), "instance")
    arquivo = os.path.join(pasta, "secret_key")
    try:
        with open(arquivo) as f:
            chave = f.read().strip()
    except FileNotFoundError:
        chave = ""
    if not chave:
        os.makedirs(pasta, exist_ok=True)
        chave = secrets.token_hex(32)
        with open(arquivo, "w") as f:
            f.write(chave)
    return chave


app.secret_key = carregar_chave_secreta()

# O cookie de sessão não vai junto em POSTs vindos de outros sites e não é
# acessível por JavaScript.
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_HTTPONLY=True,
)


@app.before_request
def bloquear_post_de_outro_site():
    """Proteção contra CSRF.

    Sem isso, uma página de outro site podia enviar um formulário escondido
    para /produto/desativar/1, /cliente/deletar/1... usando a sessão de
    quem estivesse logado. Todo POST precisa vir do próprio sistema:
    o navegador informa a origem no cabeçalho Origin (ou Referer).
    """
    if request.method != "POST":
        return None

    origem = request.headers.get("Origin") or request.headers.get("Referer")
    if not origem:
        # Clientes sem navegador (testes, scripts internos) não mandam origem
        return None

    from urllib.parse import urlparse
    if urlparse(origem).netloc != request.host:
        abort(403)
    return None


@app.after_request
def cabecalhos_de_seguranca(resposta):
    # Não deixa outro site abrir o sistema dentro de um iframe (clickjacking)
    resposta.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    # O navegador respeita o tipo do arquivo (imagens enviadas não viram script)
    resposta.headers.setdefault("X-Content-Type-Options", "nosniff")
    resposta.headers.setdefault("Referrer-Policy", "same-origin")
    return resposta


# ------------ LIMITE DE TENTATIVAS DE LOGIN ----------#
# Em memória: suficiente para um processo. Com vários servidores, trocar por
# uma tabela ou Redis.
TENTATIVAS_LOGIN = {}
LIMITE_TENTATIVAS = 5
JANELA_BLOQUEIO = timedelta(minutes=15)


def _chave_login(email):
    return (email or "").lower(), request.remote_addr


def login_bloqueado(email):
    """Minutos restantes de bloqueio, ou 0."""
    falhas = [t for t in TENTATIVAS_LOGIN.get(_chave_login(email), [])
              if datetime.now() - t < JANELA_BLOQUEIO]
    TENTATIVAS_LOGIN[_chave_login(email)] = falhas
    if len(falhas) >= LIMITE_TENTATIVAS:
        restante = JANELA_BLOQUEIO - (datetime.now() - falhas[0])
        return max(1, int(restante.total_seconds() // 60) + 1)
    return 0


def registrar_falha_login(email):
    TENTATIVAS_LOGIN.setdefault(_chave_login(email), []).append(datetime.now())


def limpar_falhas_login(email):
    TENTATIVAS_LOGIN.pop(_chave_login(email), None)


# ---------------- NOTIFICAÇÕES ---------------- #

# Preferências guardadas na tabela empresa (valem para toda a equipe).
# coluna -> (valor padrão, rótulo, explicação)
PREFERENCIAS_NOTIFICACAO = {
    "notif_estoque_baixo": (1, "Estoque baixo",
                            "Avisar quando o saldo chegar no mínimo ou abaixo dele"),
    "notif_sem_estoque": (1, "Sem estoque",
                          "Avisar quando o saldo zerar"),
    "notif_incluir_inativos": (1, "Incluir produtos inativos",
                               "Também avisar sobre produtos desativados que ainda têm saldo cadastrado"),
    "notif_pedidos_pendentes": (1, "Pedidos pendentes",
                                "Avisar sobre pedidos de saída aguardando andamento"),
}
# Aviso antecipado: avisa quando o saldo estiver até X% acima do mínimo
MARGEM_PADRAO = 0


def preferencias_notificacao(cursor, empresa_id):
    colunas = ", ".join(list(PREFERENCIAS_NOTIFICACAO) + ["notif_margem"])
    try:
        cursor.execute(f"SELECT {colunas} FROM empresa WHERE id = %s", (empresa_id,))
        linha = cursor.fetchone() or {}
    except Exception:
        linha = {}
    prefs = {c: bool(linha.get(c, p[0]) if linha.get(c) is not None else p[0])
             for c, p in PREFERENCIAS_NOTIFICACAO.items()}
    prefs["notif_margem"] = int(linha.get("notif_margem") or MARGEM_PADRAO)
    return prefs


def alertas_estoque(cursor, empresa_id, prefs=None, limite=None):
    """Saldos que precisam de atenção, por galpão.

    É a regra única usada pelo sininho e pelo dashboard. Antes os dois só
    olhavam produtos com ativo = TRUE, e um produto desativado (ou com a
    situação em branco) sumia dos alertas mesmo aparecendo abaixo do mínimo
    na tela de estoque.
    """
    prefs = prefs or preferencias_notificacao(cursor, empresa_id)
    condicoes = []
    if prefs["notif_estoque_baixo"]:
        condicoes.append(
            "(e.quantidade > 0 AND e.estoque_minimo > 0 "
            "AND e.quantidade <= e.estoque_minimo * (1 + %s / 100))"
        )
    if prefs["notif_sem_estoque"]:
        condicoes.append("(e.quantidade <= 0)")
    if not condicoes:
        return []

    sql = f"""
        SELECT p.id AS produto_id, p.nome, p.sku,
               COALESCE(p.ativo, 1) AS ativo,
               g.nome AS galpao, e.quantidade, e.estoque_minimo
        FROM estoque e
        JOIN produto p     ON p.id = e.produto_id
        LEFT JOIN galpao g ON g.id = e.galpao_id
        WHERE p.empresa_id = %s
          AND ({' OR '.join(condicoes)})
    """
    valores = [empresa_id]
    if prefs["notif_estoque_baixo"]:
        valores.append(prefs["notif_margem"])
    if not prefs["notif_incluir_inativos"]:
        sql += " AND COALESCE(p.ativo, 1) = 1"
    sql += " ORDER BY (e.quantidade - e.estoque_minimo), p.nome"
    if limite:
        sql += f" LIMIT {int(limite)}"

    cursor.execute(sql, tuple(valores))
    return cursor.fetchall()


def montar_notificacoes(cursor, empresa_id):
    """Lista pronta para o sininho: estoque e pedidos pendentes."""
    prefs = preferencias_notificacao(cursor, empresa_id)
    itens = []

    for a in alertas_estoque(cursor, empresa_id, prefs):
        zerado = to_float(a["quantidade"]) <= 0
        abaixo = to_float(a["quantidade"]) <= to_float(a["estoque_minimo"])
        itens.append({
            "icone": "bi-x-octagon-fill" if zerado else "bi-exclamation-triangle-fill",
            "cor": "perigo" if zerado else ("alerta" if abaixo else "aviso"),
            "titulo": a["nome"],
            "texto": "sem estoque" if zerado else ("com estoque baixo" if abaixo else "perto do mínimo"),
            "detalhe": f'{fmt_quantidade(a["quantidade"])} de mínimo {fmt_quantidade(a["estoque_minimo"])}'
                       + (f' · {a["galpao"]}' if a["galpao"] else "")
                       + ("" if a["ativo"] else " · inativo"),
            "link": url_for("info_produtos", id=a["produto_id"]),
        })

    if prefs["notif_pedidos_pendentes"]:
        cursor.execute("""
            SELECT pc.id, pc.cliente_id, pc.valor_total, c.nome AS cliente
            FROM pedido_cliente pc
            LEFT JOIN cliente c ON c.id = pc.cliente_id
            WHERE pc.empresa_id = %s AND pc.status_pedido = 'pendente'
            ORDER BY pc.data_pedido
        """, (empresa_id,))
        for p in cursor.fetchall():
            itens.append({
                "icone": "bi-hourglass-split",
                "cor": "info",
                "titulo": f'Pedido #{p["id"]}',
                "texto": "pendente",
                "detalhe": f'{p["cliente"] or "Cliente"} · R$ {fmt_moeda(p["valor_total"])}',
                "link": url_for("info_pedido_cliente", pedido_id=p["id"]),
            })

    return itens


def fmt_quantidade(valor):
    numero = to_float(valor)
    return str(int(numero)) if numero == int(numero) else f"{numero:.3f}".rstrip("0").replace(".", ",")


def fmt_moeda(valor):
    return f"{to_float(valor):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@app.context_processor
def dados_globais():
    empresa_nome = ""
    empresa_imagem = None
    usuario_nome = ""
    usuario_tipo = ""
    notificacoes_estoque = []
    total_notificacoes = 0

    if "empresa_id" in session:
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            cursor.execute("""
                SELECT nome, imagem
                FROM empresa
                WHERE id = %s
            """, (session["empresa_id"],))

            empresa = cursor.fetchone()

            if empresa:
                empresa_nome = empresa["nome"]
                empresa_imagem = empresa["imagem"]

            if "usuario_id" in session:
                cursor.execute("SELECT nome, tipo FROM usuario WHERE id = %s",
                               (session["usuario_id"],))
                usuario = cursor.fetchone()
                if usuario:
                    usuario_nome = usuario["nome"] or ""
                    usuario_tipo = usuario["tipo"] or ""

            # Sininho do header: mesma regra do dashboard, com as
            # preferências de notificação da empresa (Configuração)
            notificacoes_estoque = montar_notificacoes(cursor, session["empresa_id"])
            total_notificacoes = len(notificacoes_estoque)
            notificacoes_estoque = notificacoes_estoque[:8]

        finally:
            cursor.close()
            conexao.close()

    return {
        "empresa_nome": empresa_nome,
        # Foto que aparece no topo do menu lateral
        "empresa_imagem": empresa_imagem,
        # Usuário logado e notificações, mostrados no header
        "usuario_nome": usuario_nome,
        "usuario_primeiro_nome": usuario_nome.split()[0] if usuario_nome.strip() else "",
        "usuario_tipo": {"admin": "Administrador", "gerente": "Gerente",
                         "operador": "Operador"}.get(usuario_tipo, usuario_tipo.capitalize()),
        "notificacoes_estoque": notificacoes_estoque,
        "perfil": perfil_atual(),
        "pode_gerenciar": pode_gerenciar(),
        "total_notificacoes": total_notificacoes,
        # Preferências de interface guardadas na sessão. Antes ficavam no
        # localStorage e eram aplicadas por JavaScript depois que a página
        # carregava; agora chegam prontas no HTML.
        "tema": session.get("tema", "claro"),
        "sidebar_minimizada": session.get("sidebar_minimizada", False),
        # Usada como valor padrão nos campos de data dos formulários
        "hoje": datetime.now().strftime("%Y-%m-%d"),
        # Módulo atual, para o menu destacar o item certo
        "modulo_atual": modulo_do_endpoint(request.endpoint),
    }


# Cada item do menu cobre várias telas. Antes o destaque comparava o caminho
# exato ("/galpao"), então ao entrar em /estoque, /info_produto/1 ou
# /pedidos_cliente/1 nenhum item aparecia selecionado.
MODULOS = {
    "dashboard": {"dashboard"},

    "config": {"config", "usuarios"},

    "estoque": {
        "galpao", "novo_galpao", "salvar_galpao", "info_galpao",
        "atualizar_galpao", "deletar_galpao", "estoque", "estoque_galpao",
        "movimentar_estoque", "produtos", "produtos_inativos",
        "salvar_produto", "editar_produto", "atualizar_produto",
        "info_produtos", "desativar_produto", "reativar_produto",
        "excluir_produto", "ajustar_estoque_produto",
        "movimentacoes", "nova_movimentacao", "salvar_movimentacao",
        "salvar_empilhadeira", "atualizar_empilhadeira", "deletar_empilhadeira",
        "api_produtos_do_galpao", "api_todos_produtos", "api_produtos_do_fornecedor",
        "salvar_funcionario", "atualizar_funcionario", "deletar_funcionario",
    },

    "fornecedores": {
        "fornecedores", "novo_fornecedor", "salvar_fornecedor",
        "atualizar_fornecedor", "deletar_fornecedor", "info_fornecedor",
        "itens_fornecedor", "salvar_item_fornecedor",
        "vincular_fornecedor_produto",
    },

    "pedidos": {
        "pedidos", "listar_pedidos_entrada", "cadastro_pedido_entrada",
        "novo_pedido_entrada", "salvar_pedido_entrada",
        "visualizar_pedido_entrada", "editar_pedido", "deletar_pedido",
        "adicionar_item_entrada", "remover_item_entrada",
        "limpar_pedido_entrada",
    },

    "clientes": {
        "cliente", "novo_cliente", "salvar_cliente", "info_cliente",
        "atualizar_cliente", "deletar_cliente", "pedidos_clientes",
        "info_pedido_cliente", "cadastro_pedido", "cadastro_pedido_saida",
        "listar_pedidos_saida", "salvar_pedido_saida",
        "visualizar_pedido_saida", "deletar_pedido_saida",
        "adicionar_item_saida", "remover_item_saida", "limpar_pedido_saida",
    },
}


def modulo_do_endpoint(endpoint):
    for modulo, rotas in MODULOS.items():
        if endpoint in rotas:
            return modulo
    return None

# ---------------- PREFERÊNCIAS DE INTERFACE ---------------- #

def voltar_para(padrao="dashboard"):
    """Devolve o usuário para a página em que ele estava.

    O destino vem de um campo escondido do formulário. Só caminhos internos
    são aceitos: "//" e "http://" seriam redirecionamentos para fora do site.
    """
    destino = (request.form.get("voltar_para") or "").strip()

    if destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)

    return redirect(url_for(padrao))


def voltar_galpao(galpao_id):
    """Volta para a tela do galpão; sem galpão válido, para a lista.

    Os formulários de funcionário e empilhadeira mandam o galpão num campo
    escondido. Sem ele o url_for estourava com erro 500.
    """
    if str(galpao_id or "").strip().isdigit():
        return redirect(url_for("info_galpao", galpao_id=int(galpao_id)))
    return redirect(url_for("galpao"))


@app.route("/tema/alternar", methods=["POST"])
def alternar_tema():
    # O header manda o tema escolhido (lua ou sol); sem valor, alterna.
    escolhido = request.form.get("tema")
    if escolhido in ("claro", "escuro"):
        session["tema"] = escolhido
    else:
        session["tema"] = "claro" if session.get("tema") == "escuro" else "escuro"
    return voltar_para()


@app.route("/menu/alternar", methods=["POST"])
def alternar_menu():
    session["sidebar_minimizada"] = not session.get("sidebar_minimizada", False)
    return voltar_para()

# ---------------- FUNÇÕES AUXILIARES ---------------- #

def to_float(value, default=0.0):
    """Converte número digitado no padrão brasileiro ou americano.

    float("12,50") dava erro e o valor virava 0 sem aviso: um preço digitado
    com vírgula era gravado como zero. Aceita "12,50", "1.234,56", "R$ 9,90"
    e "12.5".
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)

    texto = str(value).strip().replace("R$", "").replace(" ", "")
    if not texto:
        return default

    if "," in texto:
        # vírgula é o decimal; pontos são separador de milhar
        texto = texto.replace(".", "").replace(",", ".")

    try:
        return float(texto)
    except (TypeError, ValueError):
        return default


def to_int(value, default=0):
    numero = to_float(value, None)
    if numero is None:
        return default
    return int(round(numero))

# ------------VALIDAÇÕES----------#

def telefone_valido(telefone):
    numeros = re.sub(r'\D', '', telefone)
    return len(numeros) in (10, 11)


def formatar_telefone(telefone):
    numeros = re.sub(r'\D', '', telefone)

    if len(numeros) == 11:
        return f"({numeros[:2]}) {numeros[2:7]}-{numeros[7:]}"

    if len(numeros) == 10:
        return f"({numeros[:2]}) {numeros[2:6]}-{numeros[6:]}"

    return telefone


def area_valida(area):
    try:
        valor = float(area)
        return valor > 0
    except (ValueError, TypeError):
        return False


def nome_valido(nome):
    return nome.replace(" ", "").isalpha()


def email_valido(email):
    padrao = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return re.match(padrao, email) is not None


def somente_numeros(valor):
    """Remove tudo que não for número."""
    return re.sub(r"\D", "", valor or "")


def formatar_documento(valor):
    """Aplica a máscara de CPF ou CNPJ, a partir dos números."""
    numeros = somente_numeros(valor)

    if len(numeros) == 11:
        return (f"{numeros[:3]}.{numeros[3:6]}.{numeros[6:9]}-{numeros[9:]}")

    if len(numeros) == 14:
        return (f"{numeros[:2]}.{numeros[2:5]}.{numeros[5:8]}"
                f"/{numeros[8:12]}-{numeros[12:]}")

    return valor or ""


def formatar_cep(valor):
    numeros = somente_numeros(valor)
    return f"{numeros[:5]}-{numeros[5:]}" if len(numeros) == 8 else (valor or "")


def validar_documento(valor, obrigatorio=True):
    """Confere um CPF ou CNPJ e devolve (numeros, erro).

    Aceita o documento como a pessoa costuma digitar, com ponto, barra e
    traço: a pontuação é removida antes de conferir. Antes a checagem era
    feita no texto cru com isdigit(), então "12.345.678/0001-95" era
    recusado mesmo sendo válido — e a máscara aparecia no próprio campo.

    O valor devolvido é sempre só números, para o banco não guardar o mesmo
    documento em dois formatos diferentes.
    """
    numeros = somente_numeros(valor)

    if not numeros:
        if obrigatorio:
            return "", "Informe o CPF ou o CNPJ."
        return None, None

    if len(numeros) == 11:
        if not validar_cpf(numeros):
            return numeros, "CPF inválido. Confira os números digitados."
        return numeros, None

    if len(numeros) == 14:
        if not validar_cnpj(numeros):
            return numeros, "CNPJ inválido. Confira os números digitados."
        return numeros, None

    return numeros, "O CPF deve ter 11 números e o CNPJ, 14."


def validar_telefone_campo(valor, obrigatorio=False):
    """Confere o telefone aceitando parênteses, espaço e traço."""
    numeros = somente_numeros(valor)

    if not numeros:
        if obrigatorio:
            return "", "Informe o telefone."
        return None, None

    if len(numeros) not in (10, 11):
        return numeros, "O telefone deve ter 10 ou 11 números, com DDD."

    return numeros, None


def validar_cep_campo(valor, obrigatorio=False):
    """Confere o CEP aceitando o traço."""
    numeros = somente_numeros(valor)

    if not numeros:
        if obrigatorio:
            return "", "Informe o CEP."
        return None, None

    if len(numeros) != 8:
        return numeros, "O CEP deve ter 8 números."

    return numeros, None


def documento_ja_usado(tabela, numeros, ignorar_id=None):
    """Diz se o CPF/CNPJ já pertence a outro registro da tabela.

    Compara sem a pontuação, para não deixar passar o mesmo documento salvo
    em formatos diferentes por versões anteriores do sistema.
    """
    if not numeros:
        return False

    coluna = "cpf_cnpj" if tabela == "cliente" else "cnpj"

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        sql = f"""
            SELECT id FROM {tabela}
            WHERE REGEXP_REPLACE(COALESCE({coluna}, ''), '[^0-9]', '') = %s
              AND empresa_id = %s
        """
        valores = [numeros, session.get("empresa_id")]

        if ignorar_id:
            sql += " AND id <> %s"
            valores.append(ignorar_id)

        cursor.execute(sql + " LIMIT 1", tuple(valores))
        return cursor.fetchone() is not None

    finally:
        cursor.close()
        conexao.close()


@app.template_filter("documento")
def filtro_documento(valor):
    """Mostra o CPF/CNPJ com máscara, esteja ele salvo como estiver."""
    return formatar_documento(valor) or "—"


@app.template_filter("cep")
def filtro_cep(valor):
    return formatar_cep(valor) or "—"


def validar_cpf(cpf):
    cpf = somente_numeros(cpf)

    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    resto = (soma * 10) % 11
    digito1 = 0 if resto == 10 else resto

    if digito1 != int(cpf[9]):
        return False

    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    resto = (soma * 10) % 11
    digito2 = 0 if resto == 10 else resto

    return digito2 == int(cpf[10])

def validar_cnpj(cnpj):
    cnpj = somente_numeros(cnpj)

    if len(cnpj) != 14 or cnpj == cnpj[0] * 14:
        return False

    # Primeiro dígito verificador
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    soma = sum(
        int(cnpj[i]) * pesos1[i]
        for i in range(12)
    )

    resto = soma % 11
    digito1 = 0 if resto < 2 else 11 - resto

    if digito1 != int(cnpj[12]):
        return False

    # Segundo dígito verificador
    pesos2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]

    soma = sum(
        int(cnpj[i]) * pesos2[i]
        for i in range(13)
    )

    resto = soma % 11
    digito2 = 0 if resto < 2 else 11 - resto

    return digito2 == int(cnpj[13])

# ------------ VERIFICAÇÃO DO BANCO ----------#

# Estruturas criadas depois da primeira versão do banco.sql. Se o banco foi
# criado por uma versão anterior e a migração não foi aplicada, várias telas
# quebram com "Internal Server Error" sem explicar o motivo. A verificação
# abaixo troca esse erro por uma instrução clara.
ESTRUTURAS_NECESSARIAS = [
    ("coluna", "empilhadeira", "funcionario_id"),
    ("coluna", "produto", "imagem"),
    ("coluna", "fornecedor", "imagem"),
    ("coluna", "galpao", "imagem"),
    ("coluna", "empresa", "imagem"),
    ("coluna", "cliente", "imagem"),
    ("tabela", "recuperacao_senha", None),
]

# ------------ MULTIEMPRESA (SaaS) ----------#

# Cada empresa cliente do sistema só pode ver os próprios dados. As tabelas
# principais guardam o dono em empresa_id; as tabelas filhas (estoque, itens
# de pedido, vínculo fornecedor-produto...) herdam o dono pelo registro pai.
TABELAS_DA_EMPRESA = [
    "fornecedor", "cliente", "galpao", "funcionario", "empilhadeira",
    "produto", "movimentacao", "pedido_fornecedor", "pedido_cliente",
]

# Documentos e códigos que antes eram únicos no banco inteiro. Num SaaS duas
# empresas podem ter o mesmo cliente ou o mesmo SKU, então a unicidade passa
# a ser por empresa.
UNICOS_POR_EMPRESA = {
    "fornecedor": ["cnpj"],
    "cliente": ["cpf_cnpj"],
    "funcionario": ["cpf"],
    "produto": ["sku", "codigo_barras"],
}


def migrar_multiempresa():
    """Atualiza bancos criados antes da separação por empresa.

    Idempotente: pode rodar a cada inicialização. Os registros antigos ficam
    com a primeira empresa cadastrada, que era a única dona na prática.
    """
    try:
        conexao = Database.connect()
    except Exception:
        return

    cursor = conexao.cursor()
    try:
        cursor.execute("SELECT MIN(id) FROM empresa")
        primeira = cursor.fetchone()[0]

        for tabela in TABELAS_DA_EMPRESA:
            cursor.execute("SHOW TABLES LIKE %s", (tabela,))
            if not cursor.fetchone():
                continue

            cursor.execute(f"SHOW COLUMNS FROM {tabela} LIKE 'empresa_id'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE {tabela} ADD COLUMN empresa_id INT NULL AFTER id")
                if primeira is not None:
                    cursor.execute(f"UPDATE {tabela} SET empresa_id = %s", (primeira,))
                    cursor.execute(f"ALTER TABLE {tabela} MODIFY empresa_id INT NOT NULL")
                cursor.execute(
                    f"ALTER TABLE {tabela} ADD CONSTRAINT fk_{tabela}_empresa "
                    f"FOREIGN KEY (empresa_id) REFERENCES empresa(id) ON DELETE CASCADE"
                )

            for coluna in UNICOS_POR_EMPRESA.get(tabela, []):
                # Índices únicos que tenham só a coluna (o formato antigo)
                cursor.execute(f"SHOW INDEX FROM {tabela} WHERE Non_unique = 0")
                indices = {}
                for linha in cursor.fetchall():
                    indices.setdefault(linha[2], []).append(linha[4])
                for nome, colunas in indices.items():
                    if nome != "PRIMARY" and colunas == [coluna]:
                        cursor.execute(f"ALTER TABLE {tabela} DROP INDEX `{nome}`")
                if ["empresa_id", coluna] not in indices.values():
                    cursor.execute(
                        f"ALTER TABLE {tabela} ADD UNIQUE KEY uq_{tabela}_empresa_{coluna} "
                        f"(empresa_id, {coluna})"
                    )

        # Clientes que perderam a situação ao serem editados (bug antigo:
        # o formulário não enviava o campo e gravava NULL/"None")
        cursor.execute("""
            UPDATE cliente SET ativo = 'ativo'
            WHERE ativo IS NULL OR ativo IN ('', 'None')
        """)

        # Foto do cliente (adicionada depois da primeira versão)
        cursor.execute("SHOW COLUMNS FROM cliente LIKE 'imagem'")
        if not cursor.fetchone():
            cursor.execute("ALTER TABLE cliente ADD COLUMN imagem VARCHAR(255) NULL")

        # Preferências de notificação da empresa (tela Configuração)
        novas = dict((c, f"TINYINT(1) NOT NULL DEFAULT {p[0]}")
                     for c, p in PREFERENCIAS_NOTIFICACAO.items())
        novas["notif_margem"] = f"INT NOT NULL DEFAULT {MARGEM_PADRAO}"
        for coluna, definicao in novas.items():
            cursor.execute(f"SHOW COLUMNS FROM empresa LIKE '{coluna}'")
            if not cursor.fetchone():
                cursor.execute(f"ALTER TABLE empresa ADD COLUMN {coluna} {definicao}")

        conexao.commit()
    except Exception as erro:
        conexao.rollback()
        app.logger.error("Falha ao migrar para multiempresa: %s", erro)
    finally:
        cursor.close()
        conexao.close()


ESTRUTURAS_NECESSARIAS += [("coluna", t, "empresa_id") for t in TABELAS_DA_EMPRESA]

migrar_multiempresa()


def empresa_atual():
    """Empresa da sessão; toda consulta de dados filtra por ela."""
    return session.get("empresa_id")


# Para cada nome de parâmetro (na URL ou no formulário), a tabela dona do id.
# Parâmetros genéricos como "id" dependem da rota e ficam em IDS_POR_ENDPOINT.
IDS_POR_PARAMETRO = {
    "galpao_id": "galpao",
    "galpao_destino_id": "galpao",
    "produto_id": "produto",
    "fornecedor_id": "fornecedor",
    "cliente_id": "cliente",
    "funcionario_id": "funcionario",
    "empilhadeira_id": "empilhadeira",
    "usuario_id": "usuario",
}

IDS_POR_ENDPOINT = {
    "editar_produto": ("id", "produto"),
    "atualizar_produto": ("id", "produto"),
    "ajustar_estoque_produto": ("id", "produto"),
    "desativar_produto": ("id", "produto"),
    "reativar_produto": ("id", "produto"),
    "excluir_produto": ("id", "produto"),
    "info_produtos": ("id", "produto"),
    "visualizar_pedido_entrada": ("pedido_id", "pedido_fornecedor"),
    "editar_pedido": ("id", "pedido_fornecedor"),
    "deletar_pedido": ("id", "pedido_fornecedor"),
    "visualizar_pedido_saida": ("pedido_id", "pedido_cliente"),
    "editar_pedido_cliente": ("pedido_id", "pedido_cliente"),
    "atualizar_pedido_cliente": ("pedido_id", "pedido_cliente"),
    "deletar_pedido_saida": ("id", "pedido_cliente"),
    "info_pedido_cliente": ("pedido_id", "pedido_cliente"),
    "processar_pedido": ("id", "pedido_cliente"),
    "cancelar_pedido": ("id", "pedido_cliente"),
}


# ------------ PERFIS DE ACESSO ----------#

PERFIS = {"admin": "Administrador", "gerente": "Gerente", "operador": "Operador"}

# Ações que não têm volta (excluir) ou mexem na conta da empresa ficam com
# administradores e gerentes. O operador cadastra, edita, desativa e cancela.
ENDPOINTS_GERENCIA = {
    "deletar_galpao", "deletar_empilhadeira", "excluir_produto",
    "deletar_fornecedor", "deletar_funcionario", "deletar_cliente",
    "deletar_pedido", "deletar_pedido_saida", "salvar_empresa", "salvar_notificacoes",
}

# Gestão da equipe: só o administrador
ENDPOINTS_ADMIN = {
    "usuarios", "salvar_usuario", "alternar_usuario_ativo", "alterar_perfil_usuario",
}


def perfil_atual():
    return session.get("tipo") or "operador"


def pode_gerenciar():
    return perfil_atual() in ("admin", "gerente")


@app.before_request
def verificar_perfil():
    if "usuario_id" not in session or request.endpoint in (None, "static"):
        return None

    # Relê o usuário: um perfil trocado ou uma conta desativada pelo
    # administrador vale na hora, não só no próximo login.
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT tipo, ativo FROM usuario WHERE id = %s AND empresa_id = %s",
            (session["usuario_id"], session.get("empresa_id")),
        )
        usuario = cursor.fetchone()
    finally:
        cursor.close()
        conexao.close()

    if not usuario or not usuario["ativo"]:
        session.clear()
        flash("Sua conta foi desativada. Fale com o administrador.", "erro")
        return redirect(url_for("login"))

    session["tipo"] = usuario["tipo"]

    if request.endpoint in ENDPOINTS_ADMIN and perfil_atual() != "admin":
        flash("Somente o administrador da conta pode gerenciar usuários.", "erro")
        return redirect(url_for("dashboard"))

    if request.endpoint in ENDPOINTS_GERENCIA and not pode_gerenciar():
        flash("Seu perfil (Operador) não pode fazer essa ação. Fale com um gerente.", "erro")
        destino = request.referrer or ""
        if destino.startswith(request.host_url):
            return redirect(destino)
        return redirect(url_for("dashboard"))

    return None


# Rotas que recebem o id do registro num campo "id" do formulário
IDS_NO_FORMULARIO = {
    "atualizar_funcionario": "funcionario",
}


def registro_da_empresa(tabela, registro_id):
    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            f"SELECT 1 FROM {tabela} WHERE id = %s AND empresa_id = %s",
            (registro_id, empresa_atual()),
        )
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        conexao.close()


@app.before_request
def proteger_dados_da_empresa():
    """Barra qualquer id de outra empresa, venha da URL ou do formulário.

    Sem isso bastava trocar o número na barra de endereço (/info_cliente/7)
    para abrir, editar ou excluir dados de outro cliente do SaaS.
    """
    if not empresa_atual() or request.endpoint in (None, "static"):
        return None

    verificar = []

    for nome, tabela in IDS_POR_PARAMETRO.items():
        valores = []
        if request.view_args and nome in request.view_args:
            valores.append(request.view_args[nome])
        valores += request.args.getlist(nome) + request.form.getlist(nome)
        for valor in valores:
            if str(valor).strip():
                verificar.append((tabela, valor))

    if request.endpoint in IDS_POR_ENDPOINT and request.view_args:
        nome, tabela = IDS_POR_ENDPOINT[request.endpoint]
        if nome in request.view_args:
            verificar.append((tabela, request.view_args[nome]))

    if request.endpoint in IDS_NO_FORMULARIO and request.form.get("id"):
        verificar.append((IDS_NO_FORMULARIO[request.endpoint], request.form.get("id")))

    for tabela, valor in verificar:
        try:
            registro_id = int(valor)
        except (TypeError, ValueError):
            abort(404)
        if not registro_da_empresa(tabela, registro_id):
            abort(404)

    return None


# Resultado guardado após a primeira checagem, para não consultar a cada request
_estruturas_faltando = None


def verificar_banco(forcar=False):
    """Devolve a lista de estruturas que faltam no banco."""
    global _estruturas_faltando

    if _estruturas_faltando is not None and not forcar:
        return _estruturas_faltando

    faltando = []

    try:
        conexao = Database.connect()
        cursor = conexao.cursor()

        try:
            for tipo, tabela, coluna in ESTRUTURAS_NECESSARIAS:
                if tipo == "tabela":
                    cursor.execute("SHOW TABLES LIKE %s", (tabela,))
                    if not cursor.fetchone():
                        faltando.append(f"tabela {tabela}")
                else:
                    cursor.execute(f"SHOW COLUMNS FROM {tabela} LIKE %s", (coluna,))
                    if not cursor.fetchone():
                        faltando.append(f"coluna {tabela}.{coluna}")

        finally:
            cursor.close()
            conexao.close()

    except Exception:
        # Banco fora do ar é outro problema; não é o caso de acusar migração
        return []

    _estruturas_faltando = faltando
    return faltando


@app.before_request
def avisar_banco_desatualizado():
    """Mostra o que fazer em vez de deixar a tela estourar com erro 500."""
    if request.endpoint in ("static", "banco_desatualizado"):
        return None

    if verificar_banco():
        return redirect(url_for("banco_desatualizado"))

    return None


@app.route("/banco-desatualizado")
def banco_desatualizado():
    faltando = verificar_banco()

    if not faltando:
        return redirect(url_for("landing"))

    return render_template("banco_desatualizado.html", faltando=faltando), 503


# ------------ IMAGENS ----------#

EXTENSOES_IMAGEM = {"png", "jpg", "jpeg", "webp", "gif"}

# Limite de tamanho do arquivo enviado
TAMANHO_MAXIMO_IMAGEM = 5 * 1024 * 1024  # 5 MB

PASTA_IMAGENS = os.path.join("static", "imagem")


def salvar_imagem(arquivo, prefixo, identificador):
    """Grava a imagem enviada e devolve o nome do arquivo.

    Devolve None quando nada foi enviado, e levanta ValueError quando o
    arquivo não serve. O nome inclui o tipo e o id (ex.: fornecedor_3.png),
    então trocar a imagem sobrescreve a anterior em vez de acumular lixo.
    """
    if not arquivo or not arquivo.filename:
        return None

    extensao = (arquivo.filename.rsplit(".", 1)[-1].lower()
                if "." in arquivo.filename else "")

    if extensao not in EXTENSOES_IMAGEM:
        raise ValueError(
            "Formato de imagem inválido. Use PNG, JPG, JPEG, WEBP ou GIF."
        )

    # O ponteiro precisa voltar ao início depois de medir o tamanho
    arquivo.seek(0, os.SEEK_END)
    tamanho = arquivo.tell()
    arquivo.seek(0)

    if tamanho > TAMANHO_MAXIMO_IMAGEM:
        raise ValueError("A imagem deve ter no máximo 5 MB.")

    nome_imagem = f"{prefixo}_{identificador}.{extensao}"
    pasta = os.path.join(app.root_path, PASTA_IMAGENS)
    os.makedirs(pasta, exist_ok=True)
    arquivo.save(os.path.join(pasta, nome_imagem))

    # Remove versões antigas com outra extensão, para não sobrar arquivo órfão
    for outra in EXTENSOES_IMAGEM:
        if outra == extensao:
            continue
        antigo = os.path.join(pasta, f"{prefixo}_{identificador}.{outra}")
        if os.path.exists(antigo):
            os.remove(antigo)

    return nome_imagem


def atualizar_imagem(tabela, registro_id, arquivo, prefixo):
    """Salva a imagem e grava o nome na coluna `imagem` da tabela."""
    nome_imagem = salvar_imagem(arquivo, prefixo, registro_id)

    if not nome_imagem:
        return None

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            f"UPDATE {tabela} SET imagem = %s WHERE id = %s",
            (nome_imagem, registro_id)
        )
        conexao.commit()
    finally:
        cursor.close()
        conexao.close()

    return nome_imagem


@app.template_filter("imagem_ou")
def filtro_imagem_ou(nome_imagem, padrao="imagemproduto.png"):
    """Devolve o caminho da imagem do registro ou de uma imagem padrão.

    Se o arquivo tiver sumido da pasta, cai no padrão em vez de mostrar
    um ícone de imagem quebrada.
    """
    if nome_imagem:
        caminho = os.path.join(app.root_path, PASTA_IMAGENS, nome_imagem)
        if os.path.exists(caminho):
            return nome_imagem

    return padrao


# ------------ FORMATAÇÃO ----------#

@app.template_filter("moeda")
def formatar_moeda(valor):
    """Formata um número no padrão brasileiro: 1234.5 -> 1.234,50."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0

    # Formata no padrão americano e troca os separadores de posição
    texto = f"{numero:,.2f}"
    return texto.replace(",", "X").replace(".", ",").replace("X", ".")


@app.template_filter("telefone")
def filtro_telefone(valor):
    """Exibe o telefone sempre no mesmo formato, esteja ele salvo como estiver."""
    return formatar_telefone(valor or "")


@app.template_filter("quantidade")
def formatar_quantidade(valor):
    """Mostra quantidades sem casas decimais desnecessárias: 3.000 -> 3."""
    try:
        numero = float(valor or 0)
    except (TypeError, ValueError):
        numero = 0.0

    if numero == int(numero):
        return str(int(numero))

    return f"{numero:.3f}".rstrip("0").rstrip(".").replace(".", ",")


# ------------ MENSAGENS DE ERRO ----------#

# Rótulos amigáveis para as colunas com índice único no banco.
CAMPOS_UNICOS = {
    "cnpj":          "CNPJ",
    "cpf":           "CPF",
    "cpf_cnpj":      "CPF/CNPJ",
    "sku":           "SKU",
    "codigo_barras": "código de barras",
    "email":         "e-mail",
}


def mensagem_erro(e):
    """Converte exceções do banco em texto compreensível para o usuário.

    Sem isso, uma tentativa de cadastrar um CNPJ repetido mostrava na tela
    algo como "1062 (23000): Duplicate entry ... for key 'cnpj'".
    """
    texto = str(e)

    if "Duplicate entry" in texto:
        for coluna, rotulo in CAMPOS_UNICOS.items():
            # "key 'cnpj'" (antigo) ou "key 'uq_cliente_empresa_cpf_cnpj'" (por empresa)
            if (f"key '{coluna}'" in texto or f"key '{coluna}_" in texto
                    or re.search(rf"key '(\w+\.)?uq_\w+_empresa_{coluna}'", texto)):
                return f"Já existe um registro cadastrado com este {rotulo}."
        return "Já existe um registro cadastrado com estes dados."

    if "foreign key constraint fails" in texto.lower():
        return ("Não foi possível concluir: este registro está vinculado a "
                "outros dados do sistema.")

    if "cannot be null" in texto.lower():
        return "Preencha todos os campos obrigatórios."

    return texto


# ------------ LISTAGENS (filtro e agrupamento feitos no servidor) ----------#

# ---------------- ORDENAÇÃO E FILTROS DAS LISTAGENS ---------------- #
#
# O botão "Filtros" abre um menu (sem JavaScript) com opções de ordem e de
# situação. As opções ficam aqui, junto da regra de ordenação, para cada tela
# declarar só a lista que usa.

def _texto(valor):
    return str(valor or "").strip().lower()


def _num(valor):
    return to_float(valor)


def _data(valor):
    return valor or datetime.min


ORDENS = {
    "produtos": [
        ("vendidos", "Mais vendidos", "bi-fire", lambda p: _num(p.get("vendidos")), True),
        ("az", "Nome A–Z", "bi-sort-alpha-down", lambda p: _texto(p.get("nome")), False),
        ("za", "Nome Z–A", "bi-sort-alpha-up", lambda p: _texto(p.get("nome")), True),
        ("mais_estoque", "Mais estoque", "bi-box-seam", lambda p: _num(p.get("quantidade")), True),
        ("menos_estoque", "Menos estoque", "bi-box", lambda p: _num(p.get("quantidade")), False),
        ("mais_caro", "Mais caro", "bi-currency-dollar", lambda p: _num(p.get("preco_venda")), True),
        ("mais_barato", "Mais barato", "bi-tag", lambda p: _num(p.get("preco_venda")), False),
        ("recentes", "Cadastrados recentemente", "bi-clock-history", lambda p: _data(p.get("created_at")), True),
    ],
    "clientes": [
        ("az", "Nome A–Z", "bi-sort-alpha-down", lambda c: _texto(c.get("nome")), False),
        ("za", "Nome Z–A", "bi-sort-alpha-up", lambda c: _texto(c.get("nome")), True),
        ("mais_pedidos", "Mais pedidos", "bi-bag-check", lambda c: _num(c.get("total_pedidos")), True),
        ("maior_gasto", "Maior valor gasto", "bi-cash-stack", lambda c: _num(c.get("total_gasto")), True),
        ("recentes", "Cadastrados recentemente", "bi-clock-history", lambda c: _data(c.get("created_at")), True),
    ],
    "fornecedores": [
        ("az", "Nome A–Z", "bi-sort-alpha-down", lambda f: _texto(f.get("nome")), False),
        ("za", "Nome Z–A", "bi-sort-alpha-up", lambda f: _texto(f.get("nome")), True),
        ("mais_produtos", "Mais produtos", "bi-boxes", lambda f: _num(f.get("total_produtos")), True),
        ("menos_produtos", "Menos produtos", "bi-box", lambda f: _num(f.get("total_produtos")), False),
    ],
    "galpoes": [
        ("az", "Nome A–Z", "bi-sort-alpha-down", lambda g: _texto(g.get("nome")), False),
        ("za", "Nome Z–A", "bi-sort-alpha-up", lambda g: _texto(g.get("nome")), True),
        ("mais_ocupado", "Mais ocupado", "bi-graph-up-arrow", lambda g: _num(g.get("ocupacao")), True),
        ("menos_ocupado", "Menos ocupado", "bi-graph-down-arrow", lambda g: _num(g.get("ocupacao")), False),
        ("mais_itens", "Mais itens", "bi-boxes", lambda g: _num(g.get("total_produtos")), True),
        ("maior_area", "Maior área", "bi-aspect-ratio", lambda g: _num(g.get("area_total")), True),
    ],
    "pedidos": [
        ("recentes", "Mais recentes", "bi-clock-history", lambda p: (_data(p.get("data_pedido")), p.get("id") or 0), True),
        ("antigos", "Mais antigos", "bi-clock", lambda p: (_data(p.get("data_pedido")), p.get("id") or 0), False),
        ("maior_valor", "Maior valor", "bi-cash-stack", lambda p: _num(p.get("valor_total")), True),
        ("menor_valor", "Menor valor", "bi-cash", lambda p: _num(p.get("valor_total")), False),
    ],
    "itens_fornecedor": [
        ("az", "Nome A–Z", "bi-sort-alpha-down", lambda i: _texto(i.get("produto_nome")), False),
        ("za", "Nome Z–A", "bi-sort-alpha-up", lambda i: _texto(i.get("produto_nome")), True),
        ("mais_caro", "Maior custo", "bi-currency-dollar", lambda i: _num(i.get("preco_custo")), True),
        ("mais_barato", "Menor custo", "bi-tag", lambda i: _num(i.get("preco_custo")), False),
        ("menor_prazo", "Menor prazo de entrega", "bi-truck", lambda i: _num(i.get("prazo_entrega_dias")), False),
    ],
}

# Filtros de situação por tela: valor -> (rótulo, função que decide se entra)
SITUACOES = {
    "produtos": [
        ("ativos", "Ativos", lambda p: bool(p.get("ativo"))),
        ("inativos", "Inativos", lambda p: not p.get("ativo")),
        ("baixo", "Estoque baixo", lambda p: 0 < _num(p.get("quantidade")) <= _num(p.get("quantidade_minimo"))),
        ("zerado", "Sem estoque", lambda p: _num(p.get("quantidade")) <= 0),
    ],
    "clientes": [
        ("ativos", "Ativos", lambda c: _texto(c.get("ativo")) in ("ativo", "1", "true")),
        ("inativos", "Inativos", lambda c: _texto(c.get("ativo")) not in ("ativo", "1", "true")),
        ("com_pedidos", "Com pedidos", lambda c: _num(c.get("total_pedidos")) > 0),
    ],
    "fornecedores": [
        ("ativos", "Ativos", lambda f: _texto(f.get("ativo")) in ("ativo", "1", "true")),
        ("inativos", "Inativos", lambda f: _texto(f.get("ativo")) not in ("ativo", "1", "true")),
    ],
    "pedidos": [
        ("pendente", "Pendentes", lambda p: _texto(p.get("status_pedido") or p.get("status")) == "pendente"),
        ("concluidos", "Concluídos/recebidos", lambda p: _texto(p.get("status_pedido") or p.get("status")) in ("concluido", "recebido", "pago", "enviado")),
        ("cancelado", "Cancelados", lambda p: _texto(p.get("status_pedido") or p.get("status")) == "cancelado"),
    ],
    "itens_fornecedor": [
        ("ativos", "Ativos", lambda i: bool(i.get("ativo"))),
        ("inativos", "Inativos", lambda i: not i.get("ativo")),
    ],
}


def ordenar_e_filtrar(itens, tela):
    """Aplica ?ordem= e ?situacao= da URL à lista e devolve o contexto do menu.

    Valores desconhecidos são ignorados (voltam para a ordem padrão), então
    uma URL editada à mão nunca quebra a tela.
    """
    ordens = ORDENS.get(tela, [])
    situacoes = SITUACOES.get(tela, [])

    situacao = request.args.get("situacao", "")
    regra_situacao = next((s for s in situacoes if s[0] == situacao), None)
    if regra_situacao:
        itens = [item for item in itens if regra_situacao[2](item)]
    else:
        situacao = ""

    ordem = request.args.get("ordem", "")
    regra = next((o for o in ordens if o[0] == ordem), None)
    if regra:
        itens = sorted(itens, key=regra[3], reverse=regra[4])
    else:
        ordem = ""

    menu = {
        "ordens": [(o[0], o[1], o[2]) for o in ordens],
        "situacoes": [(s[0], s[1]) for s in situacoes],
        "ordem": ordem,
        "situacao": situacao,
    }
    return list(itens), menu


def vendas_por_produto():
    """Quantidade vendida de cada produto da empresa (pedidos não cancelados)."""
    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            SELECT ipc.produto_id, COALESCE(SUM(ipc.quantidade), 0)
            FROM item_pedido_cliente ipc
            JOIN pedido_cliente pc ON pc.id = ipc.pedido_cliente_id
            WHERE pc.empresa_id = %s AND pc.status_pedido <> 'cancelado'
            GROUP BY ipc.produto_id
        """, (session["empresa_id"],))
        return {linha[0]: float(linha[1]) for linha in cursor.fetchall()}
    finally:
        cursor.close()
        conexao.close()


def com_vendas(produtos):
    vendas = vendas_por_produto()
    for produto in produtos:
        produto["vendidos"] = vendas.get(produto.get("id"), 0)
    return produtos


def filtrar_produtos(produtos, busca):
    """Filtra a listagem de produtos pelo texto digitado na barra de pesquisa.

    A busca é resolvida aqui, no Python, e não no JavaScript da página:
    o formulário envia ?busca=... por GET e a rota devolve a lista já filtrada.
    """
    termo = (busca or "").strip().lower()

    if not termo:
        return produtos

    def combina(produto):
        campos = (
            produto.get("nome"),
            produto.get("sku"),
            produto.get("categoria"),
            produto.get("fornecedor"),
            produto.get("codigo_barras"),
        )
        return any(termo in str(campo).lower() for campo in campos if campo)

    return [produto for produto in produtos if combina(produto)]


def agrupar_produtos_por_id(produtos):
    """Soma as quantidades de linhas repetidas do mesmo produto.

    Um produto pode ocupar várias localizações dentro do mesmo galpão, o que
    gera uma linha por localização. Antes essa soma era feita no navegador;
    agora a lista já chega pronta ao template.
    """
    agrupados = {}

    for produto in produtos:
        chave = produto.get("id")
        atual = agrupados.get(chave)

        if atual is None:
            agrupado = dict(produto)
            agrupado["quantidade"] = to_float(produto.get("quantidade"))
            agrupado["quantidade_minimo"] = to_float(produto.get("quantidade_minimo"))
            agrupados[chave] = agrupado
            continue

        atual["quantidade"] += to_float(produto.get("quantidade"))
        atual["quantidade_minimo"] = min(
            atual["quantidade_minimo"],
            to_float(produto.get("quantidade_minimo"))
        )

    return list(agrupados.values())


# ------------- LANDINGPAGE ------------- #

@app.route('/')
def landing():
    return render_template('landing.html')

@app.route('/home')
def home():
    if "usuario_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("landing"))

# ---------------- LOGIN OBRIGATÓRIO ---------------- #

def login_obrigatorio(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Faça login para continuar.", "erro")
            return redirect(url_for("login"))

        return f(*args, **kwargs)

    return wrap

# ---------------- INDEX ---------------- #

@app.route("/dashboard")
@login_obrigatorio
def dashboard():

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    # Todos os números são só da empresa logada
    emp = session["empresa_id"]

    try:
        # ---- Contagens gerais ----
        cursor.execute("SELECT COUNT(*) AS total FROM fornecedor WHERE empresa_id = %s", (emp,))
        total_fornecedores = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM cliente WHERE empresa_id = %s", (emp,))
        total_clientes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM galpao WHERE empresa_id = %s", (emp,))
        total_galpoes = cursor.fetchone()["total"]

        cursor.execute("SELECT COUNT(*) AS total FROM produto WHERE ativo = TRUE AND empresa_id = %s", (emp,))
        total_produtos = cursor.fetchone()["total"]

        # ---- Ganhos: pedidos de saída que não foram cancelados ----
        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_cliente
            WHERE empresa_id = %s
              AND status_pedido <> 'cancelado'
        """, (emp,))
        ganhos = to_float(cursor.fetchone()["total"])

        # ---- Gastos: pedidos de entrada que não foram cancelados ----
        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_fornecedor
            WHERE empresa_id = %s
              AND status <> 'cancelado'
        """, (emp,))
        gastos = to_float(cursor.fetchone()["total"])

        lucro = ganhos - gastos

        # ---- Gráfico: ganhos, gastos e lucro dos últimos 6 meses ----
        cursor.execute("""
            SELECT DATE_FORMAT(data_pedido, '%Y-%m') AS mes, SUM(valor_total) AS total
            FROM pedido_cliente
            WHERE empresa_id = %s
              AND status_pedido <> 'cancelado'
              AND data_pedido >= DATE_SUB(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 5 MONTH)
            GROUP BY mes
        """, (emp,))
        ganhos_por_mes = {l["mes"]: to_float(l["total"]) for l in cursor.fetchall()}

        cursor.execute("""
            SELECT DATE_FORMAT(data_pedido, '%Y-%m') AS mes, SUM(valor_total) AS total
            FROM pedido_fornecedor
            WHERE empresa_id = %s
              AND status <> 'cancelado'
              AND data_pedido >= DATE_SUB(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 5 MONTH)
            GROUP BY mes
        """, (emp,))
        gastos_por_mes = {l["mes"]: to_float(l["total"]) for l in cursor.fetchall()}

        nomes_meses = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                       "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
        hoje_data = datetime.now()
        grafico_lucro = []
        for atras in range(5, -1, -1):
            ano, mes = hoje_data.year, hoje_data.month - atras
            while mes < 1:
                mes += 12
                ano -= 1
            chave = f"{ano}-{mes:02d}"
            g = ganhos_por_mes.get(chave, 0.0)
            c = gastos_por_mes.get(chave, 0.0)
            grafico_lucro.append({"rotulo": nomes_meses[mes - 1], "ganhos": g,
                                  "gastos": c, "lucro": g - c})

        # Altura de cada barra em % da maior, calculada aqui para o
        # template só desenhar (sem biblioteca de gráfico nem JS)
        maior = max([abs(m["lucro"]) for m in grafico_lucro] + [1])
        for m in grafico_lucro:
            m["altura"] = round(abs(m["lucro"]) / maior * 100, 1)

        # ---- Comparação com o mês anterior, para a variação percentual ----
        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_cliente
            WHERE empresa_id = %s
              AND status_pedido <> 'cancelado'
              AND data_pedido >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
        """, (emp,))
        ganhos_mes = to_float(cursor.fetchone()["total"])

        cursor.execute("""
            SELECT COALESCE(SUM(valor_total), 0) AS total
            FROM pedido_cliente
            WHERE empresa_id = %s
              AND status_pedido <> 'cancelado'
              AND data_pedido >= DATE_FORMAT(CURDATE() - INTERVAL 1 MONTH, '%Y-%m-01')
              AND data_pedido <  DATE_FORMAT(CURDATE(), '%Y-%m-01')
        """, (emp,))
        ganhos_mes_anterior = to_float(cursor.fetchone()["total"])

        if ganhos_mes_anterior > 0:
            variacao = (ganhos_mes - ganhos_mes_anterior) / ganhos_mes_anterior * 100
        else:
            
            variacao = None

        # ---- Valor imobilizado em estoque (preço de custo) ----
        cursor.execute("""
            SELECT COALESCE(SUM(e.quantidade * p.preco_custo), 0) AS total
            FROM estoque e
            JOIN produto p ON p.id = e.produto_id
            WHERE p.empresa_id = %s
              AND p.ativo = TRUE
        """, (emp,))
        valor_estoque = to_float(cursor.fetchone()["total"])

        # ---- Produtos mais vendidos ----
        cursor.execute("""
            SELECT p.nome, p.sku,
                   SUM(ipc.quantidade) AS quantidade,
                   SUM(ipc.quantidade * ipc.preco_unitario_no_momento) AS receita
            FROM item_pedido_cliente ipc
            JOIN produto p        ON p.id = ipc.produto_id
            JOIN pedido_cliente pc ON pc.id = ipc.pedido_cliente_id
            WHERE pc.empresa_id = %s
              AND pc.status_pedido <> 'cancelado'
            GROUP BY p.id
            ORDER BY quantidade DESC
            LIMIT 5
        """, (emp,))
        mais_vendidos = cursor.fetchall()

        # ---- Últimas movimentações ----
        cursor.execute("""
            SELECT m.tipo, m.quantidade, m.data_movimentacao, m.observacao,
                   p.nome AS produto, g.nome AS galpao
            FROM movimentacao m
            JOIN produto p      ON p.id = m.produto_id
            LEFT JOIN galpao g  ON g.id = m.galpao_id
            WHERE m.empresa_id = %s
            ORDER BY m.data_movimentacao DESC, m.id DESC
            LIMIT 5
        """, (emp,))
        atividades = cursor.fetchall()

        # ---- Alertas de estoque baixo ----
        # Mesma regra do sininho (preferências em Configuração > Notificações)
        todos_alertas = alertas_estoque(cursor, emp)
        alertas = todos_alertas[:5]
        total_alertas = len(todos_alertas)

        cursor.execute("SELECT nome FROM empresa WHERE id = %s", (session["empresa_id"],))
        empresa = cursor.fetchone()
        empresa_nome = empresa["nome"] if empresa else ""

    finally:
        cursor.close()
        conexao.close()

    return render_template(
        "dashboard.html",
        empresa_nome=empresa_nome,
        total_fornecedores=total_fornecedores,
        total_clientes=total_clientes,
        total_galpoes=total_galpoes,
        total_produtos=total_produtos,
        ganhos=ganhos,
        gastos=gastos,
        lucro=lucro,
        grafico_lucro=grafico_lucro,
        variacao=variacao,
        valor_estoque=valor_estoque,
        mais_vendidos=mais_vendidos,
        atividades=atividades,
        alertas=alertas,
        total_alertas=total_alertas
    )

# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        senha = request.form.get("senha", "")

        if not email or not senha:
            flash("Informe o e-mail e a senha.", "erro")
            return render_template("login.html")

        espera = login_bloqueado(email)
        if espera:
            flash(f"Muitas tentativas erradas. Tente de novo em {espera} minuto(s).", "erro")
            return render_template("login.html"), 429

        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:
            # O mesmo e-mail pode existir em mais de uma empresa do SaaS
            # (usuario tem UNIQUE(email, empresa_id)); entra na conta cuja
            # senha confere.
            cursor.execute("""
                SELECT id, nome, email, senha, empresa_id, tipo, ativo
                FROM usuario
                WHERE email = %s
                ORDER BY ativo DESC, id
            """, (email,))

            usuario = next(
                (u for u in cursor.fetchall() if check_password_hash(u["senha"], senha)),
                None,
            )

            if not usuario:
                registrar_falha_login(email)
                flash("Email ou senha inválidos!", "erro")
                return render_template("login.html")

            limpar_falhas_login(email)

            if not usuario["ativo"]:
                flash("Usuário inativo.", "erro")
                return render_template("login.html")

            session.clear()

            session["usuario_logado"] = usuario["email"]
            session["usuario_id"] = usuario["id"]
            session["empresa_id"] = usuario["empresa_id"]
            session["tipo"] = usuario["tipo"]

            flash("Login realizado!", "sucesso")

            return redirect(url_for("dashboard"))

        except Exception as e:

            app.logger.exception("Falha ao autenticar usuário")

            flash("Não foi possível entrar agora. Tente novamente em instantes.", "erro")

            return render_template("login.html")

        finally:
            cursor.close()
            conexao.close()

    return render_template("login.html")

# ---------------- REDEFINIR SENHA ---------------- #

@app.route("/redefinir-senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:

        cursor.execute("""
            SELECT id, usuario_id, expira_em, usado
            FROM recuperacao_senha
            WHERE token = %s
        """, (token,))

        recuperacao = cursor.fetchone()

        if not recuperacao:
            flash("Token de recuperação inválido.", "erro")
            return redirect(url_for("esqueci_senha"))

        if recuperacao["usado"] == 1:
            flash("Este link de recuperação já foi utilizado.", "erro")
            return redirect(url_for("esqueci_senha"))

        if recuperacao["expira_em"] < datetime.now():
            flash("Este link de recuperação expirou.", "erro")
            return redirect(url_for("esqueci_senha"))

        # ------------------------------------------------
        # GET
        # ------------------------------------------------

        if request.method == "GET":

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        # ------------------------------------------------
        # POST
        # ------------------------------------------------

        senha = request.form.get("senha", "").strip()
        confirmar_senha = request.form.get("confirmar_senha", "").strip()

        if not senha:
            flash("Digite uma nova senha.", "erro")

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        if not confirmar_senha:
            flash("Confirme sua nova senha.", "erro")

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        if senha != confirmar_senha:
            flash("As senhas não são iguais.", "erro")

            return render_template(
                "redefinir_senha.html",
                token=token
            )

        # Criptografa a nova senha
        senha_hash = generate_password_hash(senha)

        # Atualiza a senha
        cursor.execute("""
            UPDATE usuario
            SET senha = %s
            WHERE id = %s
        """, (
            senha_hash,
            recuperacao["usuario_id"]
        ))

        # Marca o token como utilizado
        cursor.execute("""
            UPDATE recuperacao_senha
            SET usado = 1
            WHERE id = %s
        """, (
            recuperacao["id"],
        ))

        conexao.commit()

        flash(
            "Senha redefinida com sucesso! Faça login com sua nova senha.",
            "sucesso"
        )

        return redirect(url_for("login"))

    except Exception as e:

        conexao.rollback()

        app.logger.exception("Falha ao redefinir senha")

        flash(
            f"Erro ao redefinir senha: {mensagem_erro(e)}",
            "erro"
        )

        return redirect(url_for("esqueci_senha"))

    finally:

        cursor.close()
        conexao.close()

# ---------------- RECUPERAÇÃO DE SENHA ---------------- #

@app.route("/esqueci-senha", methods=["GET", "POST"])
def esqueci_senha():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        if not email:
            flash("Informe seu e-mail.", "erro")
            return redirect(url_for("esqueci_senha"))

        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:

            cursor.execute("""
                SELECT id, email
                FROM usuario
                WHERE email = %s
                  AND ativo = 1
            """, (email,))

            usuario = cursor.fetchone()

            if usuario:

                # Gera token seguro
                token = secrets.token_urlsafe(32)

                # Token válido por 30 minutos
                expira_em = datetime.now() + timedelta(minutes=30)

                # Salva no banco
                cursor.execute("""
                    INSERT INTO recuperacao_senha
                    (usuario_id, token, expira_em, usado)
                    VALUES (%s, %s, %s, 0)
                """, (
                    usuario["id"],
                    token,
                    expira_em
                ))

                # Link para redefinir a senha
                link = url_for(
                    "redefinir_senha",
                    token=token,
                    _external=True
                )

                conexao.commit()

                print("======================================")
                print("RECUPERAÇÃO DE SENHA")
                print("Usuário:", usuario["email"])
                print("LINK PARA REDEFINIR:")
                print(link)
                print("Expira em:", expira_em)
                print("======================================")

            flash(
                "Se o e-mail estiver cadastrado, você receberá as instruções para recuperar a senha.",
                "sucesso"
            )

        except Exception as e:

            conexao.rollback()

            app.logger.exception("Falha ao gerar token de recuperação")

            flash(
                "Ocorreu um erro ao solicitar a recuperação da senha.",
                "erro"
            )

        finally:

            cursor.close()
            conexao.close()

        return redirect(url_for("esqueci_senha"))

    return render_template("esqueci_senha.html")

# ---------------- CONFIG ---------------- #

@app.route('/config')
@login_obrigatorio
def config():
    """Tela de configurações.

    Antes era um mockup: os campos vinham preenchidos com dados fixos
    ("Ricardo Souza"), nenhum formulário tinha destino e o botão de modo
    escuro não fazia nada. Agora tudo vem do banco e cada bloco tem rota.
    """
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT id, nome, email, cpf, telefone, tipo
            FROM usuario
            WHERE id = %s
        """, (session["usuario_id"],))
        usuario = cursor.fetchone()

        cursor.execute("""
            SELECT id, nome, cnpj, imagem
            FROM empresa
            WHERE id = %s
        """, (session["empresa_id"],))
        empresa = cursor.fetchone()

        notificacoes = preferencias_notificacao(cursor, session["empresa_id"])

    finally:
        cursor.close()
        conexao.close()

    return render_template("config.html", usuario=usuario, empresa=empresa,
                           notificacoes=notificacoes,
                           opcoes_notificacao=PREFERENCIAS_NOTIFICACAO)


@app.route('/config/notificacoes', methods=["POST"])
@login_obrigatorio
def salvar_notificacoes():
    """Preferências de notificação da empresa (sininho e dashboard)."""
    valores = [1 if request.form.get(coluna) else 0 for coluna in PREFERENCIAS_NOTIFICACAO]
    margem = max(0, min(to_int(request.form.get("notif_margem")), 200))

    atribuicoes = ", ".join(f"{coluna} = %s" for coluna in PREFERENCIAS_NOTIFICACAO)
    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            f"UPDATE empresa SET {atribuicoes}, notif_margem = %s WHERE id = %s",
            tuple(valores) + (margem, session["empresa_id"]),
        )
        conexao.commit()
        flash("Preferências de notificação salvas.", "sucesso")
    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao salvar notificações: {mensagem_erro(e)}", "erro")
    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("config") + "#notificacoes")


@app.route('/config/perfil', methods=["POST"])
@login_obrigatorio
def salvar_perfil():
    nome     = (request.form.get("nome") or "").strip()
    email    = (request.form.get("email") or "").strip().lower()
    telefone = (request.form.get("telefone") or "").strip()

    if not nome:
        flash("Informe o nome do responsável.", "erro")
        return redirect(url_for("config"))

    if not email_valido(email):
        flash("Informe um e-mail válido.", "erro")
        return redirect(url_for("config"))

    if telefone and not telefone_valido(telefone):
        flash("Telefone inválido. Use DDD + número.", "erro")
        return redirect(url_for("config"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE usuario
            SET nome = %s, email = %s, telefone = %s
            WHERE id = %s
        """, (nome, email, formatar_telefone(telefone) if telefone else None,
              session["usuario_id"]))

        conexao.commit()

        # O e-mail é usado para exibir quem está logado
        session["usuario_logado"] = email
        flash("Perfil atualizado com sucesso!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao salvar o perfil: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("config"))


@app.route('/config/senha', methods=["POST"])
@login_obrigatorio
def alterar_senha():
    senha_atual = request.form.get("senha_atual") or ""
    nova_senha  = request.form.get("nova_senha") or ""
    confirmar   = request.form.get("confirmar_senha") or ""

    if len(nova_senha) < 6:
        flash("A nova senha deve ter pelo menos 6 caracteres.", "erro")
        return redirect(url_for("config"))

    if nova_senha != confirmar:
        flash("A confirmação não confere com a nova senha.", "erro")
        return redirect(url_for("config"))

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT senha FROM usuario WHERE id = %s", (session["usuario_id"],)
        )
        usuario = cursor.fetchone()

        # A senha atual é conferida para ninguém trocar a senha de uma
        # sessão deixada aberta.
        if not usuario or not check_password_hash(usuario["senha"], senha_atual):
            flash("A senha atual está incorreta.", "erro")
            return redirect(url_for("config"))

        cursor.execute("""
            UPDATE usuario SET senha = %s WHERE id = %s
        """, (generate_password_hash(nova_senha), session["usuario_id"]))

        conexao.commit()
        flash("Senha alterada com sucesso!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao alterar a senha: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("config"))


@app.route('/config/empresa', methods=["POST"])
@login_obrigatorio
def salvar_empresa():
    nome = (request.form.get("nome") or "").strip()

    cnpj, erro = validar_documento(request.form.get("cnpj"), obrigatorio=False)
    if erro:
        flash(erro, "erro")
        return redirect(url_for("config"))

    if not nome:
        flash("Informe a razão social da empresa.", "erro")
        return redirect(url_for("config"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute("""
            UPDATE empresa SET nome = %s, cnpj = %s WHERE id = %s
        """, (nome, cnpj, session["empresa_id"]))

        conexao.commit()

        # A imagem da empresa é a que aparece no topo do menu lateral
        atualizar_imagem("empresa", session["empresa_id"],
                         request.files.get("imagem"), "empresa")

        flash("Dados da empresa atualizados!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao salvar a empresa: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("config"))


# ---------------- LOGOUT ---------------- #

# ---------------- USUÁRIOS DA EMPRESA (equipe) ---------------- #

@app.route("/usuarios")
@login_obrigatorio
def usuarios():
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, nome, email, telefone, tipo, ativo, created_at
            FROM usuario
            WHERE empresa_id = %s
            ORDER BY ativo DESC, nome
        """, (session["empresa_id"],))
        lista = cursor.fetchall()
    finally:
        cursor.close()
        conexao.close()

    return render_template("usuarios.html", usuarios_empresa=lista, perfis=PERFIS)


@app.route("/usuarios/salvar", methods=["POST"])
@login_obrigatorio
def salvar_usuario():
    nome = (request.form.get("nome") or "").strip()
    email = (request.form.get("email") or "").strip().lower()
    senha = request.form.get("senha") or ""
    tipo = request.form.get("tipo") or "operador"

    erros = []
    if not nome:
        erros.append("Informe o nome.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        erros.append("Informe um e-mail válido.")
    if len(senha) < 6:
        erros.append("A senha provisória precisa ter pelo menos 6 caracteres.")
    if tipo not in PERFIS:
        erros.append("Perfil inválido.")

    if erros:
        for erro in erros:
            flash(erro, "erro")
        return redirect(url_for("usuarios"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            "SELECT 1 FROM usuario WHERE email = %s AND empresa_id = %s",
            (email, session["empresa_id"]),
        )
        if cursor.fetchone():
            flash("Já existe um usuário com este e-mail na sua empresa.", "erro")
            return redirect(url_for("usuarios"))

        cursor.execute("""
            INSERT INTO usuario (nome, email, senha, empresa_id, tipo, ativo)
            VALUES (%s, %s, %s, %s, %s, 1)
        """, (nome, email, generate_password_hash(senha), session["empresa_id"], tipo))
        conexao.commit()
        flash(f"Usuário {nome} criado. Passe a senha provisória para a pessoa entrar.", "sucesso")
    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao criar usuário: {mensagem_erro(e)}", "erro")
    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("usuarios"))


def _alterar_usuario(usuario_id, campo, valor, mensagem):
    """Troca perfil/ativo de alguém da equipe (nunca de si mesmo)."""
    if usuario_id == session.get("usuario_id"):
        flash("Você não pode alterar o próprio perfil ou desativar a própria conta.", "erro")
        return redirect(url_for("usuarios"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        cursor.execute(
            f"UPDATE usuario SET {campo} = %s WHERE id = %s AND empresa_id = %s",
            (valor, usuario_id, session["empresa_id"]),
        )
        conexao.commit()
        flash(mensagem, "sucesso")
    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:usuario_id>/ativo", methods=["POST"])
@login_obrigatorio
def alternar_usuario_ativo(usuario_id):
    ativar = request.form.get("ativo") == "1"
    return _alterar_usuario(
        usuario_id, "ativo", 1 if ativar else 0,
        "Usuário reativado." if ativar else "Usuário desativado. A pessoa não consegue mais entrar.",
    )


@app.route("/usuarios/<int:usuario_id>/perfil", methods=["POST"])
@login_obrigatorio
def alterar_perfil_usuario(usuario_id):
    tipo = request.form.get("tipo")
    if tipo not in PERFIS:
        flash("Perfil inválido.", "erro")
        return redirect(url_for("usuarios"))
    return _alterar_usuario(usuario_id, "tipo", tipo, f"Perfil alterado para {PERFIS[tipo]}.")


# Sair é uma mudança de estado, então exige POST: um link GET podia ser
# disparado por pré-carregamento do navegador e derrubar a sessão sozinho.
@app.route('/logout', methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu da conta.", "sucesso")
    return redirect(url_for('login'))

# ---------------- CADASTRO DE EMPRESA ---------------- #

@app.route("/cadastro", methods=["GET", "POST"])
def cadastro_emp():

    if request.method == "POST":

        nome = request.form.get("nome", "").strip()
        cnpj = request.form.get("cnpj", "").strip()
        email = request.form.get("email", "").strip().lower()
        telefone = request.form.get("telefone", "").strip()
        senha = request.form.get("senha", "")

        if not nome:
            flash("Informe o nome da empresa.", "erro")
            return render_template("cadastro.html")

        # O CNPJ só era testado como "preenchido": entrava qualquer número.
        # Agora os dígitos verificadores são conferidos, e a pontuação é
        # aceita e removida antes de gravar.
        cnpj, erro = validar_documento(cnpj)
        if erro:
            flash(erro, "erro")
            return render_template("cadastro.html")

        # CPF (11) também vale: MEI e profissionais autônomos usam o sistema
        if len(cnpj) not in (11, 14):
            flash("Informe um CPF (11 números) ou CNPJ (14 números).", "erro")
            return render_template("cadastro.html")

        if not email_valido(email):
            flash("Informe um e-mail válido.", "erro")
            return render_template("cadastro.html")

        telefone, erro = validar_telefone_campo(telefone)
        if erro:
            flash(erro, "erro")
            return render_template("cadastro.html")

        if len(senha) < 6:
            flash("A senha precisa ter pelo menos 6 caracteres.", "erro")
            return render_template("cadastro.html")

        senha_hash = generate_password_hash(senha)

        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)

        try:

            # Verifica se o CNPJ já existe
            # Compara sem a pontuação: empresas cadastradas por versões
            # anteriores podem ter o CNPJ salvo com ponto e barra.
            cursor.execute("""
                SELECT id
                FROM empresa
                WHERE REGEXP_REPLACE(COALESCE(cnpj, ''), '[^0-9]', '') = %s
                LIMIT 1
            """, (cnpj,))

            if cursor.fetchone():
                flash("Este CPF/CNPJ já está cadastrado.", "erro")
                return render_template("cadastro.html")

            # Verifica se o e-mail já existe
            cursor.execute("""
                SELECT id
                FROM usuario
                WHERE email = %s
                LIMIT 1
            """, (email,))

            if cursor.fetchone():
                flash("Este e-mail já está cadastrado.", "erro")
                return render_template("cadastro.html")

            # Cria a empresa
            cursor.execute("""
                INSERT INTO empresa (nome, cnpj)
                VALUES (%s, %s)
            """, (nome, cnpj))

            empresa_id = cursor.lastrowid

            # Cria o usuário administrador
            cursor.execute("""
                INSERT INTO usuario
                (nome, telefone, email, senha, empresa_id, tipo, ativo)
                VALUES (%s, %s, %s, %s, %s, 'admin', 1)
            """, (
                nome,
                telefone,
                email,
                senha_hash,
                empresa_id
            ))

            usuario_id = cursor.lastrowid
            conexao.commit()

            # Já entra na conta nova: quem acabou de criar a empresa não
            # precisa digitar tudo de novo na tela de login.
            session.clear()
            session["usuario_logado"] = email
            session["usuario_id"] = usuario_id
            session["empresa_id"] = empresa_id
            session["tipo"] = "admin"

            flash(f"Bem-vindo! A conta da {nome} está pronta. Comece cadastrando um galpão.", "sucesso")

            return redirect(url_for("dashboard"))

        except Exception as e:

            conexao.rollback()

            app.logger.exception("Falha ao cadastrar empresa")

            flash(
                f"Erro ao cadastrar empresa: {mensagem_erro(e)}",
                "erro"
            )

        finally:
            cursor.close()
            conexao.close()

    return render_template("cadastro.html")


# ---------------- ESTOQUE ---------------- #

@app.route("/estoque")
@login_obrigatorio
def estoque():
    # Visão consolidada: soma o estoque do produto em todos os galpões.
    busca = (request.args.get("busca") or "").strip()

    produtos, menu = ordenar_e_filtrar(
        com_vendas(filtrar_produtos(Estoque.find_all_consolidado(), busca)), "produtos")

    return render_template(
        "estoque.html",
        produtos=produtos,
        menu_filtros=menu,
        fornecedores=Fornecedor.find_all(),
        galpao=None,
        galpoes=Galpao.find_all(),
        busca=busca
    )


@app.route("/estoque/<int:galpao_id>")
@login_obrigatorio
def estoque_galpao(galpao_id):
    galpao = Galpao.find_by_id(galpao_id)

    if not galpao:
        flash("Galpão não encontrado.", "erro")
        return redirect(url_for("galpao"))

    busca = (request.args.get("busca") or "").strip()

    # A consolidação por produto é feita aqui, no Python, e não mais no
    # JavaScript da página: um produto guardado em várias localizações do
    # mesmo galpão aparece em uma única linha com a quantidade somada.
    produtos = agrupar_produtos_por_id(Estoque.find_by_galpao(galpao_id))

    produtos, menu = ordenar_e_filtrar(com_vendas(filtrar_produtos(produtos, busca)), "produtos")

    return render_template(
        "estoque.html",
        produtos=produtos,
        menu_filtros=menu,
        fornecedores=Fornecedor.find_all(),
        galpao=galpao,
        galpoes=Galpao.find_all(),
        busca=busca
    )


@app.route("/estoque/movimentar", methods=["POST"])
@login_obrigatorio
def movimentar_estoque():
    galpao_id = to_int(request.form.get("galpao_id"))
    try:
        produto_id = to_int(request.form.get("produto_id"))
        quantidade = to_int(request.form.get("quantidade"))
        tipo = request.form.get("tipo")

        Estoque.movimentar(produto_id, galpao_id, quantidade, tipo)
        flash("Movimentação realizada com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("estoque", galpao_id=galpao_id))

# ---------------- INFO GALPAO ---------------- #

@app.route("/info_galpao/<int:galpao_id>")
@login_obrigatorio
def info_galpao(galpao_id):

    galpao = Galpao.find_by_id(galpao_id)

    if not galpao:
        flash("Galpão não encontrado.", "erro")
        return redirect(url_for("galpao"))

    funcionarios = Funcionario.find_by_galpao(galpao_id)
    empilhadeiras = Empilhadeira.find_by_galpao(galpao_id)

    return render_template(
        "info_galpao.html",
        galpao=galpao,
        funcionarios=funcionarios,
        empilhadeiras=empilhadeiras
    )

@app.route("/galpao/atualizar/<int:galpao_id>", methods=["POST"])
@login_obrigatorio
def atualizar_galpao(galpao_id):
    try:

        # =========================
        # TELEFONE
        # =========================

        # Aceita "(15) 99999-9999" ou só números, como as outras telas
        telefone, erro = validar_telefone_campo(request.form.get("telefone"))

        if erro:
            flash(erro, "erro")
            return redirect(url_for("info_galpao", galpao_id=galpao_id))


        # =========================
        # CEP
        # =========================

        cep = request.form.get("cep", "").strip()

        cep = cep.replace("-", "").replace(" ", "")

        if not cep:
            flash(
                "O CEP é obrigatório.",
                "erro"
            )

            return redirect(
                url_for(
                    "info_galpao",
                    galpao_id=galpao_id
                )
            )

        if not cep.isdigit():
            flash(
                "O CEP deve conter apenas números.",
                "erro"
            )

            return redirect(
                url_for(
                    "info_galpao",
                    galpao_id=galpao_id
                )
            )

        if len(cep) != 8:
            flash(
                "O CEP deve conter exatamente 8 números.",
                "erro"
            )

            return redirect(
                url_for(
                    "info_galpao",
                    galpao_id=galpao_id
                )
            )


        # =========================
        # CAPACIDADE
        # =========================

        caixas_por_nivel = to_int(
            request.form.get("caixas_por_nivel")
        )

        niveis_por_prateleira = to_int(
            request.form.get("niveis_por_prateleira")
        )

        total_prateleiras = to_int(
            request.form.get("total_prateleiras")
        )

        capacidade_total = (
            caixas_por_nivel
            * niveis_por_prateleira
            * total_prateleiras
        )


        # =========================
        # DADOS
        # =========================

        dados = {
            "nome_resp": request.form.get("nome_resp"),
            "email_resp": request.form.get("email_resp"),
            "telefone": telefone,
            "stats": request.form.get("stats"),
            "nome": request.form.get("nome"),
            "cep": cep,
            "endereco": request.form.get("endereco"),
            "referencia": request.form.get("referencia"),
            "area_total": to_float(
                request.form.get("area_total")
            ),
            "caixas_por_nivel": caixas_por_nivel,
            "niveis_por_prateleira": niveis_por_prateleira,
            "total_prateleiras": total_prateleiras,
            "capacidade_total": capacidade_total,
        }


        Galpao.update(
            galpao_id,
            dados
        )

        flash(
            "Galpão atualizado com sucesso!",
            "sucesso"
        )

    except Exception as e:

        flash(
            f"Erro ao atualizar o galpão: {mensagem_erro(e)}",
            "erro"
        )

    return redirect(
        url_for(
            "info_galpao",
            galpao_id=galpao_id
        )
    )


@app.route("/galpao/deletar/<int:galpao_id>", methods=["POST"])
@login_obrigatorio
def deletar_galpao(galpao_id):
    try:

        Galpao.delete(galpao_id)

        flash(
            "Galpão excluído com sucesso!",
            "sucesso"
        )

    except Exception as e:
        if "foreign key" in str(e).lower() or "1451" in str(e):
            flash("Este galpão tem movimentações ou pedidos registrados e não pode ser "
                  "excluído, para não apagar o histórico. Você pode mudar o status "
                  "dele para Inativo.", "erro")
        else:
            flash(f"Erro ao excluir o galpão: {mensagem_erro(e)}", "erro")
        return redirect(url_for("info_galpao", galpao_id=galpao_id))

    return redirect(
        url_for("galpao")
    )
    


# ---------------- EMPILHADEIRAS ---------------- #

@app.route("/empilhadeira/salvar", methods=["POST"])
@login_obrigatorio
def salvar_empilhadeira():
    try:
        empilhadeira = Empilhadeira(
            marca=request.form.get("marca"),
            modelo=request.form.get("modelo"),
            ano_fabricacao=request.form.get("ano_fabricacao"),
            tipo_combustivel=request.form.get("tipo_combustivel"),
            capacidade=to_int(request.form.get("capacidade")),
            galpao_id=to_int(request.form.get("galpao_id")) or None,
            funcionario_id=to_int(request.form.get("funcionario_id")) or None,
            ativo=request.form.get("ativo")
        )
        empilhadeira.insert()
        flash("Empilhadeira cadastrada com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return voltar_galpao(request.form.get("galpao_id"))

@app.route("/empilhadeira/atualizar/<int:empilhadeira_id>", methods=["POST"])
@login_obrigatorio
def atualizar_empilhadeira(empilhadeira_id):
    galpao_id = to_int(request.form.get("galpao_id"))

    dados = {
        "marca":            request.form.get("marca"),
        "modelo":           request.form.get("modelo"),
        "ano_fabricacao":   request.form.get("ano_fabricacao"),
        "tipo_combustivel": request.form.get("tipo_combustivel"),
        "capacidade":       to_int(request.form.get("capacidade")),
        # Operador responsável: vazio significa "sem operador atribuído"
        "funcionario_id":   to_int(request.form.get("funcionario_id")) or None,
        "ativo":            request.form.get("ativo"),
    }

    try:
        Empilhadeira.update(empilhadeira_id, dados)
        flash("Empilhadeira atualizada com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return voltar_galpao(galpao_id)


@app.route("/empilhadeira/deletar/<int:empilhadeira_id>", methods=["POST"])
@login_obrigatorio
def deletar_empilhadeira(empilhadeira_id):
    galpao_id = request.form.get("galpao_id")
    try:
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM empilhadeira WHERE id = %s", (empilhadeira_id,))
        conn.commit()
        conn.close()
        flash("Empilhadeira removida com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return voltar_galpao(galpao_id)

# ---------------- PRODUTOS ---------------- #

@app.route("/produtos")
@login_obrigatorio
def produtos():
    # Mesma listagem consolidada de /estoque, mantida como rota separada
    # porque vários redirecionamentos apontam para "produtos".
    busca = (request.args.get("busca") or "").strip()

    lista, menu = ordenar_e_filtrar(
        com_vendas(filtrar_produtos(Estoque.find_all_consolidado(), busca)), "produtos")

    return render_template(
        "estoque.html",
        produtos=lista,
        menu_filtros=menu,
        fornecedores=Fornecedor.find_all(),
        galpao=None,
        galpoes=Galpao.find_all(),
        busca=busca
    )

@app.route("/produto/salvar", methods=["POST"])
@login_obrigatorio
def salvar_produto():
    sku = request.form.get("sku", "").strip()
    nome = request.form.get("nome", "").strip()
    galpao_id = to_int(request.form.get("galpao_id"))
    quantidade = to_int(request.form.get("quantidade", 1))
    estoque_minimo = to_int(request.form.get("quantidade_minimo", 0))

    if not sku or not nome:
        flash("SKU e Nome são obrigatórios.", "erro")
        return redirect(url_for("produtos"))

    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)

    try:
        # 1. Verifica se o produto já existe pelo SKU
        cursor.execute("SELECT id FROM produto WHERE sku = %s AND empresa_id = %s LIMIT 1",
                       (sku, session["empresa_id"]))
        produto_existente = cursor.fetchone()

        if produto_existente:
            produto_id = produto_existente["id"]
        else:
            # 2. Se não existir, insere o novo produto
            dados_produto = (
                sku,
                nome,
                request.form.get("descricao"),
                request.form.get("categoria"),
                to_float(request.form.get("preco_custo")),
                to_float(request.form.get("preco_venda")),
                to_float(request.form.get("peso")),
                to_float(request.form.get("volume")),
                request.form.get("tipo"),
                request.form.get("codigo_barras"),
                to_int(request.form.get("item_por_caixa"))
            )
            
            cursor.execute("""
                INSERT INTO produto 
                (empresa_id, sku, nome, descricao, categoria, preco_custo, preco_venda, peso, volume, tipo, codigo_barras, item_por_caixa, ativo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1)
            """, (session["empresa_id"],) + dados_produto)
            
            produto_id = cursor.lastrowid

        # 3. Imagem: mesma validação de tipo e tamanho das outras telas
        nome_imagem = salvar_imagem(request.files.get("imagem"), "produto", produto_id)
        if nome_imagem:
            cursor.execute("UPDATE produto SET imagem = %s WHERE id = %s", (nome_imagem, produto_id))

        # 4. Atualiza ou insere a quantidade no estoque do galpão (evita duplicar linhas)
        if galpao_id:
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE 
                    quantidade = quantidade + VALUES(quantidade),
                    estoque_minimo = VALUES(estoque_minimo)
            """, (produto_id, galpao_id, quantidade, estoque_minimo))

        conn.commit()
        flash("Produto e estoque processados com sucesso!", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao salvar produto: {mensagem_erro(e)}", "erro")
    finally:
        cursor.close()
        conn.close()

    if galpao_id:
        return redirect(url_for("estoque_galpao", galpao_id=galpao_id))
    return redirect(url_for("produtos"))


@app.route("/produto/editar/<int:id>")
@login_obrigatorio
def editar_produto(id):
    # Redireciona para info_produtos, que já exibe o formulário de edição
    return redirect(url_for("info_produtos", id=id))

@app.route("/produto/atualizar/<int:id>", methods=["POST"])
@login_obrigatorio
def atualizar_produto(id):
    produto = Produto.find_by_id(id)

    if not produto:
        flash("Produto não encontrado.", "erro")
        return redirect(url_for("produtos"))

    # O formulário envia "quantidade_minimo"; antes a rota lia "estoque_minimo",
    # então o mínimo era gravado como 0 a cada salvamento.
    estoque_minimo = to_int(request.form.get("quantidade_minimo"))

    dados = {
        "sku": request.form.get("sku"),
        "nome": request.form.get("nome"),
        "descricao": request.form.get("descricao"),
        "categoria": request.form.get("categoria"),
        "preco_custo": to_float(request.form.get("preco_custo")),
        "preco_venda": to_float(request.form.get("preco_venda")),
        "peso": to_float(request.form.get("peso")),
        "volume": to_float(request.form.get("volume")),
        "tipo": request.form.get("tipo"),
        "codigo_barras": request.form.get("codigo_barras") or None,
        "item_por_caixa": to_int(request.form.get("item_por_caixa")),
        # Produto.update grava a coluna `imagem` sempre. Sem este valor a
        # imagem atual era apagada toda vez que o produto era editado.
        "imagem": produto.get("imagem"),
    }

    if not dados["sku"] or not dados["nome"]:
        flash("SKU e Nome são obrigatórios.", "erro")
        return redirect(url_for("info_produtos", id=id))

    try:
        # Troca da imagem, quando uma nova for enviada
        imagem = request.files.get("imagem")

        if imagem and imagem.filename:
            extensoes_validas = {"png", "jpg", "jpeg", "webp"}
            extensao = (imagem.filename.rsplit(".", 1)[-1].lower()
                        if "." in imagem.filename else "")

            if extensao not in extensoes_validas:
                flash("Formato de imagem inválido. Use PNG, JPG, JPEG ou WEBP.", "erro")
                return redirect(url_for("info_produtos", id=id))

            nome_imagem = f"produto_{id}.{extensao}"
            pasta_imagem = os.path.join(app.root_path, "static", "imagem")
            os.makedirs(pasta_imagem, exist_ok=True)
            imagem.save(os.path.join(pasta_imagem, nome_imagem))
            dados["imagem"] = nome_imagem

        Produto.update(id, dados)

        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE estoque
                SET estoque_minimo = %s
                WHERE produto_id = %s
            """, (estoque_minimo, id))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        flash("Produto atualizado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro ao atualizar produto: {mensagem_erro(e)}", "erro")

    return redirect(url_for("info_produtos", id=id))


@app.route("/produto/ajustar_estoque/<int:id>", methods=["POST"])
@login_obrigatorio
def ajustar_estoque_produto(id):
    """Corrige o saldo de um produto em um galpão.

    A quantidade não é editada junto com os dados do produto porque o saldo é
    por galpão e precisa ficar registrado: todo acerto vira uma movimentação
    do tipo "ajuste_inventario".
    """
    galpao_id  = to_int(request.form.get("galpao_id"))
    quantidade = to_float(request.form.get("quantidade"))
    observacao = (request.form.get("observacao") or "").strip() or "Ajuste de inventário"

    if not galpao_id:
        flash("Selecione o galpão do ajuste.", "erro")
        return redirect(url_for("info_produtos", id=id))

    if quantidade < 0:
        flash("A quantidade não pode ser negativa.", "erro")
        return redirect(url_for("info_produtos", id=id))

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
            VALUES (%s, %s, %s, 0)
            ON DUPLICATE KEY UPDATE quantidade = VALUES(quantidade)
        """, (id, galpao_id, quantidade))

        cursor.execute("""
            INSERT INTO movimentacao
                (empresa_id, produto_id, galpao_id, tipo, quantidade, observacao)
            VALUES (%s, %s, %s, 'ajuste_inventario', %s, %s)
        """, (session["empresa_id"], id, galpao_id, quantidade, observacao))

        conn.commit()
        flash("Saldo ajustado e movimentação registrada.", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao ajustar o saldo: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("info_produtos", id=id))

def voltar_para_produto(produto_id, padrao="info_produtos"):
    """Devolve o usuário à tela de onde a ação partiu.

    Ativar, desativar ou excluir um produto pode ser feito de vários lugares
    (estoque, itens do fornecedor, inativos, ficha do produto). O formulário
    manda em `voltar_para` a página de origem; sem ela, cai no destino padrão.
    Só caminhos internos são aceitos, para o campo não virar redirecionamento
    para fora do site.
    """
    destino = (request.form.get("voltar_para") or "").strip()

    if destino.startswith("/") and not destino.startswith("//"):
        return redirect(destino)

    if padrao == "info_produtos":
        return redirect(url_for("info_produtos", id=produto_id))

    return redirect(url_for(padrao))


@app.route("/produto/desativar/<int:id>", methods=["POST"])
@login_obrigatorio
def desativar_produto(id):
    try:
        Produto.desativar(id)
        flash("Produto desativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    # Volta para a tela de origem (itens do fornecedor, estoque, ficha do
    # produto). Antes caía sempre na ficha do produto, tirando o usuário da
    # lista em que ele estava trabalhando.
    return voltar_para_produto(id)

@app.route("/produto/reativar/<int:id>", methods=["POST"])
@login_obrigatorio
def reativar_produto(id):
    try:
        Produto.reativar(id)
        flash("Produto reativado com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return voltar_para_produto(id, padrao="produtos_inativos")

@app.route("/produtos/inativos")
@login_obrigatorio
def produtos_inativos():
    lista = Produto.find_inativos()
    return render_template("produtos_inativos.html", produtos=lista)

@app.route("/produto/excluir/<int:id>", methods=["POST"])
@login_obrigatorio
def excluir_produto(id):
    try:
        Produto.safe_delete(id)
        flash("Produto excluído com sucesso!", "sucesso")
    except ValueError as e:
        # Produto com histórico: a mensagem já explica, e a ficha continua existindo
        flash(str(e), "erro")
        return redirect(url_for("info_produtos", id=id))
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
        return redirect(url_for("info_produtos", id=id))

    # Excluído de vez: a ficha não existe mais, então volta para a lista de
    # origem (itens do fornecedor, inativos, estoque).
    return voltar_para_produto(id, padrao="produtos")

# ---------------- INFO PRODUTO ---------------- #

@app.route("/info_produto/<int:id>")
@login_obrigatorio
def info_produtos(id):
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT
                p.*,
                COALESCE(SUM(e.quantidade), 0)      AS quantidade,
                COALESCE(MIN(e.estoque_minimo), 0)  AS estoque_minimo,
                GROUP_CONCAT(DISTINCT f.nome ORDER BY f.nome SEPARATOR ', ')
                                                    AS fornecedor
            FROM produto p
            LEFT JOIN estoque e              ON p.id = e.produto_id
            LEFT JOIN fornecedor_produto fp  ON p.id = fp.produto_id
            LEFT JOIN fornecedor f           ON fp.fornecedor_id = f.id
            WHERE p.id = %s
            GROUP BY p.id
        """, (id,))
        produto = cursor.fetchone()

        if not produto:
            flash("Produto não encontrado.", "erro")
            return redirect(url_for("produtos"))

        produtos = Produto.find_all_completo()

        # Saldo por galpão: o total exibido no topo é a soma destes valores,
        # e cada linha permite ajustar o estoque daquele galpão.
        cursor.execute("""
            SELECT e.galpao_id, g.nome AS galpao_nome,
                   e.quantidade, e.estoque_minimo
            FROM estoque e
            JOIN galpao g ON g.id = e.galpao_id
            WHERE e.produto_id = %s
            ORDER BY g.nome
        """, (id,))
        saldos = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template(
        "info_produto.html",
        produto=produto,
        produtos=produtos,
        saldos=saldos,
        galpoes=Galpao.find_all(),
        # A tela mostra um histórico de alterações que ainda não tem tabela
        # no banco; sem esta lista o bloco quebrava ao ser renderizado.
        historico=[]
    )

# ---------------- GALPÕES ---------------- #

# ---------------- BUSCA GERAL (campo do header) ---------------- #

@app.route("/buscar")
@login_obrigatorio
def buscar():
    q = (request.args.get("q") or "").strip()
    resultados = {"produtos": [], "clientes": [], "fornecedores": [], "galpoes": []}

    if q:
        termo = f"%{q}%"
        emp = session["empresa_id"]
        conexao = Database.connect()
        cursor = conexao.cursor(dictionary=True)
        try:
            cursor.execute("""
                SELECT id, nome, sku, categoria, ativo FROM produto
                WHERE empresa_id = %s
                  AND (nome LIKE %s OR sku LIKE %s OR categoria LIKE %s OR codigo_barras LIKE %s)
                ORDER BY ativo DESC, nome LIMIT 20
            """, (emp,) + (termo,) * 4)
            resultados["produtos"] = cursor.fetchall()

            cursor.execute("""
                SELECT id, nome, empresa, cidade, cpf_cnpj FROM cliente
                WHERE empresa_id = %s
                  AND (nome LIKE %s OR empresa LIKE %s OR cpf_cnpj LIKE %s
                       OR email LIKE %s OR cidade LIKE %s)
                ORDER BY nome LIMIT 20
            """, (emp,) + (termo,) * 5)
            resultados["clientes"] = cursor.fetchall()

            cursor.execute("""
                SELECT id, nome, nome_ctt, cnpj FROM fornecedor
                WHERE empresa_id = %s
                  AND (nome LIKE %s OR nome_ctt LIKE %s OR cnpj LIKE %s OR email LIKE %s)
                ORDER BY nome LIMIT 20
            """, (emp,) + (termo,) * 4)
            resultados["fornecedores"] = cursor.fetchall()

            cursor.execute("""
                SELECT id, nome, cidade, estado FROM galpao
                WHERE empresa_id = %s
                  AND (nome LIKE %s OR cidade LIKE %s OR estado LIKE %s OR nome_resp LIKE %s)
                ORDER BY nome LIMIT 20
            """, (emp,) + (termo,) * 4)
            resultados["galpoes"] = cursor.fetchall()
        finally:
            cursor.close()
            conexao.close()

    total = sum(len(v) for v in resultados.values())
    return render_template("busca.html", q=q, total=total, **resultados)


@app.route("/galpao")
@login_obrigatorio
def galpao():
    busca = (request.args.get("busca") or "").strip()
    galpoes = Galpao.find_all()

    if busca:
        termo = busca.lower()

        def combina(g):
            campos = (g.get("nome"), g.get("cidade"), g.get("estado"),
                      g.get("nome_resp"), g.get("endereco"), g.get("stats"))
            return any(termo in str(c).lower() for c in campos if c)

        galpoes = [g for g in galpoes if combina(g)]

    galpoes, menu = ordenar_e_filtrar(galpoes, "galpoes")
    return render_template("galpao.html", galpoes=galpoes, busca=busca, menu_filtros=menu)

@app.route("/galpao/novo")
@login_obrigatorio
def novo_galpao():
    # O cadastro de galpão é um modal dentro da própria listagem; renderizar
    # o template solto deixava a tela sem os galpões e sem a barra de busca.
    return redirect(url_for("galpao"))

@app.route("/galpao/salvar", methods=["POST"])
@login_obrigatorio
def salvar_galpao():
    try:

        # =========================
        # E-MAIL
        # =========================

        email = request.form.get("email_resp", "").strip()

        if not email_valido(email):
            flash("Informe um e-mail válido.", "erro")
            return redirect(url_for("galpao"))


        # =========================
        # NOME DO RESPONSÁVEL
        # =========================

        nome_resp = request.form.get("nome_resp", "").strip()

        if not nome_valido(nome_resp):
            flash(
                "O nome do responsável deve conter apenas letras.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # CEP
        # =========================

        cep = request.form.get("cep", "").strip()

        # Remove hífen e espaços
        cep = cep.replace("-", "").replace(" ", "")

        if not cep:
            flash("O CEP é obrigatório.", "erro")
            return redirect(url_for("galpao"))

        if not cep.isdigit():
            flash("O CEP deve conter apenas números.", "erro")
            return redirect(url_for("galpao"))

        if len(cep) != 8:
            flash(
                "O CEP deve conter exatamente 8 números.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # ÁREA TOTAL
        # =========================

        area_total = request.form.get("area_total", "").strip()

        if not area_valida(area_total):
            flash(
                "A área total deve ser um número maior que zero.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # TELEFONE
        # =========================

        telefone = request.form.get("telefone", "").strip()

        if not telefone_valido(telefone):
            flash(
                "Informe um telefone válido com 10 ou 11 números.",
                "erro"
            )
            return redirect(url_for("galpao"))

        telefone = formatar_telefone(telefone)

        if not telefone_valido(telefone):
            flash(
                "Informe um telefone válido com 10 ou 11 números.",
                "erro"
            )
            return redirect(url_for("galpao"))


        # =========================
        # CAPACIDADE DO GALPÃO
        # =========================

        caixas_por_nivel = to_int(
            request.form.get("caixas_por_nivel")
        )

        niveis_por_prateleira = to_int(
            request.form.get("niveis_por_prateleira")
        )

        total_prateleiras = to_int(
            request.form.get("total_prateleiras")
        )

        capacidade_total = (
            caixas_por_nivel
            * niveis_por_prateleira
            * total_prateleiras
        )


        # =========================
        # CRIAÇÃO DO GALPÃO
        # =========================

        g = Galpao(
            nome=request.form.get("nome"),
            stats=request.form.get("stats"),
            cep=cep,
            email_resp=email,
            nome_resp=nome_resp,
            endereco=request.form.get("endereco"),
            referencia=request.form.get("referencia"),
            cidade=request.form.get("cidade"),
            estado=request.form.get("estado"),
            area_total=float(area_total),
            telefone=telefone,
            total_prateleiras=total_prateleiras,
            niveis_por_prateleira=niveis_por_prateleira,
            caixas_por_nivel=caixas_por_nivel,
            capacidade_total=capacidade_total
        )

        g.insert()

        flash(
            "Galpão cadastrado com sucesso!",
            "sucesso"
        )

    except Exception as e:

        flash(
            f"Erro: {mensagem_erro(e)}",
            "erro"
        )

    return redirect(url_for("galpao"))

# ---------------- FORNECEDORES ---------------- #

@app.route("/fornecedores")
@login_obrigatorio
def fornecedores():
    busca = (request.args.get("busca") or "").strip()

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        # Removido o WHERE ativo = 'ativo' — agora traz todos
        cursor.execute("""
            SELECT
                f.id,
                f.nome,
                f.nome_ctt,
                f.email,
                f.telefone,
                f.ativo,
                f.cnpj,
                COUNT(fp.produto_id) AS total_produtos

            FROM fornecedor f

            LEFT JOIN fornecedor_produto fp
                ON fp.fornecedor_id = f.id

            WHERE f.empresa_id = %s

            GROUP BY
                f.id,
                f.nome,
                f.nome_ctt,
                f.email,
                f.telefone,
                f.ativo,
                f.cnpj

            ORDER BY f.nome ASC
        """, (session["empresa_id"],))

        lista_fornecedores = cursor.fetchall()
        

        cursor.execute("SELECT id, nome, sku FROM produto WHERE empresa_id = %s ORDER BY nome ASC",
                       (session["empresa_id"],))
        lista_produtos = cursor.fetchall()

        cursor.execute("""
            SELECT
                fp.produto_id,
                fp.fornecedor_id,
                p.nome AS produto_nome,
                p.sku,
                f.nome AS fornecedor_nome,
                fp.preco_custo,
                fp.desconto,
                fp.quantidade_minima,
                fp.prazo_entrega_dias,
                fp.ativo
            FROM fornecedor_produto fp
            JOIN produto p ON fp.produto_id = p.id
            JOIN fornecedor f ON fp.fornecedor_id = f.id
            WHERE f.empresa_id = %s
            ORDER BY f.nome ASC, p.nome ASC
        """, (session["empresa_id"],))
        fornecedores_produtos = cursor.fetchall()

    finally:
        cursor.close()
        conexao.close()

    # A lista principal é filtrada em Python: a consulta agrupa produtos por
    # fornecedor, e filtrar no SQL mudaria as contagens exibidas.
    if busca:
        termo = busca.lower()

        def combina(fornecedor):
            campos = (fornecedor.get("nome"), fornecedor.get("nome_ctt"),
                      fornecedor.get("email"), fornecedor.get("cnpj"),
                      fornecedor.get("telefone"))
            return any(termo in str(c).lower() for c in campos if c)

        lista_fornecedores = [f for f in lista_fornecedores if combina(f)]

    lista_fornecedores, menu = ordenar_e_filtrar(lista_fornecedores, "fornecedores")

    return render_template(
        "fornecedores.html",
        fornecedores=lista_fornecedores,
        lista_fornecedores=lista_fornecedores,
        lista_produtos=lista_produtos,
        fornecedores_produtos=fornecedores_produtos,
        menu_filtros=menu,
        busca=busca
    )


@app.route("/fornecedor/novo")
@login_obrigatorio
def novo_fornecedor():
    return render_template("form_fornecedor.html")


@app.route("/fornecedor/salvar", methods=["POST"])
@login_obrigatorio
def salvar_fornecedor():
    nome  = (request.form.get("nome") or "").strip()
    email = (request.form.get("email") or "").strip()

    # O fornecedor não tinha nenhuma conferência: entrava qualquer CNPJ.
    # Agora vale a mesma regra do cliente, aceitando a pontuação.
    cnpj, erro = validar_documento(request.form.get("cnpj"), obrigatorio=False)
    if erro:
        flash(erro, "erro")
        return redirect(url_for("fornecedores"))

    telefone, erro = validar_telefone_campo(request.form.get("telefone"))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("fornecedores"))

    if not nome:
        flash("Informe o nome do fornecedor.", "erro")
        return redirect(url_for("fornecedores"))

    if email and not email_valido(email):
        flash("Informe um e-mail válido.", "erro")
        return redirect(url_for("fornecedores"))

    if cnpj and documento_ja_usado("fornecedor", cnpj):
        flash("Já existe um fornecedor com este CNPJ.", "erro")
        return redirect(url_for("fornecedores"))

    try:
        fornecedor = Fornecedor(
            nome=nome,
            ativo=request.form.get("ativo"),
            cnpj=cnpj,
            nome_ctt=(request.form.get("nome_ctt") or "").strip(),
            telefone=telefone,
            email=email
        )
        fornecedor.insert()
        flash("Fornecedor cadastrado!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("fornecedores"))


@app.route("/fornecedor/atualizar/<int:fornecedor_id>", methods=["POST"])
@login_obrigatorio
def atualizar_fornecedor(fornecedor_id):
    nome  = (request.form.get("nome") or "").strip()
    email = (request.form.get("email") or "").strip()

    cnpj, erro = validar_documento(request.form.get("cnpj"), obrigatorio=False)
    if erro:
        flash(erro, "erro")
        return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

    telefone, erro = validar_telefone_campo(request.form.get("telefone"))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

    if not nome:
        flash("Informe o nome do fornecedor.", "erro")
        return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

    if email and not email_valido(email):
        flash("Informe um e-mail válido.", "erro")
        return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

    if cnpj and documento_ja_usado("fornecedor", cnpj, fornecedor_id):
        flash("Já existe outro fornecedor com este CNPJ.", "erro")
        return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))

    try:
        conexao = Database.connect()
        cursor = conexao.cursor()

        cursor.execute("""
            UPDATE fornecedor
            SET nome=%s, cnpj=%s, nome_ctt=%s, email=%s, telefone=%s, ativo=%s
            WHERE id=%s
        """, (
            nome,
            cnpj,
            (request.form.get("nome_ctt") or "").strip(),
            email,
            telefone,
            request.form.get("ativo"),
            fornecedor_id
        ))

        conexao.commit()

        # Troca da imagem do fornecedor, quando enviada
        atualizar_imagem("fornecedor", fornecedor_id,
                         request.files.get("imagem"), "fornecedor")

        flash("Fornecedor atualizado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("info_fornecedor", fornecedor_id=fornecedor_id))


@app.route("/fornecedor/deletar/<int:fornecedor_id>", methods=["POST"])
@login_obrigatorio
def deletar_fornecedor(fornecedor_id):
    try:
        conexao = Database.connect()
        cursor = conexao.cursor()

        cursor.execute("DELETE FROM fornecedor WHERE id = %s", (fornecedor_id,))
        conexao.commit()
        flash("Fornecedor removido com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("fornecedores"))


@app.route("/fornecedores/vincular_produto", methods=["POST"])
@login_obrigatorio
def vincular_fornecedor_produto():
    fornecedor_id = to_int(request.form.get("fornecedor_id"))
    produto_id = to_int(request.form.get("produto_id"))
    preco_custo = to_float(request.form.get("preco_custo"))
    desconto = to_float(request.form.get("desconto"))
    quantidade_minima = to_int(request.form.get("quantidade_minima"))
    prazo_entrega_dias = to_int(request.form.get("prazo_entrega_dias"))

    conexao = Database.connect()
    cursor = conexao.cursor()

    try:
        sql = """
            INSERT INTO fornecedor_produto
            (fornecedor_id, produto_id, preco_custo, desconto, quantidade_minima, prazo_entrega_dias, ativo)
            VALUES (%s, %s, %s, %s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
                preco_custo = VALUES(preco_custo),
                desconto = VALUES(desconto),
                quantidade_minima = VALUES(quantidade_minima),
                prazo_entrega_dias = VALUES(prazo_entrega_dias),
                ativo = 1
        """
        cursor.execute(sql, (fornecedor_id, produto_id, preco_custo, desconto, quantidade_minima, prazo_entrega_dias))
        conexao.commit()
        flash("Produto associado ao fornecedor com sucesso!", "sucesso")
    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao salvar vínculo comercial: {mensagem_erro(e)}", "erro")
    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("fornecedores"))

# ---------------- INFO FORNECEDOR ---------------- #
@app.route("/info_fornecedor/<int:fornecedor_id>")
@login_obrigatorio
def info_fornecedor(fornecedor_id):
    fornecedor = Fornecedor.find_by_id(fornecedor_id)

    if not fornecedor:
        flash("Fornecedor não encontrado.", "erro")
        return redirect(url_for("fornecedores"))

    produtos = Fornecedor.find_produtos(fornecedor_id)
    lista_produtos = Produto.find_all()

    return render_template(
        "info_fornecedor.html",
        fornecedor=fornecedor,
        produtos=produtos,
        lista_produtos=lista_produtos,
        historico=[]   # FIX: evita erro no template enquanto a tabela de log não existe
    )

# ---------------- ITENS FORNECEDOR ---------------- #

@app.route("/itens_fornecedores/<int:fornecedor_id>")
@login_obrigatorio
def itens_fornecedor(fornecedor_id):
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM fornecedor WHERE id = %s", (fornecedor_id,))
        fornecedor = cursor.fetchone()

        if not fornecedor:
            flash("Fornecedor não encontrado.", "erro")
            return redirect(url_for("fornecedores"))

        fornecedores_produtos = itens_do_fornecedor(cursor, fornecedor_id)

        busca = (request.args.get("busca") or "").strip()
        if busca:
            termo = busca.lower()
            fornecedores_produtos = [
                i for i in fornecedores_produtos
                if termo in _texto(i["produto_nome"]) or termo in _texto(i["sku"])
            ]
        fornecedores_produtos, menu = ordenar_e_filtrar(fornecedores_produtos, "itens_fornecedor")

        return render_template(
            "itens_fornecedores.html",
            fornecedor=fornecedor,
            fornecedores_produtos=fornecedores_produtos,
            busca=busca,
            menu_filtros=menu,
        )
    finally:
        cursor.close()
        conexao.close()


def itens_do_fornecedor(cursor, fornecedor_id):
    cursor.execute("""
        SELECT
            p.id            AS produto_id,
            p.nome          AS produto_nome,
            p.sku,
            p.imagem,
            p.ativo         AS produto_ativo,
            fp.preco_custo,
            fp.desconto,
            fp.quantidade_minima,
            fp.prazo_entrega_dias,
            fp.ativo,
            f.nome          AS fornecedor_nome
        FROM fornecedor_produto fp
        JOIN produto   p ON p.id  = fp.produto_id
        JOIN fornecedor f ON f.id = fp.fornecedor_id
        WHERE fp.fornecedor_id = %s
        ORDER BY p.nome ASC
    """, (fornecedor_id,))
    return cursor.fetchall()


@app.route("/itens_fornecedores/<int:fornecedor_id>/exportar")
@login_obrigatorio
def exportar_itens_fornecedor(fornecedor_id):
    """Catálogo do fornecedor em CSV (abre direto no Excel, separado por ;)."""
    import csv

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute("SELECT nome FROM fornecedor WHERE id = %s", (fornecedor_id,))
        fornecedor = cursor.fetchone()
        itens = itens_do_fornecedor(cursor, fornecedor_id)
    finally:
        cursor.close()
        conexao.close()

    saida = io.StringIO()
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow(["Produto", "SKU", "Preço de custo", "Desconto (%)",
                       "Quantidade mínima", "Prazo (dias)", "Situação"])
    for item in itens:
        escritor.writerow([
            item["produto_nome"], item["sku"],
            f'{to_float(item["preco_custo"]):.2f}'.replace(".", ","),
            f'{to_float(item["desconto"]):.2f}'.replace(".", ","),
            to_int(item["quantidade_minima"]), to_int(item["prazo_entrega_dias"]),
            "Ativo" if item["ativo"] else "Inativo",
        ])

    nome = re.sub(r"[^A-Za-z0-9]+", "_", (fornecedor or {}).get("nome") or "fornecedor").strip("_")
    # BOM no início: o Excel reconhece os acentos
    return app.response_class(
        "\ufeff" + saida.getvalue(),
        mimetype="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="itens_{nome}.csv"'},
    )


# Rota nova: cria o produto E já vincula ao fornecedor em uma só ação
@app.route("/fornecedor/<int:fornecedor_id>/salvar_item", methods=["POST"])
@login_obrigatorio
def salvar_item_fornecedor(fornecedor_id):
    try:
        produto = Produto(
            sku=request.form.get("sku"),
            nome=request.form.get("nome"),
            descricao=request.form.get("descricao"),
            categoria=request.form.get("categoria"),
            preco_custo=to_float(request.form.get("preco_custo")),
            preco_venda=0.0,
            peso=to_float(request.form.get("peso")),
            volume=to_float(request.form.get("volume")),
            tipo=request.form.get("tipo"),
            codigo_barras=request.form.get("codigo_barras") or None,
        )

        erros = produto.validate()
        if erros:
            for erro in erros:
                flash(erro, "erro")
            return redirect(url_for("itens_fornecedor", fornecedor_id=fornecedor_id))

        produto_id = produto.insert()

        # Salva campos extras que não estão no __init__ padrão
        conn = Database.connect()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE produto
                SET unidade_medida = %s, item_por_caixa = %s
                WHERE id = %s
            """, (
                request.form.get("unidade_medida", "un"),
                to_int(request.form.get("item_por_caixa")),
                produto_id
            ))

            # Vincula ao fornecedor
            cursor.execute("""
                INSERT INTO fornecedor_produto
                    (fornecedor_id, produto_id, preco_custo, desconto,
                     quantidade_minima, prazo_entrega_dias, ativo)
                VALUES (%s, %s, %s, 0, %s, %s, 1)
                ON DUPLICATE KEY UPDATE
                    preco_custo       = VALUES(preco_custo),
                    quantidade_minima = VALUES(quantidade_minima),
                    prazo_entrega_dias = VALUES(prazo_entrega_dias),
                    ativo             = 1
            """, (
                fornecedor_id,
                produto_id,
                to_float(request.form.get("preco_custo")),
                to_int(request.form.get("pedido_minimo")),
                to_int(request.form.get("tempo_entrega")),
            ))
            conn.commit()
        finally:
            cursor.close()
            conn.close()

        flash("Produto cadastrado e vinculado ao fornecedor!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("itens_fornecedor", fornecedor_id=fornecedor_id))

# ---------------- CLIENTES ---------------- #

@app.route("/clientes")
@login_obrigatorio
def cliente():

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    # Pesquisa resolvida no SQL, a partir de ?busca=... enviado pelo formulário
    busca = (request.args.get("busca") or "").strip()

    sql = """
        SELECT
            c.*,
            COUNT(pc.id) AS total_pedidos,
            COALESCE(SUM(pc.valor_total), 0) AS total_gasto
        FROM cliente c
        LEFT JOIN pedido_cliente pc
            ON pc.cliente_id = c.id
           AND pc.status_pedido <> 'cancelado'
        WHERE c.empresa_id = %s
    """
    valores = (session["empresa_id"],)

    if busca:
        sql += """
          AND (c.nome LIKE %s OR c.empresa LIKE %s
               OR c.cpf_cnpj LIKE %s OR c.email LIKE %s
               OR c.cidade LIKE %s)
        """
        valores += tuple([f"%{busca}%"] * 5)

    sql += " GROUP BY c.id ORDER BY c.nome"

    cursor.execute(sql, valores)
    clientes = cursor.fetchall()

    cursor.close()
    conexao.close()

    clientes, menu = ordenar_e_filtrar(clientes, "clientes")

    return render_template(
        "cliente.html",
        clientes=clientes,
        menu_filtros=menu,
        busca=busca
    )

@app.route("/cliente/novo")
@login_obrigatorio
def novo_cliente():
    # Mesmo caso do galpão: o cadastro é um modal da listagem de clientes.
    return redirect(url_for("cliente"))

@app.route("/cliente/salvar", methods=["POST"])
@login_obrigatorio
def salvar_cliente():
    try:
        nome = request.form.get("nome", "").strip()
        empresa = request.form.get("empresa", "").strip()
        cpf_cnpj = request.form.get("cpf", "").strip()
        email = request.form.get("email", "").strip()
        telefone = request.form.get("telefone", "").strip()
        cidade = request.form.get("cidade", "").strip()
        cep = request.form.get("cep", "").strip()
        estado = request.form.get("estado", "").strip()
        ativo = request.form.get("ativo", "").strip()

        # =========================
        # CPF / CNPJ, TELEFONE E CEP
        # =========================
        # A pontuação é aceita e removida antes de conferir, e só os números
        # são gravados — assim o mesmo documento não fica salvo em dois
        # formatos diferentes.

        cpf_cnpj_numeros, erro = validar_documento(cpf_cnpj)
        if erro:
            flash(erro, "erro")
            return redirect(url_for("cliente"))

        telefone, erro = validar_telefone_campo(telefone)
        if erro:
            flash(erro, "erro")
            return redirect(url_for("cliente"))

        cep, erro = validar_cep_campo(cep)
        if erro:
            flash(erro, "erro")
            return redirect(url_for("cliente"))

        if not nome:
            flash("Informe o nome do cliente.", "erro")
            return redirect(url_for("cliente"))

        if email and not email_valido(email):
            flash("Informe um e-mail válido.", "erro")
            return redirect(url_for("cliente"))

        # Um mesmo CPF/CNPJ não pode ser cadastrado duas vezes
        if documento_ja_usado("cliente", cpf_cnpj_numeros):
            flash("Já existe um cliente com este CPF/CNPJ.", "erro")
            return redirect(url_for("cliente"))

        # =========================
        # CADASTRO
        # =========================

        c = Cliente(
            nome=nome,
            ativo=ativo,
            cidade=cidade,
            empresa=empresa,
            cep=cep,
            estado=estado,
            cpf_cnpj=cpf_cnpj_numeros,
            email=email,
            telefone=telefone
        )

        c.insert()

        flash("Cliente cadastrado!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return redirect(url_for("cliente"))

# ---------------- FUNCIONÁRIOS ---------------- #

def validar_cpf_funcionario(valor, ignorar_id=None):
    """CPF do funcionário: opcional, mas quando informado precisa ser um CPF
    válido (11 números) e não repetido dentro da empresa. Antes era gravado
    como veio, sem conferência nenhuma."""
    numeros, erro = validar_documento(valor, obrigatorio=False)
    if erro:
        return None, erro
    if not numeros:
        return None, None
    if len(numeros) != 11:
        return None, "O CPF do funcionário precisa ter 11 números."

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        sql = """SELECT id FROM funcionario
                 WHERE REGEXP_REPLACE(COALESCE(cpf, ''), '[^0-9]', '') = %s
                   AND empresa_id = %s"""
        valores = [numeros, session["empresa_id"]]
        if ignorar_id:
            sql += " AND id <> %s"
            valores.append(ignorar_id)
        cursor.execute(sql + " LIMIT 1", tuple(valores))
        if cursor.fetchone():
            return None, "Já existe um funcionário com este CPF."
    finally:
        cursor.close()
        conexao.close()

    return numeros, None


@app.route("/funcionario/salvar", methods=["POST"])
@login_obrigatorio
def salvar_funcionario():
    cpf, erro = validar_cpf_funcionario(request.form.get("cpf"))
    if erro:
        flash(erro, "erro")
        return voltar_galpao(request.form.get("galpao_id"))

    try:
        salario = to_float(request.form.get("salario"))

        funcionario = Funcionario(
            nome=request.form.get("nome"),
            cpf=cpf,
            salario=salario,
            data_nascimento=request.form.get("data_nascimento") or None,
            data_admissao=request.form.get("data_admissao") or None,
            email=request.form.get("email"),
            telefone=request.form.get("telefone"),
            ativo=request.form.get("ativo"),
            cargo=request.form.get("cargo"),
            galpao_id=request.form.get("galpao_id")
        )
        funcionario.insert()
        flash("Funcionário cadastrado com sucesso!", "sucesso")

    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")

    return voltar_galpao(request.form.get("galpao_id"))

@app.route("/funcionario/atualizar", methods=["POST"])
@login_obrigatorio
def atualizar_funcionario():
    funcionario_id = to_int(request.form.get("id"))
    galpao_id      = to_int(request.form.get("galpao_id"))
    nome           = request.form.get("nome", "").strip()

    if not funcionario_id or not nome:
        flash("Informe o funcionário e o nome.", "erro")
        return voltar_galpao(galpao_id)

    cpf, erro = validar_cpf_funcionario(request.form.get("cpf"), ignorar_id=funcionario_id)
    if erro:
        flash(erro, "erro")
        return voltar_galpao(galpao_id)

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE funcionario
            SET nome=%s, cpf=%s, salario=%s, email=%s,
                telefone=%s, cargo=%s, ativo=%s
            WHERE id=%s
        """, (
            nome,
            cpf,
            to_float(request.form.get("salario")),
            request.form.get("email"),
            formatar_telefone(request.form.get("telefone", "").strip()),
            request.form.get("cargo"),
            request.form.get("ativo"),
            funcionario_id
        ))

        conn.commit()
        flash("Funcionário atualizado com sucesso!", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao atualizar funcionário: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return voltar_galpao(galpao_id)

@app.route("/funcionario/deletar/<int:funcionario_id>", methods=["POST"])
@login_obrigatorio
def deletar_funcionario(funcionario_id):
    galpao_id = request.form.get("galpao_id")
    try:
        conn = Database.connect()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM funcionario WHERE id = %s", (funcionario_id,))
        conn.commit()
        conn.close()
        flash("Funcionário removido com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro ao remover funcionário: {mensagem_erro(e)}", "erro")
    return voltar_galpao(galpao_id)

# ---------------- MOVIMENTAÇÕES ---------------- #

@app.route("/movimentacoes")
@login_obrigatorio
def movimentacoes():
    # Os filtros são resolvidos aqui, no servidor, via query string (?produto_id=&galpao_id=&tipo=).
    produto_id = to_int(request.args.get("produto_id")) or None
    galpao_id  = to_int(request.args.get("galpao_id")) or None
    tipo       = (request.args.get("tipo") or "").strip().lower() or None

    return render_template(
        "movimentacoes.html",
        movimentacoes=Movimentacao.find_all_with_product(produto_id, galpao_id, tipo),
        produtos=Produto.find_all(),
        galpoes=Galpao.find_all(),
        tipos=Movimentacao.TIPOS,
        filtro_produto_id=produto_id,
        filtro_galpao_id=galpao_id,
        filtro_tipo=tipo
    )

@app.route("/movimentacao/nova")
@login_obrigatorio
def nova_movimentacao():
    return render_template(
        "form_movimentacao.html",
        produtos=Produto.find_all(),
        galpoes=Galpao.find_all(),
        funcionarios=Funcionario.find_all(),
        tipos=Movimentacao.TIPOS
    )

@app.route("/movimentacao/salvar", methods=["POST"])
@login_obrigatorio
def salvar_movimentacao():
    produto_id        = to_int(request.form.get("produto_id")) or None
    galpao_id         = to_int(request.form.get("galpao_id")) or None
    galpao_destino_id = to_int(request.form.get("galpao_destino_id")) or None
    funcionario_id    = to_int(request.form.get("funcionario_id")) or None
    tipo              = (request.form.get("tipo") or "").strip().lower()
    quantidade        = to_float(request.form.get("quantidade"))
    observacao        = (request.form.get("observacao") or "").strip() or None

    movimentacao = Movimentacao(
        produto_id=produto_id,
        galpao_id=galpao_id,
        tipo=tipo,
        quantidade=quantidade,
        galpao_destino_id=galpao_destino_id,
        funcionario_id=funcionario_id,
        observacao=observacao
    )

    erros = movimentacao.validate()
    if erros:
        for erro in erros:
            flash(erro, "erro")
        return redirect(url_for("nova_movimentacao"))

    conexao = Database.connect()
    cursor = conexao.cursor()
    try:
        # Saldo atual na origem
        cursor.execute("""
            SELECT quantidade FROM estoque
            WHERE produto_id = %s AND galpao_id = %s
            FOR UPDATE
        """, (produto_id, galpao_id))

        resultado = cursor.fetchone()
        atual = float(resultado[0]) if resultado else 0.0

        if tipo in ("saida", "transferencia") and atual < quantidade:
            raise ValueError(
                f"Estoque insuficiente no galpão de origem (disponível: {atual:g})."
            )

        cursor.execute("""
            INSERT INTO movimentacao
                (empresa_id, produto_id, galpao_id, galpao_destino_id,
                 funcionario_id, tipo, quantidade, observacao)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (session["empresa_id"], produto_id, galpao_id, galpao_destino_id,
              funcionario_id, tipo, quantidade, observacao))

        if tipo == "entrada":
            delta_origem = quantidade
        elif tipo in ("saida", "transferencia"):
            delta_origem = -quantidade
        else:  # ajuste_inventario define o saldo absoluto
            delta_origem = None

        if delta_origem is None:
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = VALUES(quantidade)
            """, (produto_id, galpao_id, quantidade))
        else:
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
            """, (produto_id, galpao_id, delta_origem))

        # Na transferência o estoque sai da origem e entra no destino
        if tipo == "transferencia":
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
            """, (produto_id, galpao_destino_id, quantidade))

        conexao.commit()
        flash("Movimentação registrada!", "sucesso")

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao registrar movimentação: {mensagem_erro(e)}", "erro")
        return redirect(url_for("nova_movimentacao"))

    finally:
        cursor.close()
        conexao.close()

    return redirect(url_for("movimentacoes"))

# ---------------- INFO CLIENTES ---------------- #

@app.route("/info_cliente/<int:cliente_id>")
@login_obrigatorio
def info_cliente(cliente_id):
    c = Cliente.find_by_id(cliente_id)
    if not c:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("cliente"))
    pedidos = PedidoCliente.find_by_cliente(cliente_id)
    return render_template("info_cliente.html", cliente=c, pedidos=pedidos)


@app.route("/cliente/atualizar/<int:cliente_id>", methods=["POST"])
@login_obrigatorio
def atualizar_cliente(cliente_id):
    nome  = (request.form.get("nome") or "").strip()
    email = (request.form.get("email") or "").strip()

    # As mesmas regras do cadastro: antes a edição não conferia nada, então
    # dava para gravar telefone, CEP e documento em qualquer formato.
    cpf_cnpj, erro = validar_documento(request.form.get("cpf_cnpj"),
                                       obrigatorio=False)
    if erro:
        flash(erro, "erro")
        return redirect(url_for("info_cliente", cliente_id=cliente_id))

    telefone, erro = validar_telefone_campo(request.form.get("telefone"))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("info_cliente", cliente_id=cliente_id))

    cep, erro = validar_cep_campo(request.form.get("cep"))
    if erro:
        flash(erro, "erro")
        return redirect(url_for("info_cliente", cliente_id=cliente_id))

    if not nome:
        flash("Informe o nome do cliente.", "erro")
        return redirect(url_for("info_cliente", cliente_id=cliente_id))

    if email and not email_valido(email):
        flash("Informe um e-mail válido.", "erro")
        return redirect(url_for("info_cliente", cliente_id=cliente_id))

    if cpf_cnpj and documento_ja_usado("cliente", cpf_cnpj, cliente_id):
        flash("Já existe outro cliente com este CPF/CNPJ.", "erro")
        return redirect(url_for("info_cliente", cliente_id=cliente_id))

    try:
        dados = {
            "nome":     nome,
            # Sem o campo no formulário, mantém a situação atual: antes o
            # cliente virava "None" (inativo) a cada edição.
            "ativo":    (request.form.get("ativo")
                         if request.form.get("ativo") in ("ativo", "inativo")
                         else (Cliente.find_by_id(cliente_id) or {}).get("ativo") or "ativo"),
            "empresa":  (request.form.get("empresa") or "").strip(),
            "email":    email,
            "telefone": telefone,
            "cep":      cep,
            "cidade":   (request.form.get("cidade") or "").strip(),
            "estado":   request.form.get("estado"),
            "cpf_cnpj": cpf_cnpj,
        }
        Cliente.update(cliente_id, dados)
        atualizar_imagem("cliente", cliente_id, request.files.get("imagem"), "cliente")
        flash("Cliente atualizado com sucesso!", "sucesso")
    except ValueError as e:
        flash(str(e), "erro")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("info_cliente", cliente_id=cliente_id))


@app.route("/cliente/deletar/<int:cliente_id>", methods=["POST"])
@login_obrigatorio
def deletar_cliente(cliente_id):
    try:
        Cliente.delete(cliente_id)
        flash("Cliente excluído com sucesso!", "sucesso")
    except Exception as e:
        flash(f"Erro: {mensagem_erro(e)}", "erro")
    return redirect(url_for("cliente"))


# ------------------------------------------------------------------ #
# API — produtos disponíveis por galpão                               #
# ------------------------------------------------------------------ #

# ------------------------------------------------------------------ #
# CONSULTAS DE PEDIDOS                                                #
# ------------------------------------------------------------------ #

def buscar_pedidos_entrada(busca=""):
    """Pedidos de fornecedor, opcionalmente filtrados por fornecedor/documento."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = """
            SELECT pf.*, f.nome AS fornecedor_nome, g.nome AS galpao_nome
            FROM pedido_fornecedor pf
            LEFT JOIN fornecedor f ON pf.fornecedor_id = f.id
            LEFT JOIN galpao     g ON pf.galpao_id     = g.id
        """
        sql += " WHERE pf.empresa_id = %s"
        valores = (session["empresa_id"],)

        if busca:
            sql += " AND (f.nome LIKE %s OR pf.numero_documento LIKE %s)"
            valores += (f"%{busca}%", f"%{busca}%")

        sql += " ORDER BY pf.id DESC"

        cursor.execute(sql, valores)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


def buscar_pedidos_saida(busca=""):
    """Pedidos de cliente, opcionalmente filtrados por cliente/documento."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        sql = """
            SELECT pc.*, c.nome AS cliente_nome, g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c ON pc.cliente_id = c.id
            LEFT JOIN galpao  g ON pc.galpao_id  = g.id
        """
        sql += " WHERE pc.empresa_id = %s"
        valores = (session["empresa_id"],)

        if busca:
            sql += " AND (c.nome LIKE %s OR pc.numero_documento LIKE %s)"
            valores += (f"%{busca}%", f"%{busca}%")

        sql += " ORDER BY pc.id DESC"

        cursor.execute(sql, valores)
        return cursor.fetchall()
    finally:
        cursor.close()
        conn.close()


# ------------------------------------------------------------------ #
# CARRINHO DE PEDIDOS (mantido na sessão, sem JavaScript)             #
# ------------------------------------------------------------------ #
# Antes os itens do pedido eram montados no navegador e enviados em um
# campo escondido "itens_json". Agora cada item é adicionado por um POST
# normal, guardado na sessão do Flask e renderizado direto no template.

def carrinho_obter(chave):
    return session.get(chave, [])


def carrinho_salvar(chave, itens):
    session[chave] = itens
    session.modified = True


def carrinho_limpar(chave):
    session.pop(chave, None)
    session.modified = True


def carrinho_total(itens):
    return sum(item["quantidade"] * item["preco_unitario"] for item in itens)


def carrinho_adicionar(chave, produto, quantidade, preco_unitario):
    """Adiciona (ou soma, se já existir) um produto ao carrinho da sessão."""
    itens = carrinho_obter(chave)

    for item in itens:
        if item["produto_id"] == produto["id"]:
            item["quantidade"] += quantidade
            item["preco_unitario"] = preco_unitario
            break
    else:
        itens.append({
            "produto_id":     produto["id"],
            "sku":            produto.get("sku") or "—",
            "nome":           produto.get("nome") or "",
            "quantidade":     quantidade,
            "preco_unitario": preco_unitario,
        })

    carrinho_salvar(chave, itens)


def carrinho_remover(chave, indice):
    itens = carrinho_obter(chave)

    if 0 <= indice < len(itens):
        itens.pop(indice)
        carrinho_salvar(chave, itens)


def produtos_por_galpao():
    """Todos os produtos com saldo, com o galpão a que pertencem.

    A tela recebe a lista inteira e mostra só os do galpão escolhido, então
    trocar de galpão não precisa recarregar a página.
    """
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                e.galpao_id,
                p.id,
                p.sku,
                p.nome,
                COALESCE(p.preco_venda, 0) AS preco_venda,
                COALESCE(e.quantidade, 0)  AS estoque_disponivel
            FROM estoque e
            INNER JOIN produto p ON e.produto_id = p.id
            WHERE e.quantidade > 0 AND p.ativo = TRUE AND p.empresa_id = %s
            ORDER BY p.nome
        """, (session["empresa_id"],))
        produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_venda"] = to_float(produto["preco_venda"])
            produto["estoque_disponivel"] = to_float(produto["estoque_disponivel"])

        return produtos
    finally:
        cursor.close()
        conn.close()


def produtos_por_fornecedor():
    """Produtos ativos com os fornecedores a que estão vinculados.

    `fornecedor_id` vazio marca os produtos sem vínculo, que continuam
    disponíveis para qualquer fornecedor (mesma regra do fallback anterior).
    """
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                fp.fornecedor_id,
                p.id,
                p.sku,
                p.nome,
                COALESCE(p.ativo, 1) AS ativo,
                COALESCE(fp.preco_custo, p.preco_custo, 0) AS preco_custo
            FROM produto p
            LEFT JOIN fornecedor_produto fp
                   ON fp.produto_id = p.id AND COALESCE(fp.ativo, 1) = 1
            -- Produtos desativados também entram: comprar de novo é
            -- justamente como um produto volta a ter estoque. Antes eles
            -- sumiam e a tela dizia "Nenhum produto para este fornecedor".
            WHERE p.empresa_id = %s
            ORDER BY COALESCE(p.ativo, 1) DESC, p.nome
        """, (session["empresa_id"],))
        produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_custo"] = to_float(produto["preco_custo"])

        return produtos
    finally:
        cursor.close()
        conn.close()


def produtos_do_fornecedor(fornecedor_id):
    """Produtos vinculados ao fornecedor (ou todos os ativos, se não houver vínculo)."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT p.id, p.sku, p.nome, fp.preco_custo
            FROM fornecedor_produto fp
            JOIN produto p ON fp.produto_id = p.id
            WHERE fp.fornecedor_id = %s AND fp.ativo = 1 AND p.ativo = TRUE
            ORDER BY p.nome
        """, (fornecedor_id,))
        produtos = cursor.fetchall()

        if not produtos:
            cursor.execute("""
                SELECT p.id, p.sku, p.nome, p.preco_custo
                FROM produto p
                WHERE p.ativo = TRUE AND p.empresa_id = %s
                ORDER BY p.nome
            """, (session["empresa_id"],))
            produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_custo"] = to_float(produto["preco_custo"])

        return produtos
    finally:
        cursor.close()
        conn.close()


def produtos_do_galpao(galpao_id):
    """Produtos com saldo disponível no galpão informado."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                p.id,
                p.sku,
                p.nome,
                COALESCE(p.preco_venda, 0)  AS preco_venda,
                COALESCE(e.quantidade, 0)   AS estoque_disponivel
            FROM estoque e
            INNER JOIN produto p ON e.produto_id = p.id
            WHERE e.galpao_id = %s AND e.quantidade > 0 AND p.ativo = TRUE
            ORDER BY p.nome
        """, (galpao_id,))
        produtos = cursor.fetchall()

        for produto in produtos:
            produto["preco_venda"] = to_float(produto["preco_venda"])
            produto["estoque_disponivel"] = to_float(produto["estoque_disponivel"])

        return produtos
    finally:
        cursor.close()
        conn.close()



# ------------------------------------------------------------------ #
# API — produtos disponíveis por galpão
# ------------------------------------------------------------------ #

@app.route("/api/produtos_do_galpao/<int:galpao_id>")
@login_obrigatorio
def api_produtos_do_galpao(galpao_id):
    from flask import jsonify

    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT p.id, p.sku, p.nome, p.preco_venda,
                   e.quantidade AS estoque_disponivel
            FROM estoque e
            JOIN produto p ON e.produto_id = p.id
            WHERE e.galpao_id = %s AND e.quantidade > 0
            ORDER BY p.nome ASC
        """, (galpao_id,))
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()


@app.route("/api/todos_produtos")
@login_obrigatorio
def api_todos_produtos():
    from flask import jsonify

    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT id, sku, nome, preco_custo
            FROM produto
            WHERE ativo = TRUE AND empresa_id = %s
            ORDER BY nome ASC
        """, (session["empresa_id"],))
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()


@app.route("/api/produtos_do_fornecedor/<int:fornecedor_id>")
@login_obrigatorio
def api_produtos_do_fornecedor(fornecedor_id):
    from flask import jsonify

    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT
                p.id,
                p.sku,
                p.nome,
                fp.preco_custo,
                COALESCE(e_total.estoque_disponivel, 0) AS estoque_disponivel
            FROM fornecedor_produto fp
            JOIN produto p ON fp.produto_id = p.id
            LEFT JOIN (
                SELECT produto_id, SUM(quantidade) AS estoque_disponivel
                FROM estoque
                GROUP BY produto_id
            ) e_total ON e_total.produto_id = p.id
            WHERE fp.fornecedor_id = %s
              AND COALESCE(fp.ativo, 1) = 1
            ORDER BY COALESCE(p.ativo, 1) DESC, p.nome ASC
        """, (fornecedor_id,))
        return jsonify(cursor.fetchall())
    finally:
        cursor.close()
        conn.close()


# ------------------------------------------------------------------ #
# PEDIDOS DE ENTRADA  (usa tabela: pedido_fornecedor)                 #
# ------------------------------------------------------------------ #

CARRINHO_ENTRADA = "carrinho_entrada"


@app.route("/cadastro_pedido_entrada")
@login_obrigatorio
def cadastro_pedido_entrada():
    # O fornecedor escolhido volta pela query string, então a lista de
    # produtos é montada aqui no servidor — sem chamada AJAX.
    fornecedor_id = to_int(request.args.get("fornecedor_id")) or None
    galpao_id     = to_int(request.args.get("galpao_id")) or None
    produto_id    = to_int(request.args.get("produto_id")) or None
    itens         = carrinho_obter(CARRINHO_ENTRADA)
    # A lista completa vai para a tela, que mostra só os produtos do
    # fornecedor escolhido. Sem recarregar a página para trocar de fornecedor.
    produtos = produtos_por_fornecedor()

    return render_template(
        "pedidos_fornecedor.html",
        galpoes=Galpao.find_all(),
        fornecedores=Fornecedor.find_all(),
        produtos=produtos,
        fornecedor_id=fornecedor_id,
        galpao_id=galpao_id,
        produto_id=produto_id,
        itens=itens,
        total=carrinho_total(itens)
    )


@app.route("/pedido_entrada/item/adicionar", methods=["POST"])
@login_obrigatorio
def adicionar_item_entrada():
    fornecedor_id = to_int(request.form.get("fornecedor_id")) or None
    galpao_id     = to_int(request.form.get("galpao_id")) or None
    produto_id    = to_int(request.form.get("produto_id"))
    quantidade    = to_float(request.form.get("quantidade"))
    preco         = to_float(request.form.get("preco_unitario"))

    destino = url_for("cadastro_pedido_entrada",
                      fornecedor_id=fornecedor_id, galpao_id=galpao_id)

    if not fornecedor_id:
        flash("Selecione o fornecedor antes de adicionar produtos.", "erro")
        return redirect(destino)

    if not produto_id:
        flash("Selecione o produto.", "erro")
        return redirect(destino)

    if quantidade <= 0:
        flash("A quantidade deve ser maior que zero.", "erro")
        return redirect(destino)

    if quantidade != int(quantidade):
        flash("Informe a quantidade em unidades inteiras.", "erro")
        return redirect(destino)

    # Preço de compra negativo entrava no pedido e reduzia o total
    if preco < 0:
        flash("O preço unitário não pode ser negativo.", "erro")
        return redirect(destino)

    produto = Produto.find_by_id(produto_id)
    if not produto:
        flash("Produto não encontrado.", "erro")
        return redirect(destino)

    carrinho_adicionar(CARRINHO_ENTRADA, produto, quantidade, preco)
    flash(f"{produto['nome']} adicionado ao pedido.", "sucesso")
    return redirect(destino)


@app.route("/pedido_entrada/item/remover/<int:indice>", methods=["POST"])
@login_obrigatorio
def remover_item_entrada(indice):
    carrinho_remover(CARRINHO_ENTRADA, indice)
    return redirect(url_for(
        "cadastro_pedido_entrada",
        fornecedor_id=to_int(request.form.get("fornecedor_id")) or None,
        galpao_id=to_int(request.form.get("galpao_id")) or None
    ))


@app.route("/pedido_entrada/limpar", methods=["POST"])
@login_obrigatorio
def limpar_pedido_entrada():
    carrinho_limpar(CARRINHO_ENTRADA)
    flash("Itens do pedido removidos.", "sucesso")
    return redirect(url_for("cadastro_pedido_entrada"))


@app.route("/pedidos_entrada")
@login_obrigatorio
def listar_pedidos_entrada():
    return redirect(url_for("pedidos", busca=request.args.get("busca") or None))


# Mantida por compatibilidade: os redirecionamentos antigos apontavam para cá.
@app.route("/pedidos_entrada/novo")
@login_obrigatorio
def novo_pedido_entrada():
    return redirect(url_for("cadastro_pedido_entrada"))


@app.route("/salvar_pedido_entrada", methods=["POST"])
@login_obrigatorio
def salvar_pedido_entrada():
    fornecedor_id    = to_int(request.form.get("fornecedor_id")) or None
    galpao_id        = to_int(request.form.get("galpao_id")) or None
    numero_documento = (request.form.get("numero_documento") or "").strip() or None
    data_prevista    = (request.form.get("data_entrada") or "").strip() or None
    observacao       = (request.form.get("observacao") or "").strip() or None

    itens = carrinho_obter(CARRINHO_ENTRADA)

    destino = url_for("cadastro_pedido_entrada",
                      fornecedor_id=fornecedor_id, galpao_id=galpao_id)

    if not fornecedor_id or not galpao_id:
        flash("Selecione o fornecedor e o galpão de destino.", "erro")
        return redirect(destino)

    if not itens:
        flash("Adicione pelo menos um item ao pedido.", "erro")
        return redirect(destino)

    valor_total = carrinho_total(itens)

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO pedido_fornecedor
                (empresa_id, fornecedor_id, galpao_id, numero_documento,
                 data_prevista, observacao, status, valor_total)
            VALUES (%s, %s, %s, %s, %s, %s, 'recebido', %s)
        """, (session["empresa_id"], fornecedor_id, galpao_id, numero_documento,
              data_prevista, observacao, valor_total))
        pedido_id = cursor.lastrowid

        for item in itens:
            cursor.execute("""
                INSERT INTO item_pedido_fornecedor
                    (pedido_fornecedor_id, produto_id, quantidade, preco_unitario)
                VALUES (%s, %s, %s, %s)
            """, (pedido_id, item["produto_id"],
                  item["quantidade"], item["preco_unitario"]))

            # AUTO-VÍNCULO: associa o produto ao fornecedor, se ainda não estiver
            cursor.execute("""
                INSERT INTO fornecedor_produto
                    (fornecedor_id, produto_id, preco_custo, desconto,
                     quantidade_minima, prazo_entrega_dias, ativo)
                VALUES (%s, %s, %s, 0, 1, 0, 1)
                ON DUPLICATE KEY UPDATE
                    preco_custo = VALUES(preco_custo),
                    ativo = 1
            """, (fornecedor_id, item["produto_id"], item["preco_unitario"]))

            # Entrada de estoque no galpão de destino
            cursor.execute("""
                INSERT INTO estoque (produto_id, galpao_id, quantidade, estoque_minimo)
                VALUES (%s, %s, %s, 0)
                ON DUPLICATE KEY UPDATE quantidade = quantidade + VALUES(quantidade)
            """, (item["produto_id"], galpao_id, item["quantidade"]))

            # Registra a movimentação correspondente
            cursor.execute("""
                INSERT INTO movimentacao
                    (empresa_id, produto_id, galpao_id, tipo, quantidade, observacao)
                VALUES (%s, %s, %s, 'entrada', %s, %s)
            """, (session["empresa_id"], item["produto_id"], galpao_id, item["quantidade"],
                  f"Pedido de entrada #{pedido_id}"))

        conn.commit()
        carrinho_limpar(CARRINHO_ENTRADA)
        flash("Pedido de entrada cadastrado com sucesso!", "sucesso")
        return redirect(url_for("visualizar_pedido_entrada", pedido_id=pedido_id))

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao cadastrar pedido de entrada: {mensagem_erro(e)}", "erro")
        return redirect(destino)
    finally:
        cursor.close()
        conn.close()


@app.route("/pedidos_entrada/visualizar/<int:pedido_id>")
@login_obrigatorio
def visualizar_pedido_entrada(pedido_id):
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pf.*, f.nome AS fornecedor_nome, g.nome AS galpao_nome
            FROM pedido_fornecedor pf
            LEFT JOIN fornecedor f ON pf.fornecedor_id = f.id
            LEFT JOIN galpao     g ON pf.galpao_id     = g.id
            WHERE pf.id = %s
        """, (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("listar_pedidos_entrada"))

        cursor.execute("""
            SELECT ipf.*, p.nome AS produto_nome, p.sku
            FROM item_pedido_fornecedor ipf
            JOIN produto p ON ipf.produto_id = p.id
            WHERE ipf.pedido_fornecedor_id = %s
        """, (pedido_id,))
        pedido["itens"] = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template("pedidos_entrada/visualizar.html", pedido=pedido)


# ------------------------------------------------------------------ #
# PEDIDOS DE SAÍDA  (usa tabela: pedido_cliente)                      #
# ------------------------------------------------------------------ #

CARRINHO_SAIDA = "carrinho_saida"


@app.route("/cadastro_pedido/<int:cliente_id>")
@login_obrigatorio
def cadastro_pedido(cliente_id):
    cliente = Cliente.find_by_id(cliente_id)

    if not cliente:
        flash("Cliente não encontrado.", "erro")
        return redirect(url_for("cliente"))

    # Assim como na entrada, o galpão volta pela query string e os produtos
    # disponíveis são carregados aqui no servidor.
    galpao_id  = to_int(request.args.get("galpao_id")) or None
    produto_id = to_int(request.args.get("produto_id")) or None
    itens      = carrinho_obter(CARRINHO_SAIDA)
    # Lista completa; a tela filtra pelo galpão escolhido
    produtos = produtos_por_galpao()

    return render_template(
        "cadastro_pedidos.html",
        cliente=cliente,
        clientes=Cliente.find_all(),
        galpoes=Galpao.find_all(),
        produtos=produtos,
        galpao_id=galpao_id,
        produto_id=produto_id,
        itens=itens,
        total=carrinho_total(itens)
    )


@app.route("/cadastro_pedido_saida")
@login_obrigatorio
def cadastro_pedido_saida():
    # Sem cliente definido: mostra a tela com o seletor de clientes.
    galpao_id  = to_int(request.args.get("galpao_id")) or None
    produto_id = to_int(request.args.get("produto_id")) or None
    itens      = carrinho_obter(CARRINHO_SAIDA)
    produtos = produtos_por_galpao()

    return render_template(
        "cadastro_pedidos.html",
        cliente=None,
        clientes=Cliente.find_all(),
        galpoes=Galpao.find_all(),
        produtos=produtos,
        galpao_id=galpao_id,
        produto_id=produto_id,
        itens=itens,
        total=carrinho_total(itens)
    )


def destino_pedido_saida(cliente_id, galpao_id):
    if cliente_id:
        return url_for("cadastro_pedido", cliente_id=cliente_id, galpao_id=galpao_id)
    return url_for("cadastro_pedido_saida", galpao_id=galpao_id)


@app.route("/pedido_saida/item/adicionar", methods=["POST"])
@login_obrigatorio
def adicionar_item_saida():
    cliente_id = to_int(request.form.get("cliente_id")) or None
    galpao_id  = to_int(request.form.get("galpao_id")) or None
    produto_id = to_int(request.form.get("produto_id"))
    quantidade = to_float(request.form.get("quantidade"))

    destino = destino_pedido_saida(cliente_id, galpao_id)

    # O estoque é contado em unidades inteiras: 2,5 virava 3 sem aviso
    if quantidade != int(quantidade):
        flash("Informe a quantidade em unidades inteiras.", "erro")
        return redirect(destino)

    if not galpao_id:
        flash("Selecione o galpão de retirada antes de adicionar produtos.", "erro")
        return redirect(destino)

    if not produto_id:
        flash("Selecione o produto.", "erro")
        return redirect(destino)

    if quantidade <= 0:
        flash("A quantidade deve ser maior que zero.", "erro")
        return redirect(destino)

    # O preço e a disponibilidade vêm do banco, não do formulário.
    disponiveis = {p["id"]: p for p in produtos_do_galpao(galpao_id)}
    produto = disponiveis.get(produto_id)

    if not produto:
        flash("Este produto não está disponível no galpão selecionado.", "erro")
        return redirect(destino)

    ja_no_carrinho = sum(
        item["quantidade"] for item in carrinho_obter(CARRINHO_SAIDA)
        if item["produto_id"] == produto_id
    )

    if ja_no_carrinho + quantidade > produto["estoque_disponivel"]:
        flash(
            f"Estoque insuficiente para {produto['nome']} "
            f"(disponível: {produto['estoque_disponivel']:g}).",
            "erro"
        )
        return redirect(destino)

    carrinho_adicionar(CARRINHO_SAIDA, produto, quantidade, produto["preco_venda"])
    flash(f"{produto['nome']} adicionado ao pedido.", "sucesso")
    return redirect(destino)


@app.route("/pedido_saida/item/remover/<int:indice>", methods=["POST"])
@login_obrigatorio
def remover_item_saida(indice):
    carrinho_remover(CARRINHO_SAIDA, indice)
    return redirect(destino_pedido_saida(
        to_int(request.form.get("cliente_id")) or None,
        to_int(request.form.get("galpao_id")) or None
    ))


@app.route("/pedido_saida/limpar", methods=["POST"])
@login_obrigatorio
def limpar_pedido_saida():
    carrinho_limpar(CARRINHO_SAIDA)
    flash("Itens do pedido removidos.", "sucesso")
    return redirect(destino_pedido_saida(
        to_int(request.form.get("cliente_id")) or None, None
    ))


@app.route("/pedidos_saida")
@login_obrigatorio
def listar_pedidos_saida():
    # Cada pedido de saída pertence a um cliente, então a consulta começa
    # pela lista de clientes em vez de uma listagem geral.
    flash("Escolha o cliente para ver os pedidos de saída.", "sucesso")
    return redirect(url_for("cliente"))


@app.route("/salvar_pedido_saida", methods=["POST"])
@login_obrigatorio
def salvar_pedido_saida():
    cliente_id       = to_int(request.form.get("cliente_id")) or None
    galpao_id        = to_int(request.form.get("galpao_id")) or None
    numero_documento = (request.form.get("numero_documento") or "").strip() or None
    data_saida       = (request.form.get("data_saida") or "").strip() or None
    observacao       = (request.form.get("observacao") or "").strip() or None

    itens = carrinho_obter(CARRINHO_SAIDA)

    destino = destino_pedido_saida(cliente_id, galpao_id)

    if not cliente_id:
        flash("Selecione o cliente do pedido.", "erro")
        return redirect(destino)

    if not galpao_id:
        flash("Selecione o galpão de retirada.", "erro")
        return redirect(destino)

    if not itens:
        flash("Adicione pelo menos um item ao pedido.", "erro")
        return redirect(destino)

    valor_total = carrinho_total(itens)

    conn = Database.connect()
    cursor = conn.cursor()
    try:
        # Sem data informada o banco usa a data/hora atual (DEFAULT do campo)
        if data_saida:
            cursor.execute("""
                INSERT INTO pedido_cliente
                    (empresa_id, cliente_id, galpao_id, numero_documento,
                     observacao, valor_total, status_pedido, data_pedido)
                VALUES (%s, %s, %s, %s, %s, %s, 'pendente', %s)
            """, (session["empresa_id"], cliente_id, galpao_id, numero_documento, observacao,
                  valor_total, data_saida))
        else:
            cursor.execute("""
                INSERT INTO pedido_cliente
                    (empresa_id, cliente_id, galpao_id, numero_documento,
                     observacao, valor_total, status_pedido)
                VALUES (%s, %s, %s, %s, %s, %s, 'pendente')
            """, (session["empresa_id"], cliente_id, galpao_id, numero_documento, observacao, valor_total))
        pedido_id = cursor.lastrowid

        for item in itens:
            # Confere o saldo dentro da transação, para não deixar estoque negativo
            cursor.execute("""
                SELECT quantidade FROM estoque
                WHERE produto_id = %s AND galpao_id = %s
            FOR UPDATE
            """, (item["produto_id"], galpao_id))

            saldo = cursor.fetchone()
            disponivel = float(saldo[0]) if saldo else 0.0

            if disponivel < item["quantidade"]:
                raise ValueError(
                    f"Estoque insuficiente para {item['nome']} "
                    f"(disponível: {disponivel:g})."
                )

            cursor.execute("""
                INSERT INTO item_pedido_cliente
                    (pedido_cliente_id, produto_id, quantidade, preco_unitario_no_momento)
                VALUES (%s, %s, %s, %s)
            """, (pedido_id, item["produto_id"],
                  item["quantidade"], item["preco_unitario"]))

            cursor.execute("""
                UPDATE estoque SET quantidade = quantidade - %s
                WHERE produto_id = %s AND galpao_id = %s
            """, (item["quantidade"], item["produto_id"], galpao_id))

            cursor.execute("""
                INSERT INTO movimentacao
                    (empresa_id, produto_id, galpao_id, tipo, quantidade, observacao)
                VALUES (%s, %s, %s, 'saida', %s, %s)
            """, (session["empresa_id"], item["produto_id"], galpao_id, item["quantidade"],
                  f"Pedido de saída #{pedido_id}"))

        conn.commit()
        carrinho_limpar(CARRINHO_SAIDA)
        flash("Pedido de saída cadastrado com sucesso!", "sucesso")
        return redirect(url_for("visualizar_pedido_saida", pedido_id=pedido_id))

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao cadastrar pedido de saída: {mensagem_erro(e)}", "erro")
        return redirect(destino)
    finally:
        cursor.close()
        conn.close()


@app.route("/pedidos_saida/visualizar/<int:pedido_id>")
@login_obrigatorio
def visualizar_pedido_saida(pedido_id):
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT pc.*, c.nome AS cliente_nome, g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c ON pc.cliente_id = c.id
            LEFT JOIN galpao  g ON pc.galpao_id  = g.id
            WHERE pc.id = %s
        """, (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("listar_pedidos_saida"))

        cursor.execute("""
            SELECT ipc.*, p.nome AS produto_nome, p.sku
            FROM item_pedido_cliente ipc
            JOIN produto p ON ipc.produto_id = p.id
            WHERE ipc.pedido_cliente_id = %s
        """, (pedido_id,))
        pedido["itens"] = cursor.fetchall()

    finally:
        cursor.close()
        conn.close()

    return render_template("pedidos_saida/visualizar.html", pedido=pedido)

STATUS_PEDIDO_CLIENTE = ["pendente", "pago", "enviado", "concluido", "cancelado"]


@app.route("/pedido_cliente/<int:pedido_id>/editar")
@login_obrigatorio
def editar_pedido_cliente(pedido_id):
    """Tela de edição de um pedido de saída.

    Antes a tela de pedidos do cliente chamava `editar_pedido`, que abre um
    pedido de FORNECEDOR: o botão levava para outro registro. Além disso o
    botão era um <button href=...>, que não navega para lugar nenhum.
    """
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("""
            SELECT pc.*, c.nome AS cliente_nome, g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c ON c.id = pc.cliente_id
            LEFT JOIN galpao  g ON g.id = pc.galpao_id
            WHERE pc.id = %s
        """, (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("cliente"))

        cursor.execute("""
            SELECT ipc.*, p.nome, p.sku
            FROM item_pedido_cliente ipc
            JOIN produto p ON p.id = ipc.produto_id
            WHERE ipc.pedido_cliente_id = %s
        """, (pedido_id,))
        itens = cursor.fetchall()

    finally:
        cursor.close()
        conexao.close()

    return render_template(
        "editar_pedido_cliente.html",
        pedido=pedido,
        itens=itens,
        status_possiveis=STATUS_PEDIDO_CLIENTE
    )


@app.route("/pedido_cliente/<int:pedido_id>/atualizar", methods=["POST"])
@login_obrigatorio
def atualizar_pedido_cliente(pedido_id):
    """Grava os dados do pedido que não mexem no estoque.

    Quantidades e produtos não são editados aqui de propósito: alterá-los
    mudaria o saldo já baixado no fechamento. Para isso existe o cancelamento,
    que devolve o estoque, e a abertura de um novo pedido.
    """
    numero_documento = (request.form.get("numero_documento") or "").strip() or None
    observacao       = (request.form.get("observacao") or "").strip() or None
    status           = (request.form.get("status_pedido") or "").strip()

    if status not in STATUS_PEDIDO_CLIENTE:
        flash("Situação do pedido inválida.", "erro")
        return redirect(url_for("editar_pedido_cliente", pedido_id=pedido_id))

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT cliente_id, status_pedido FROM pedido_cliente WHERE id = %s",
            (pedido_id,)
        )
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("cliente"))

        # Cancelar devolve estoque, então tem rota própria e não entra aqui
        if status == "cancelado" and pedido["status_pedido"] != "cancelado":
            flash(
                "Para cancelar, use o botão de cancelamento: ele devolve o "
                "estoque ao galpão.",
                "erro"
            )
            return redirect(url_for("editar_pedido_cliente", pedido_id=pedido_id))

        if pedido["status_pedido"] == "cancelado" and status != "cancelado":
            flash("Um pedido cancelado não pode voltar a ficar ativo.", "erro")
            return redirect(url_for("editar_pedido_cliente", pedido_id=pedido_id))

        cursor.execute("""
            UPDATE pedido_cliente
            SET numero_documento = %s, observacao = %s, status_pedido = %s
            WHERE id = %s
        """, (numero_documento, observacao, status, pedido_id))

        conexao.commit()
        flash("Pedido atualizado com sucesso!", "sucesso")

        cliente_id = pedido["cliente_id"]

    except Exception as e:
        conexao.rollback()
        flash(f"Erro ao atualizar o pedido: {mensagem_erro(e)}", "erro")
        return redirect(url_for("editar_pedido_cliente", pedido_id=pedido_id))

    finally:
        cursor.close()
        conexao.close()

    if cliente_id:
        return redirect(url_for("pedidos_clientes", cliente_id=cliente_id))

    return redirect(url_for("listar_pedidos_saida"))


@app.route("/editar_pedido/<int:id>")
@login_obrigatorio
def editar_pedido(id):
    # A edição de um pedido já recebido mexeria no saldo de estoque, então
    # a tela é somente leitura: mostra o pedido e seus itens.
    return redirect(url_for("visualizar_pedido_entrada", pedido_id=id))

@app.route("/deletar_pedido/<int:id>", methods=["POST"])
@login_obrigatorio
def deletar_pedido(id):
    """Exclui um pedido de ENTRADA (fornecedor) e desfaz a entrada de estoque."""
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT galpao_id FROM pedido_fornecedor WHERE id = %s", (id,))
        pedido = cursor.fetchone()

        if not pedido:
            raise ValueError("Pedido de entrada não encontrado.")

        # Devolve o estoque que este pedido havia somado ao galpão
        cursor.execute("""
            SELECT produto_id, quantidade
            FROM item_pedido_fornecedor
            WHERE pedido_fornecedor_id = %s
        """, (id,))

        for item in cursor.fetchall():
            cursor.execute("""
                UPDATE estoque SET quantidade = quantidade - %s
                WHERE produto_id = %s AND galpao_id = %s
            """, (item["quantidade"], item["produto_id"], pedido["galpao_id"]))

        cursor.execute(
            "DELETE FROM item_pedido_fornecedor WHERE pedido_fornecedor_id = %s", (id,)
        )
        cursor.execute("DELETE FROM pedido_fornecedor WHERE id = %s", (id,))

        conn.commit()
        flash("Pedido de entrada excluído e estoque ajustado.", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pedido: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("listar_pedidos_entrada"))


@app.route("/deletar_pedido_saida/<int:id>", methods=["POST"])
@login_obrigatorio
def deletar_pedido_saida(id):
    """Exclui um pedido de SAÍDA (cliente) e devolve o estoque ao galpão.

    Antes a tela de pedidos do cliente chamava "deletar_pedido", que apaga
    pedidos de fornecedor — ou seja, excluía o registro errado.
    """
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT cliente_id, galpao_id, status_pedido FROM pedido_cliente WHERE id = %s",
            (id,)
        )
        pedido = cursor.fetchone()

        if not pedido:
            raise ValueError("Pedido de saída não encontrado.")

        # Um pedido cancelado já teve o estoque devolvido
        if pedido["status_pedido"] != "cancelado":
            cursor.execute("""
                SELECT produto_id, quantidade
                FROM item_pedido_cliente
                WHERE pedido_cliente_id = %s
            """, (id,))

            for item in cursor.fetchall():
                cursor.execute("""
                    UPDATE estoque SET quantidade = quantidade + %s
                    WHERE produto_id = %s AND galpao_id = %s
                """, (item["quantidade"], item["produto_id"], pedido["galpao_id"]))

        cliente_id = pedido["cliente_id"]

        cursor.execute(
            "DELETE FROM item_pedido_cliente WHERE pedido_cliente_id = %s", (id,)
        )
        cursor.execute("DELETE FROM pedido_cliente WHERE id = %s", (id,))

        conn.commit()
        flash("Pedido de saída excluído e estoque ajustado.", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao excluir pedido: {mensagem_erro(e)}", "erro")
        return redirect(url_for("listar_pedidos_saida"))

    finally:
        cursor.close()
        conn.close()

    if cliente_id:
        return redirect(url_for("pedidos_clientes", cliente_id=cliente_id))
    return redirect(url_for("listar_pedidos_saida"))


# ---------------- PEDIDOS CLIENTES ---------------- #

@app.route("/pedidos_cliente/<int:cliente_id>")
@login_obrigatorio
def pedidos_clientes(cliente_id):
    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        cursor.execute("SELECT * FROM cliente WHERE id = %s", (cliente_id,))
        c = cursor.fetchone()

        if not c:
            flash("Cliente não encontrado.", "erro")
            return redirect(url_for("cliente"))

        busca = (request.args.get("busca") or "").strip()

        sql = """
            SELECT pc.*, c.nome AS cliente_nome, c.email AS cliente_email
            FROM pedido_cliente pc
            JOIN cliente c ON pc.cliente_id = c.id
            WHERE pc.cliente_id = %s
        """
        valores = [cliente_id]

        if busca:
            sql += " AND pc.numero_documento LIKE %s"
            valores.append(f"%{busca}%")

        sql += " ORDER BY pc.data_pedido DESC"

        cursor.execute(sql, tuple(valores))
        pedidos = cursor.fetchall()

        pedidos, menu = ordenar_e_filtrar(pedidos, "pedidos")

        return render_template(
            "pedidos_cliente.html",
            cliente=c,
            pedidos=pedidos,
            menu_filtros=menu,
            galpoes=Galpao.find_all(),
            produtos=Produto.find_all(),
            busca=busca
        )
    except Exception as e:
        app.logger.exception("Falha ao carregar pedidos do cliente")
        flash(f"Erro ao carregar pedidos do cliente: {mensagem_erro(e)}", "erro")
        return redirect(url_for("cliente"))
    finally:
        cursor.close()
        conexao.close()
        
# ---------------- INFO PEDIDOS ------------#

@app.route("/pedido-cliente/<int:pedido_id>")
@login_obrigatorio
def info_pedido_cliente(pedido_id):

    conexao = Database.connect()
    cursor = conexao.cursor(dictionary=True)

    try:
        # Dados do pedido
        sql = """
            SELECT
                pc.*,
                c.nome AS cliente_nome,
                c.email AS cliente_email,
                c.telefone AS cliente_telefone,
                c.cidade,
                c.estado,
                g.nome AS galpao_nome
            FROM pedido_cliente pc
            LEFT JOIN cliente c
                ON pc.cliente_id = c.id
            LEFT JOIN galpao g
                ON pc.galpao_id = g.id
            WHERE pc.id = %s
        """

        cursor.execute(sql, (pedido_id,))
        pedido = cursor.fetchone()

        if not pedido:
            flash("Pedido não encontrado.", "erro")
            return redirect(url_for("cliente"))

        # Itens do pedido
        sql_itens = """
            SELECT
                ipc.*,
                p.nome,
                p.sku,
                p.codigo_barras
            FROM item_pedido_cliente ipc
            INNER JOIN produto p
                ON ipc.produto_id = p.id
            WHERE ipc.pedido_cliente_id = %s
        """

        cursor.execute(sql_itens, (pedido_id,))
        itens = cursor.fetchall()

        return render_template(
            "info_pedido_cliente.html",
            pedido=pedido,
            itens=itens
        )

    except Exception as e:
        flash(f"Erro ao carregar pedido: {mensagem_erro(e)}", "erro")
        return redirect(url_for("cliente"))

    finally:
        cursor.close()
        conexao.close()
# ---------------- PEDIDOS ---------------- #

@app.route("/pedidos")
@login_obrigatorio
def pedidos():
    """Pedidos de entrada (compras de fornecedor).

    As saídas não aparecem aqui: elas pertencem ao cliente e ficam em
    /pedidos_cliente/<cliente_id>.
    """
    busca = (request.args.get("busca") or "").strip()

    pedidos, menu = ordenar_e_filtrar(buscar_pedidos_entrada(busca), "pedidos")

    return render_template(
        "pedidos.html",
        pedidos=pedidos,
        menu_filtros=menu,
        busca=busca
    )


@app.route("/pedido/salvar", methods=["POST"])
@login_obrigatorio
def salvar_pedido():
    dados = {
        "produto_id": to_int(request.form.get("produto_id")),
        "tipo": (request.form.get("tipo") or "").upper(),
        "quantidade": to_int(request.form.get("quantidade")),
        "observacao": request.form.get("observacao")
    }

    try:
        PedidoCliente.create(dados)
        flash("Pedido criado com sucesso!", "sucesso")
        return redirect(url_for("pedidos"))
    except Exception as e:
        flash(f"Erro ao criar pedido: {mensagem_erro(e)}", "erro")
        return redirect(url_for("produtos"))


@app.route("/pedido/processar/<int:id>", methods=["POST"])
@login_obrigatorio
def processar_pedido(id):
    # Conclui um pedido de saída pendente. A baixa de estoque já ocorreu no
    # fechamento do pedido, então aqui só o status muda.
    conn = Database.connect()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute("SELECT status_pedido FROM pedido_cliente WHERE id = %s", (id,))
        pedido = cursor.fetchone()

        if not pedido:
            raise ValueError("Pedido não encontrado.")

        if pedido["status_pedido"] != "pendente":
            raise ValueError("Só é possível processar pedidos pendentes.")

        cursor.execute("""
            UPDATE pedido_cliente
            SET status_pedido = 'concluido'
            WHERE id = %s
        """, (id,))

        conn.commit()
        flash("Pedido processado com sucesso!", "sucesso")

    except Exception as e:
        conn.rollback()
        flash(f"Erro ao processar pedido: {mensagem_erro(e)}", "erro")

    finally:
        cursor.close()
        conn.close()

    return redirect(url_for("pedidos"))

@app.route("/pedido/cancelar/<int:id>", methods=["POST"])
@login_obrigatorio
def cancelar_pedido(id):
    # PedidoCliente.cancelar devolve o estoque e marca o pedido como cancelado.
    try:
        PedidoCliente.cancelar(id)
        flash("Pedido cancelado e estoque devolvido.", "sucesso")
    except Exception as e:
        flash(f"Erro ao cancelar pedido: {mensagem_erro(e)}", "erro")
    return redirect(url_for("pedidos"))

# ---------------- ERRO 404 ---------------- #

@app.errorhandler(404)
def pagina_nao_encontrada(error):
    return render_template("404.html"), 404

# ---------------- RUN ---------------- #

if __name__ == "__main__":
    # Ative o modo debug apenas em desenvolvimento: FLASK_DEBUG=1 python app.py
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")