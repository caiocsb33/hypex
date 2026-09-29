# HYPEX — Documentação do Sistema

Sistema SaaS de gestão de estoque, galpões, fornecedores, clientes e pedidos.
Várias empresas usam a mesma instalação, e cada uma enxerga **apenas os próprios dados**.

---

## Sumário

1. [Visão geral](#1-visão-geral)
2. [Tecnologias](#2-tecnologias)
3. [Instalação e execução](#3-instalação-e-execução)
4. [Estrutura de pastas](#4-estrutura-de-pastas)
5. [Arquitetura](#5-arquitetura)
6. [Multiempresa (SaaS)](#6-multiempresa-saas)
7. [Usuários, perfis e permissões](#7-usuários-perfis-e-permissões)
8. [Banco de dados](#8-banco-de-dados)
9. [Módulos e telas](#9-módulos-e-telas)
10. [Referência de rotas](#10-referência-de-rotas)
11. [Interface: layout, tema e componentes](#11-interface-layout-tema-e-componentes)
12. [Validações e formatação](#12-validações-e-formatação)
13. [Segurança](#13-segurança)
14. [Guia para desenvolvedores](#14-guia-para-desenvolvedores)
15. [Limitações conhecidas e próximos passos](#15-limitações-conhecidas-e-próximos-passos)

---

## 1. Visão geral

| Item | Descrição |
|---|---|
| Público | Empresas que armazenam mercadorias em um ou mais galpões |
| Modelo | SaaS multiempresa: cada empresa cria a própria conta em `/cadastro` |
| O que o sistema faz | Cadastro de galpões, produtos, fornecedores, clientes, funcionários e empilhadeiras; controle de saldo por galpão; pedidos de entrada (compras) e de saída (vendas); histórico de movimentações; dashboard financeiro; alertas de estoque mínimo |
| Filosofia técnica | Regras no servidor (Python/Flask), telas em HTML/CSS. O JavaScript é mínimo e opcional: sem ele tudo continua funcionando, só que recarregando a página |

### Fluxo típico de uso

1. A empresa se cadastra em **/cadastro** e já entra logada como **Administrador**.
2. Cadastra **galpões** e, dentro de cada galpão, **produtos**, **funcionários** e **empilhadeiras**.
3. Cadastra **fornecedores** e vincula os produtos que cada um fornece.
4. Registra **pedidos de entrada**: o estoque do galpão sobe e uma movimentação de entrada é gravada.
5. Cadastra **clientes** e registra **pedidos de saída**: o estoque baixa e uma movimentação de saída é gravada.
6. Acompanha tudo pelo **dashboard** e pelo **sininho** de alertas.
7. O administrador cria contas para a equipe em **Usuários**.

---

## 2. Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.11+ |
| Framework web | Flask 3 (Jinja2 para templates, Werkzeug para hash de senha) |
| Banco de dados | MySQL 8 ou MariaDB 10.5+ (driver `mysql-connector-python`) |
| Front-end | HTML + CSS próprios, Bootstrap 5.3 e Bootstrap Icons via CDN |
| JavaScript | Só quatro arquivos pequenos em `static/js/` (tema e menu, pré-visualização de imagem, preço no pedido, acessibilidade) |

> O `REGEXP_REPLACE` usado na comparação de documentos exige **MySQL 8+** ou **MariaDB 10.0.5+**.

---

## 3. Instalação e execução

### 3.1 Pré-requisitos

- Python 3.11 ou superior
- MySQL 8 ou MariaDB em execução

### 3.2 Passo a passo

```bash
cd "Software 4/Software2.0/Software"

# 1. Dependências
pip install -r requirements.txt

# 2. Conexão com o banco: edite config.py (host, user, password, database)

# 3. Cria o banco e as tabelas
mysql -u root -p < banco.sql

# 4. (Opcional) Empresa de demonstração
python empresa.py            # cria "Imbil": contato@imbil.com / 654321 (Administrador)
python testes/dados_exemplo.py   # galpão, produtos, fornecedor, cliente e pedidos de exemplo

# 5. Sobe o sistema
python app.py                # http://127.0.0.1:5000
```

### 3.3 Variáveis de ambiente

| Variável | Uso | Padrão |
|---|---|---|
| `FLASK_SECRET_KEY` | Chave que assina a sessão (login). **Defina em produção.** | Gerada uma vez e salva em `instance/secret_key` |

### 3.4 Atualizando um banco antigo

Não é preciso rodar script. Ao iniciar, o `app.py` executa `migrar_multiempresa()`, que:

1. cria a coluna `empresa_id` nas tabelas que ainda não têm;
2. atribui os registros existentes à **primeira empresa cadastrada**;
3. troca a unicidade global de SKU, código de barras, CNPJ e CPF por unicidade **por empresa**.

A migração pode rodar várias vezes: quando o banco já está atualizado, ela não faz nada.
Se alguma estrutura continuar faltando, todas as telas levam para **/banco-desatualizado**, que explica o que falta em vez de mostrar um erro 500.

---

## 4. Estrutura de pastas

```
Software/
├── app.py                  # Aplicação Flask: rotas, regras, validações, segurança
├── config.py               # Conexão com o banco (DB_CONFIG)
├── banco.sql               # Criação do banco completo
├── empresa.py              # Cria a empresa e o usuário de demonstração
├── requirements.txt
├── testes_rotas.py         # Testes funcionais automatizados
├── core/
│   ├── database.py         # Database.connect()
│   ├── empresa.py          # empresa_atual(): empresa da sessão
│   └── crud_base.py        # CRUD genérico já filtrado por empresa
├── models/                 # Acesso a dados por entidade
│   ├── cliente.py  empilhadeira.py  endereco.py  estoque.py
│   ├── fornecedor.py  funcionario.py  galpao.py  movimentacao.py
│   └── pedidocliente.py  produto.py
├── templates/              # Telas (Jinja2)
│   ├── base.html           # Layout: menu lateral, header, notificações
│   ├── _confirmar.html     # Janela de confirmação (só CSS)
│   ├── _notificacoes.html  # Notificações (flash messages)
│   ├── _imagem_upload.html # Campo de imagem reutilizável
│   └── ... uma tela por arquivo
├── static/
│   ├── style.css           # Estilos globais (menu, header, tabelas, dashboard)
│   ├── modo-escuro.css     # Todas as cores do tema escuro, num só lugar
│   ├── notificacoes.css    # Notificações e janela de confirmação
│   ├── style_*.css         # Estilos específicos de cada tela
│   ├── imagem/             # Imagens enviadas e imagens padrão
│   └── js/                 # tema.js, imagem-preview.js, preco-produto.js, acessibilidade.js
├── testes/                 # Scripts de teste (ver docs/TESTES.md)
└── docs/
    ├── DOCUMENTACAO.md     # Este arquivo
    └── TESTES.md           # Plano e relatório de testes
```

---

## 5. Arquitetura

```
Navegador ──HTTP──▶ Flask (app.py)
                     │
                     ├─ before_request (nesta ordem)
                     │    1. avisar_banco_desatualizado  → falta estrutura? vai para /banco-desatualizado
                     │    2. proteger_dados_da_empresa   → id de outra empresa? responde 404
                     │    3. verificar_perfil            → relê o usuário e confere a permissão
                     │
                     ├─ rota (@login_obrigatorio)
                     │    ├─ models/*  ou  SQL direto (sempre filtrando por empresa_id)
                     │    └─ render_template / redirect + flash
                     │
                     └─ context_processor dados_globais
                          → empresa, usuário, perfil, tema, menu, notificações do sininho
```

### Padrões usados em todo o código

| Padrão | Como funciona |
|---|---|
| **PRG** (Post/Redirect/Get) | Todo formulário faz POST, o servidor grava e redireciona. Recarregar a página não reenvia os dados. |
| **Notificações** | `flash(mensagem, "sucesso" \| "erro" \| "aviso")`, exibidas por `_notificacoes.html` em todas as telas. |
| **`voltar_para`** | Campo escondido com a página de origem. Depois da ação, o usuário volta para onde estava. Só aceita caminhos internos, o que evita redirecionar para fora do site. |
| **Carrinho de pedido** | Os itens do pedido em montagem ficam na sessão (`/pedido_entrada/item/...`, `/pedido_saida/item/...`), sem JavaScript. |
| **Confirmação sem JS** | `_confirmar.html` usa checkbox escondido + CSS para abrir a janela "Tem certeza?". |
| **Preferências** | Tema e menu minimizado ficam na sessão e chegam prontos no HTML. |

---

## 6. Multiempresa (SaaS)

### 6.1 Onde fica o dono de cada registro

| Tabela | Como pertence à empresa |
|---|---|
| `fornecedor`, `cliente`, `galpao`, `funcionario`, `empilhadeira`, `produto`, `movimentacao`, `pedido_fornecedor`, `pedido_cliente` | Coluna **`empresa_id`** (FK para `empresa`, `ON DELETE CASCADE`) |
| `usuario` | Coluna `empresa_id` |
| `estoque`, `fornecedor_produto`, `item_pedido_*`, `localizacao`, `lote`, `endereco` | Herdam do registro pai (produto, galpão, pedido, fornecedor ou cliente) |

### 6.2 As três camadas de proteção

1. **Guarda central por id** (`proteger_dados_da_empresa`, em `app.py`)
   - Confere todo id que chega pela URL, pela query string ou pelo formulário.
   - Nomes verificados: `galpao_id`, `galpao_destino_id`, `produto_id`, `fornecedor_id`, `cliente_id`, `funcionario_id`, `empilhadeira_id` e `usuario_id` (mapa `IDS_POR_PARAMETRO`).
   - Rotas que recebem só `id` ou `pedido_id` estão no mapa `IDS_POR_ENDPOINT`.
   - O `id` enviado pelo formulário de funcionário está no mapa `IDS_NO_FORMULARIO`.
   - Se o registro não é da empresa logada, a resposta é **404**, como se ele não existisse.
2. **Consultas filtradas.** Listagens, contagens, buscas, dashboard e notificações usam `WHERE ... empresa_id = %s`. Nos models isso vem de `core/empresa.py → empresa_atual()`, e o `CrudBase` aplica o filtro automaticamente.
3. **Gravação com dono.** Todo `INSERT` nas tabelas da seção 6.1 grava o `empresa_id` da sessão.

### 6.3 Unicidade por empresa

| Tabela | Chave única |
|---|---|
| `produto` | `(empresa_id, sku)` e `(empresa_id, codigo_barras)` |
| `fornecedor` | `(empresa_id, cnpj)` |
| `cliente` | `(empresa_id, cpf_cnpj)` |
| `funcionario` | `(empresa_id, cpf)` |
| `usuario` | `(email, empresa_id)`. O mesmo e-mail pode ter conta em duas empresas; o login entra na conta cuja senha confere. |

### 6.4 Regra para quem for criar algo novo

> Toda tabela nova com dados de cliente precisa de `empresa_id`, entrar em `TABELAS_DA_EMPRESA` e ter todas as consultas filtradas. Se a rota recebe um id novo, adicione o parâmetro em `IDS_POR_PARAMETRO` ou em `IDS_POR_ENDPOINT`. O teste `testar_isolamento_entre_empresas` precisa continuar passando.

---

## 7. Usuários, perfis e permissões

| Ação | Administrador | Gerente | Operador |
|---|:-:|:-:|:-:|
| Ver todas as telas da empresa | ✔ | ✔ | ✔ |
| Cadastrar e editar (produtos, pedidos, clientes...) | ✔ | ✔ | ✔ |
| Movimentar estoque, desativar produto, cancelar pedido | ✔ | ✔ | ✔ |
| **Excluir** registros (galpão, produto, fornecedor, cliente, funcionário, empilhadeira, pedidos) | ✔ | ✔ | ✖ |
| Alterar dados da empresa (nome, CNPJ, logo) | ✔ | ✔ | ✖ |
| **Gerenciar usuários** (criar, trocar perfil, desativar) | ✔ | ✖ | ✖ |
| Alterar o próprio perfil e a própria senha | ✔ | ✔ | ✔ |

Como funciona:

- **Onde ficam as regras:** as rotas restritas estão nos conjuntos `ENDPOINTS_GERENCIA` e `ENDPOINTS_ADMIN`, e o `before_request verificar_perfil` bloqueia com uma mensagem clara.
- **Botões escondidos:** os botões de excluir não aparecem para o Operador (variável de template `pode_gerenciar`).
- **Mudança vale na hora:** a cada requisição o usuário é relido do banco. Perfil trocado vale imediatamente, e uma conta desativada é desconectada na próxima tela que abrir.
- **Proteção contra si mesmo:** ninguém pode trocar o próprio perfil nem desativar a própria conta, para a empresa não ficar sem administrador.
- **Senha provisória:** os usuários criados em **/usuarios** recebem uma senha provisória (mínimo de 6 caracteres) e trocam em **Configurações → Alterar Senha**.

---

## 8. Banco de dados

Script completo: `banco.sql`. Principais tabelas e colunas:

| Tabela | Colunas principais | Observações |
|---|---|---|
| `empresa` | id, nome, cnpj (único), imagem | A "conta" do SaaS |
| `usuario` | id, empresa_id, nome, email, senha (hash), tipo (`admin`/`gerente`/`operador`), ativo | |
| `recuperacao_senha` | usuario_id, token, expira_em, usado | Fluxo "Esqueci a senha" |
| `galpao` | id, empresa_id, nome, stats, responsável, endereço, cep, area_total, prateleiras/níveis/caixas, capacidade_total, imagem | |
| `produto` | id, empresa_id, sku, nome, categoria, preco_custo, preco_venda, peso, volume, tipo, codigo_barras, imagem, ativo | Desativar é reversível; excluir só sem histórico |
| `estoque` | produto_id, galpao_id, quantidade, estoque_minimo | Único por (produto, galpão) |
| `fornecedor` | id, empresa_id, nome, nome_ctt, email, telefone, cnpj, ativo, imagem | |
| `fornecedor_produto` | fornecedor_id, produto_id, preco_custo, desconto, quantidade_minima, prazo_entrega_dias, ativo | Catálogo de cada fornecedor |
| `cliente` | id, empresa_id, nome, empresa, cpf_cnpj, email, telefone, cep, cidade, estado, ativo | |
| `funcionario` | id, empresa_id, galpao_id, nome, cpf, cargo, salário, datas, ativo | |
| `empilhadeira` | id, empresa_id, galpao_id, funcionario_id, marca, modelo, ano, combustível, capacidade | |
| `movimentacao` | id, empresa_id, produto_id, galpao_id, galpao_destino_id, funcionario_id, tipo (`entrada`/`saida`/`transferencia`/`ajuste_inventario`), quantidade, data, observação | Histórico imutável |
| `pedido_fornecedor` + `item_pedido_fornecedor` | fornecedor, galpão, nº do documento, datas, status, valor_total | Pedido de **entrada** |
| `pedido_cliente` + `item_pedido_cliente` | cliente, galpão, nº do documento, status (`pendente`/`pago`/`enviado`/`cancelado`/`concluido`), valor_total | Pedido de **saída** |

### Regras de negócio no banco e no código

- **Entrada:** salvar um pedido de entrada soma a quantidade no `estoque` do galpão e grava uma `movimentacao` do tipo `entrada`.
- **Saída:** salvar um pedido de saída confere o saldo, baixa o `estoque` e grava uma `movimentacao` do tipo `saida`.
- **Cancelar ou excluir** um pedido de saída devolve o estoque.
- **Excluir produto** só é permitido quando ele não tem histórico (movimentações ou itens de pedido); caso contrário, use **Desativar**.
- **Valores monetários** são guardados como `DECIMAL` e exibidos no formato brasileiro (`R$ 1.234,56`).

---

## 9. Módulos e telas

O menu lateral tem **Dashboard, Estoque, Fornecedores, Pedidos, Clientes** e, no rodapé, **Configuração**. O item do módulo atual fica destacado em todas as telas daquele módulo (mapa `MODULOS` em `app.py`).

### 9.1 Header (todas as telas)

| Elemento | Função |
|---|---|
| Campo **Pesquisar** | Busca geral em produtos, clientes, fornecedores e galpões (`/buscar?q=`) |
| Chave **lua/sol** | Troca o tema na hora, sem recarregar, e salva a escolha na sessão |
| **Alto-falante** | Liga ou desliga a leitura por voz (acessibilidade) |
| **Sininho** | Alertas de estoque baixo, sem estoque e pedidos pendentes, conforme **Configuração → Notificações**; cada item leva ao produto ou ao pedido |
| **Olá, Nome / Perfil** | Menu com Configuração, Usuários (só admin) e Sair (com confirmação) |

### 9.2 Telas

| Tela | Rota | O que faz |
|---|---|---|
| Landing | `/` | Página pública de apresentação |
| Cadastro de empresa | `/cadastro` | Cria a empresa e o administrador e já entra na conta |
| Login | `/login` | E-mail e senha |
| Esqueci a senha / Redefinir | `/esqueci-senha`, `/redefinir-senha/<token>` | Link com validade de 30 minutos |
| Dashboard | `/dashboard` | Ganhos, gastos, contagens, lucro com gráfico dos últimos 6 meses, mais vendidos, atividades recentes e alertas |
| Galpões | `/galpao` | Cards dos galpões com ocupação; clicar abre o **estoque** do galpão |
| Informações do galpão | `/info_galpao/<id>` | Edita dados, funcionários e empilhadeiras do galpão |
| Estoque | `/estoque`, `/estoque/<galpao_id>` | Saldo consolidado ou por galpão, com foto e situação (Ativo/Inativo) de cada produto; filtros e ordenação; cadastrar, ajustar, desativar/reativar e excluir produto |
| Produto | `/info_produto/<id>` | Edição, fornecedores, saldo por galpão e histórico |
| Produtos inativos | `/produtos/inativos` | Reativar ou excluir |
| Movimentações | `/movimentacoes`, `/movimentacao/nova` | Histórico com filtros (produto, galpão, tipo) e lançamento manual |
| Fornecedores | `/fornecedores`, `/info_fornecedor/<id>`, `/itens_fornecedores/<id>` | Cadastro e catálogo de itens do fornecedor, com busca, filtros e exportação para CSV (abre no Excel) |
| Clientes | `/clientes`, `/info_cliente/<id>` | Cadastro com total de pedidos e total gasto (sem cancelados) |
| Pedidos de entrada | `/pedidos`, `/cadastro_pedido_entrada`, `/pedidos_entrada/visualizar/<id>` | Compra de fornecedor |
| Pedidos de saída | `/pedidos_cliente/<cliente_id>`, `/cadastro_pedido/<cliente_id>`, `/pedido-cliente/<id>`, `/pedido_cliente/<id>/editar` | Venda para cliente; edição de status, documento e observação |
| Busca geral | `/buscar` | Resultados agrupados por tipo |
| Configuração | `/config` | Dados da empresa (admin e gerente), meu perfil, alterar senha, **notificações** (admin e gerente), equipe (admin), preferências |

### 9.3 Notificações

O sininho e o card "Alertas" do dashboard usam a **mesma regra** (`alertas_estoque()` e `montar_notificacoes()` no `app.py`). Ela é avaliada por galpão e ajustada em **Configuração → Notificações**, com preferências gravadas na tabela `empresa` e válidas para toda a equipe:

| Preferência | Padrão | Efeito |
|---|---|---|
| Estoque baixo | Ligado | Saldo > 0 e ≤ mínimo (mais a margem) |
| Sem estoque | Ligado | Saldo ≤ 0 |
| Incluir produtos inativos | Ligado | Também avisa sobre produtos desativados, com a marcação "inativo" |
| Pedidos pendentes | Ligado | Pedidos de saída com status pendente |
| Aviso antecipado (%) | 0 | Avisa quando o saldo estiver até X% acima do mínimo (0 a 200) |

> Antes os alertas consideravam só produtos com `ativo = TRUE`. Um produto desativado, ou com a situação em branco, sumia dos alertas mesmo aparecendo abaixo do mínimo na tela de estoque.
| Usuários | `/usuarios` | Equipe, perfis e ativação (só admin) |

---

## 10. Referência de rotas

Legenda de acesso: **L** = precisa estar logado · **G** = só admin e gerente · **A** = só admin · **P** = pública.

| Método | Rota | Função (endpoint) | Acesso |
|---|---|---|---|
| GET | `/` | landing | P |
| GET | `/home` | home | P (redireciona para o dashboard ou para a landing) |
| GET, POST | `/login` | login | P |
| POST | `/logout` | logout | L |
| GET, POST | `/cadastro` | cadastro_emp | P |
| GET, POST | `/esqueci-senha` | esqueci_senha | P |
| GET, POST | `/redefinir-senha/<token>` | redefinir_senha | P |
| GET | `/banco-desatualizado` | banco_desatualizado | P |
| POST | `/tema/alternar` | alternar_tema | P |
| POST | `/menu/alternar` | alternar_menu | P |
| GET | `/dashboard` | dashboard | L |
| GET | `/buscar` | buscar | L |
| GET | `/config` | config | L |
| POST | `/config/perfil` | salvar_perfil | L |
| POST | `/config/senha` | alterar_senha | L |
| POST | `/config/empresa` | salvar_empresa | G |
| POST | `/config/notificacoes` | salvar_notificacoes | G |
| GET | `/usuarios` | usuarios | A |
| POST | `/usuarios/salvar` | salvar_usuario | A |
| POST | `/usuarios/<usuario_id>/ativo` | alternar_usuario_ativo | A |
| POST | `/usuarios/<usuario_id>/perfil` | alterar_perfil_usuario | A |
| GET | `/galpao` | galpao | L |
| GET | `/galpao/novo` | novo_galpao | L |
| POST | `/galpao/salvar` | salvar_galpao | L |
| GET | `/info_galpao/<galpao_id>` | info_galpao | L |
| POST | `/galpao/atualizar/<galpao_id>` | atualizar_galpao | L |
| POST | `/galpao/deletar/<galpao_id>` | deletar_galpao | G |
| POST | `/funcionario/salvar` | salvar_funcionario | L |
| POST | `/funcionario/atualizar` | atualizar_funcionario | L |
| POST | `/funcionario/deletar/<funcionario_id>` | deletar_funcionario | G |
| POST | `/empilhadeira/salvar` | salvar_empilhadeira | L |
| POST | `/empilhadeira/atualizar/<empilhadeira_id>` | atualizar_empilhadeira | L |
| POST | `/empilhadeira/deletar/<empilhadeira_id>` | deletar_empilhadeira | G |
| GET | `/estoque` | estoque | L |
| GET | `/estoque/<galpao_id>` | estoque_galpao | L |
| POST | `/estoque/movimentar` | movimentar_estoque | L |
| GET | `/produtos` | produtos | L |
| GET | `/produtos/inativos` | produtos_inativos | L |
| POST | `/produto/salvar` | salvar_produto | L |
| GET | `/produto/editar/<id>` | editar_produto | L |
| POST | `/produto/atualizar/<id>` | atualizar_produto | L |
| POST | `/produto/ajustar_estoque/<id>` | ajustar_estoque_produto | L |
| POST | `/produto/desativar/<id>` | desativar_produto | L |
| POST | `/produto/reativar/<id>` | reativar_produto | L |
| POST | `/produto/excluir/<id>` | excluir_produto | G |
| GET | `/info_produto/<id>` | info_produtos | L |
| GET | `/movimentacoes` | movimentacoes | L |
| GET | `/movimentacao/nova` | nova_movimentacao | L |
| POST | `/movimentacao/salvar` | salvar_movimentacao | L |
| GET | `/fornecedores` | fornecedores | L |
| GET | `/fornecedor/novo` | novo_fornecedor | L |
| POST | `/fornecedor/salvar` | salvar_fornecedor | L |
| POST | `/fornecedor/atualizar/<fornecedor_id>` | atualizar_fornecedor | L |
| POST | `/fornecedor/deletar/<fornecedor_id>` | deletar_fornecedor | G |
| POST | `/fornecedores/vincular_produto` | vincular_fornecedor_produto | L |
| GET | `/info_fornecedor/<fornecedor_id>` | info_fornecedor | L |
| GET | `/itens_fornecedores/<fornecedor_id>` | itens_fornecedor | L |
| GET | `/itens_fornecedores/<fornecedor_id>/exportar` | exportar_itens_fornecedor (CSV) | L |
| POST | `/fornecedor/<fornecedor_id>/salvar_item` | salvar_item_fornecedor | L |
| GET | `/clientes` | cliente | L |
| GET | `/cliente/novo` | novo_cliente | L |
| POST | `/cliente/salvar` | salvar_cliente | L |
| GET | `/info_cliente/<cliente_id>` | info_cliente | L |
| POST | `/cliente/atualizar/<cliente_id>` | atualizar_cliente | L |
| POST | `/cliente/deletar/<cliente_id>` | deletar_cliente | G |
| GET | `/pedidos` | pedidos | L |
| GET | `/pedidos_entrada` | listar_pedidos_entrada | L |
| GET | `/pedidos_entrada/novo` | novo_pedido_entrada | L |
| GET | `/cadastro_pedido_entrada` | cadastro_pedido_entrada | L |
| POST | `/pedido_entrada/item/adicionar` | adicionar_item_entrada | L |
| POST | `/pedido_entrada/item/remover/<indice>` | remover_item_entrada | L |
| POST | `/pedido_entrada/limpar` | limpar_pedido_entrada | L |
| POST | `/salvar_pedido_entrada` | salvar_pedido_entrada | L |
| GET | `/pedidos_entrada/visualizar/<pedido_id>` | visualizar_pedido_entrada | L |
| GET | `/editar_pedido/<id>` | editar_pedido | L |
| POST | `/deletar_pedido/<id>` | deletar_pedido | G |
| GET | `/pedidos_saida` | listar_pedidos_saida | L |
| GET | `/cadastro_pedido_saida` | cadastro_pedido_saida | L |
| GET | `/cadastro_pedido/<cliente_id>` | cadastro_pedido | L |
| POST | `/pedido_saida/item/adicionar` | adicionar_item_saida | L |
| POST | `/pedido_saida/item/remover/<indice>` | remover_item_saida | L |
| POST | `/pedido_saida/limpar` | limpar_pedido_saida | L |
| POST | `/salvar_pedido_saida` | salvar_pedido_saida | L |
| GET | `/pedidos_saida/visualizar/<pedido_id>` | visualizar_pedido_saida | L |
| GET | `/pedidos_cliente/<cliente_id>` | pedidos_clientes | L |
| GET | `/pedido-cliente/<pedido_id>` | info_pedido_cliente | L |
| GET | `/pedido_cliente/<pedido_id>/editar` | editar_pedido_cliente | L |
| POST | `/pedido_cliente/<pedido_id>/atualizar` | atualizar_pedido_cliente | L |
| POST | `/pedido/salvar` | salvar_pedido | L |
| POST | `/pedido/processar/<id>` | processar_pedido | L |
| POST | `/pedido/cancelar/<id>` | cancelar_pedido | L |
| POST | `/deletar_pedido_saida/<id>` | deletar_pedido_saida | G |
| GET | `/api/todos_produtos` | api_todos_produtos | L |
| GET | `/api/produtos_do_galpao/<galpao_id>` | api_produtos_do_galpao | L |
| GET | `/api/produtos_do_fornecedor/<fornecedor_id>` | api_produtos_do_fornecedor | L |

Em todas as rotas com id, o id é conferido contra a empresa logada (seção 6.2).

---

## 11. Interface: layout, tema e componentes

### 11.1 Layout (`templates/base.html`)

- **Menu lateral:**
  - No topo, a foto e o nome da empresa.
  - Os três pontinhos minimizam e expandem o menu, com animação. O `tema.js` troca na hora e salva na sessão; sem JS, a página recarrega.
  - No celular, o menu abre pelo botão ☰ (checkbox + CSS).
- **Header:** descrito na seção 9.1.
- **Conteúdo:** fica no bloco `{% block content %}`.

### 11.2 Tema escuro

- Todas as cores ficam em **`static/modo-escuro.css`**, com variáveis no topo (`--e-fundo`, `--e-card`, `--e-texto`...). Para ajustar o tema escuro, mexa nelas.
- O `static/js/tema.js` só liga e desliga a classe `modo-escuro` no `<body>`, com uma transição suave, e salva a escolha pela rota `/tema/alternar`.
- O `modo-escuro.css` é carregado depois do CSS de cada tela, para poder sobrescrevê-lo.

### 11.3 Componentes reutilizáveis

| Componente | Uso |
|---|---|
| `_confirmar.html` | `{% with id=..., form_id=..., titulo=..., texto=..., icone=..., classe=..., confirmar=..., perigo=True %}{% include '_confirmar.html' %}{% endwith %}` |
| `_notificacoes.html` | Incluído no `base.html`; mostra os `flash()` com ícone por tipo |
| `_imagem_upload.html` | Campo de imagem com pré-visualização (`campo_id`, `imagem`, `padrao`, `titulo`) |
| `.acoes-linha` | Envolve os botões de ação das tabelas para ficarem lado a lado |
| `.barra-pesquisa` | Padrão de pesquisa: campo com lupa + botões **Filtros** e **Limpar** |
| `_filtros.html` | Botão **Filtros** com menu (sem JS, via `<details>`) de **ordenação** e **situação**. Fica dentro do `<form method="GET">` da busca: `{% with limpar_url=url_for('...') %}{% include '_filtros.html' %}{% endwith %}` |
| `.produto-celula` + `.miniatura-produto` | Foto do produto (44 px, recortada) + nome e SKU nas tabelas |
| `.selo-situacao.ativo` / `.inativo` | Selo de situação nas tabelas |

### 11.5 Filtros e ordenação das listagens

A rota chama `ordenar_e_filtrar(lista, "<tela>")`, que lê `?ordem=` e `?situacao=` da URL. Valores desconhecidos são ignorados. As opções ficam nos dicionários `ORDENS` e `SITUACOES` do `app.py`:

| Tela | Ordenar por | Mostrar |
|---|---|---|
| Estoque (`produtos`) | Mais vendidos, A–Z, Z–A, mais estoque, menos estoque, mais caro, mais barato, recentes | Ativos, inativos, estoque baixo, sem estoque |
| Clientes | A–Z, Z–A, mais pedidos, maior valor gasto, recentes | Ativos, inativos, com pedidos |
| Fornecedores | A–Z, Z–A, mais produtos, menos produtos | Ativos, inativos |
| Galpões | A–Z, Z–A, mais ocupado, menos ocupado, mais itens, maior área | — |
| Pedidos (entrada e do cliente) | Mais recentes, mais antigos, maior valor, menor valor | Pendentes, concluídos, cancelados |
| Itens do fornecedor | A–Z, Z–A, maior custo, menor custo, menor prazo | Ativos, inativos |

"Mais vendidos" usa a soma das quantidades dos pedidos de saída não cancelados (`vendas_por_produto()`).

### 11.6 Responsividade

| Largura | Comportamento |
|---|---|
| > 1100 px | Layout completo |
| ≤ 1100 px | O header esconde o texto "Olá, Nome" (fica só a foto); a busca encolhe |
| ≤ 992 px | Cabeçalhos das telas e grupos de botões quebram linha |
| ≤ 768 px | O menu lateral vira ☰; tabelas rolam dentro do card; formulários em uma coluna; barra de pesquisa empilhada |
| ≤ 480 px | Header compacto (o botão de voz sai do header) |

As regras gerais ficam no fim do `static/style.css` (seção "RESPONSIVO — REGRAS GERAIS").

### 11.4 Filtros de template (Jinja)

| Filtro | Exemplo de saída |
|---|---|
| `moeda` | `1234.5 → 1.234,50` |
| `quantidade` | `10.000 → 10` (inteiro quando não há fração) |
| `telefone` | `11999998888 → (11) 99999-8888` |
| `documento` | CPF `000.000.000-00` / CNPJ `00.000.000/0000-00` |
| `cep` | `13000000 → 13000-000` |
| `imagem_ou('padrao.png')` | Nome da imagem ou a imagem padrão |

---

## 12. Validações e formatação

| Campo | Regra |
|---|---|
| CPF / CNPJ | Aceita com ou sem pontuação, confere os dígitos verificadores, recusa sequências repetidas e grava só os números. A duplicidade é verificada **dentro da empresa**. O cadastro da empresa aceita **CPF ou CNPJ** (MEI e autônomos). |
| CPF do funcionário | Opcional; quando informado, precisa ser um CPF válido de 11 números e não pode se repetir na empresa |
| Telefone | 10 ou 11 dígitos; grava só os números |
| CEP | 8 dígitos; grava só os números |
| E-mail | Formato válido |
| Senha | Mínimo de 6 caracteres (cadastro, alteração, redefinição e senha provisória) |
| Números e preços | `to_float` / `to_int` aceitam `12,50`, `1.234,56`, `R$ 9,90` e `12.5`. Entrada inválida vira 0, nunca erro 500. |
| Imagens | PNG, JPG, WEBP ou GIF, até 5 MB, com o conteúdo conferido no servidor (`salvar_imagem`) |
| Estoque | A saída não pode passar do saldo do galpão |
| Quantidades | Sempre em unidades inteiras (entrada, saída, transferência, pedidos); o ajuste de inventário aceita 0 para zerar o saldo |
| Preço no pedido de entrada | Não pode ser negativo |

---

## 13. Segurança

| Tema | Como é tratado |
|---|---|
| Isolamento entre empresas | Seção 6: guarda por id, consultas filtradas, 404 para registros de outra empresa |
| Senhas | Hash do Werkzeug (`generate_password_hash`), nunca gravadas nem registradas em log em texto puro |
| Sessão | Assinada com `FLASK_SECRET_KEY` (ou `instance/secret_key`, fora do Git) |
| Permissões | Perfis por rota (seção 7) |
| Conta desativada | Desconectada na próxima tela que abrir |
| Redirecionamento | `voltar_para` só aceita caminhos internos |
| Ações destrutivas | Só por POST e sempre com confirmação |
| SQL | Consultas parametrizadas (`%s`); nomes de tabela e coluna só vêm de listas fixas do código |
| Uploads | Tipo e tamanho validados; o nome do arquivo é gerado pelo sistema |
| CSRF | Todo POST precisa vir do próprio sistema (cabeçalho `Origin`/`Referer`); o cookie de sessão é `SameSite=Lax` e `HttpOnly` |
| Força bruta no login | 5 tentativas erradas por e-mail e IP bloqueiam por 15 minutos (resposta 429) |
| Cabeçalhos | `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin` |
| Concorrência no estoque | O saldo é lido com `SELECT ... FOR UPDATE` antes de uma saída ou transferência; duas saídas simultâneas não deixam o estoque negativo |

> **Atrás de proxy (nginx etc.):** a checagem de CSRF compara a origem com o host da requisição. Configure o proxy para repassar o `Host` original (`proxy_set_header Host $host;`) ou use o `ProxyFix` do Werkzeug.

---

## 14. Guia para desenvolvedores

### Criar uma tela nova

1. Crie a rota em `app.py` com `@login_obrigatorio`.
2. Filtre todas as consultas por `session["empresa_id"]` (ou use `empresa_atual()` nos models).
3. Crie o template com `{% extends "base.html" %}` e o CSS em `static/`.
4. Para o menu destacar o módulo certo, adicione o endpoint em `MODULOS`.
5. Se a rota excluir algo, adicione o endpoint em `ENDPOINTS_GERENCIA` e envolva o botão em `{% if pode_gerenciar %}`.
6. Se a rota receber um id novo, registre-o na guarda (seção 6.4).
7. Rode `bash testes/rodar_todos.sh`. A varredura de telas já inclui a rota nova automaticamente.

### Convenções

- Mensagens ao usuário em português, por `flash()`.
- Nada de `alert()` ou `confirm()` do navegador: use `_confirmar.html`.
- Dados sempre gravados "limpos" (documentos, telefone e CEP só com números) e formatados na exibição, pelos filtros.

---

## 15. Limitações conhecidas e próximos passos

| Item | Situação | Sugestão |
|---|---|---|
| E-mail de recuperação de senha | O link é **impresso no log do servidor** (não há serviço de e-mail) | Integrar SMTP ou um serviço transacional e remover o `print` |
| Modais de "Adicionar" | Usam o JavaScript do Bootstrap (CDN) | Converter para o padrão de páginas ou modais só com CSS |
| Assinatura e cobrança | Não existe controle de plano ou pagamento por empresa | Tabela de planos e limites por empresa |
| Auditoria | Não há registro de "quem fez o quê" | Tabela de log com usuário, ação e data |
| Produção | O `app.py` roda o servidor de desenvolvimento do Flask | Usar gunicorn ou waitress atrás de um proxy HTTPS e definir `FLASK_SECRET_KEY` |
