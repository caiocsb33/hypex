CREATE DATABASE IF NOT EXISTS sistema_estoque;
USE sistema_estoque;

-- FORNECEDOR
CREATE TABLE fornecedor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    telefone VARCHAR(20),
    cnpj VARCHAR(18) UNIQUE,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- CLIENTE
CREATE TABLE cliente (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cpf_cnpj VARCHAR(18) UNIQUE,
    email VARCHAR(100),
    telefone VARCHAR(20),
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- FUNCIONARIO
CREATE TABLE funcionario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cpf VARCHAR(14) UNIQUE,
    email VARCHAR(100),
    cargo VARCHAR(50),
    data_admissao DATE,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- USUARIO (LOGIN)
CREATE TABLE usuario (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(100) UNIQUE NOT NULL,
    senha VARCHAR(255) NOT NULL,
    tipo ENUM('admin', 'operador', 'gerente') DEFAULT 'operador',
    funcionario_id INT UNIQUE NULL,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (funcionario_id) REFERENCES funcionario(id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- GALPAO
CREATE TABLE galpao (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cep VARCHAR(10),
    localizacao VARCHAR(100),
    total_prateleiras INT,
    niveis_por_prateleira INT,
    caixas_por_nivel INT,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- EMPILHADEIRA
CREATE TABLE empilhadeira (
    id INT AUTO_INCREMENT PRIMARY KEY,
    modelo VARCHAR(100),
    capacidade INT,
    galpao_id INT NULL,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (galpao_id) REFERENCES galpao(id)
        ON DELETE SET NULL ON UPDATE CASCADE
);

-- PRODUTO
CREATE TABLE produto (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sku VARCHAR(50) UNIQUE NOT NULL,
    nome VARCHAR(100) NOT NULL,
    descricao TEXT,
    categoria VARCHAR(50),
    unidade_medida VARCHAR(20),
    preco_custo DECIMAL(10,2),
    preco_venda DECIMAL(10,2),
    peso DECIMAL(10,2),
    volume DECIMAL(10,2),
    tipo ENUM('leve', 'medio', 'pesado', 'fragil') DEFAULT 'medio',
    codigo_barras VARCHAR(100) UNIQUE,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- FORNECEDOR X PRODUTO 
CREATE TABLE fornecedor_produto (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fornecedor_id INT,
    produto_id INT,
    preco_custo DECIMAL(10,2),
    desconto DECIMAL(5,2),
    quantidade_minima INT,
    prazo_entrega_dias INT,
    ativo BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (fornecedor_id) REFERENCES fornecedor(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produto(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (fornecedor_id, produto_id)
);

-- LOCALIZACAO
CREATE TABLE localizacao (
    id INT AUTO_INCREMENT PRIMARY KEY,
    galpao_id INT,
    setor VARCHAR(10),
    prateleira INT,
    nivel INT,
    capacidade_maxima INT,
    FOREIGN KEY (galpao_id) REFERENCES galpao(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (galpao_id, setor, prateleira, nivel)
);

-- ESTOQUE 
CREATE TABLE estoque (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produto_id INT,
    galpao_id INT,
    localizacao_id INT,
    quantidade DECIMAL(12,3) DEFAULT 0,
    estoque_minimo DECIMAL(12,3) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (produto_id) REFERENCES produto(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (galpao_id) REFERENCES galpao(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (localizacao_id) REFERENCES localizacao(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE (produto_id, galpao_id, localizacao_id)
);

-- LOTE
CREATE TABLE lote (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produto_id INT,
    galpao_id INT,
    localizacao_id INT,
    numero_lote VARCHAR(50),
    data_validade DATE,
    quantidade DECIMAL(12,3),
    FOREIGN KEY (produto_id) REFERENCES produto(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (galpao_id) REFERENCES galpao(id)
        ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (localizacao_id) REFERENCES localizacao(id)
        ON DELETE CASCADE ON UPDATE CASCADE
);

-- MOVIMENTACAO
CREATE TABLE movimentacao (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produto_id INT NOT NULL,
    galpao_id INT NOT NULL,
    galpao_destino_id INT NULL,
    funcionario_id INT NULL,
    tipo ENUM('entrada', 'saida', 'transferencia', 'ajuste_inventario') NOT NULL,
    quantidade DECIMAL(12,3) NOT NULL,
    data_movimentacao TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    observacao TEXT,
    FOREIGN KEY (produto_id) REFERENCES produto(id)
        ON DELETE CASCADE,
    FOREIGN KEY (galpao_id) REFERENCES galpao(id)
        ON DELETE CASCADE,
    FOREIGN KEY (galpao_destino_id) REFERENCES galpao(id)
        ON DELETE SET NULL,
    FOREIGN KEY (funcionario_id) REFERENCES funcionario(id)
        ON DELETE SET NULL
);

-- PEDIDO MOVIMENTACAO
CREATE TABLE pedido_movimentacao (
    id INT AUTO_INCREMENT PRIMARY KEY,
    produto_id INT,
    tipo VARCHAR(20),
    quantidade INT,
    status VARCHAR(20),
    observacao TEXT,
    data_pedido DATETIME,
    data_processamento DATETIME,
    FOREIGN KEY (produto_id) REFERENCES produto(id)
);

-- PEDIDO FORNECEDOR
CREATE TABLE pedido_fornecedor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fornecedor_id INT,
    funcionario_id INT,
    galpao_id INT,
    data_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data_prevista DATE,
    data_recebimento DATE,
    status ENUM('pendente', 'aprovado', 'enviado', 'recebido', 'cancelado') DEFAULT 'pendente',
    valor_total DECIMAL(12,2) DEFAULT 0,
    observacao TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (fornecedor_id) REFERENCES fornecedor(id),
    FOREIGN KEY (funcionario_id) REFERENCES funcionario(id),
    FOREIGN KEY (galpao_id) REFERENCES galpao(id)
);

-- ITEM PEDIDO FORNECEDOR
CREATE TABLE item_pedido_fornecedor (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pedido_fornecedor_id INT,
    produto_id INT,
    quantidade DECIMAL(12,3),
    preco_unitario DECIMAL(10,2),
    desconto DECIMAL(5,2) DEFAULT 0,
    FOREIGN KEY (pedido_fornecedor_id) REFERENCES pedido_fornecedor(id)
        ON DELETE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produto(id)
);

-- PEDIDO CLIENTE
CREATE TABLE pedido_cliente (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cliente_id INT,
    data_pedido TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status_pedido ENUM('pendente', 'pago', 'enviado', 'cancelado', 'concluido') DEFAULT 'pendente',
    valor_total DECIMAL(12,2) DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES cliente(id)
);

-- ITEM PEDIDO CLIENTE
CREATE TABLE item_pedido_cliente (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pedido_cliente_id INT,
    produto_id INT,
    quantidade DECIMAL(12,3),
    preco_unitario_no_momento DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (pedido_cliente_id) REFERENCES pedido_cliente(id)
        ON DELETE CASCADE,
    FOREIGN KEY (produto_id) REFERENCES produto(id)
);

-- ENDERECO
CREATE TABLE endereco (
    id INT AUTO_INCREMENT PRIMARY KEY,
    rua VARCHAR(100),
    cidade VARCHAR(50),
    estado VARCHAR(50),
    cep VARCHAR(10),
    cliente_id INT NULL,
    fornecedor_id INT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (cliente_id) REFERENCES cliente(id)
        ON DELETE CASCADE,
    FOREIGN KEY (fornecedor_id) REFERENCES fornecedor(id)
        ON DELETE CASCADE
);