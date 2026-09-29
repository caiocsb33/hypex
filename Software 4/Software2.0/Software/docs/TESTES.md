# HYPEX — Documentação de Testes

Plano, casos e relatório de todos os testes feitos no sistema: automatizados, no navegador e de segurança.

---

## Sumário

1. [Resumo da última execução](#1-resumo-da-última-execução)
2. [Ambiente de teste](#2-ambiente-de-teste)
3. [Como rodar os testes](#3-como-rodar-os-testes)
4. [Estratégia](#4-estratégia)
5. [Testes automatizados](#5-testes-automatizados)
6. [Casos de teste funcionais por módulo](#6-casos-de-teste-funcionais-por-módulo)
7. [Testes de segurança e multiempresa](#7-testes-de-segurança-e-multiempresa)
8. [Testes de interface (navegador)](#8-testes-de-interface-navegador)
9. [Testes de migração do banco](#9-testes-de-migração-do-banco)
10. [Registro de defeitos encontrados e corrigidos](#10-registro-de-defeitos-encontrados-e-corrigidos)
11. [Não coberto / riscos residuais](#11-não-coberto--riscos-residuais)

---

## 1. Resumo da última execução

| Suíte | Itens | Resultado |
|---|---|---|
| `testes_rotas.py` (funcionais) | 10 grupos, 55+ verificações | ✅ Todos passaram |
| `testes/varredura_telas.py` — erro 500 | 46 telas | ✅ 0 falhas |
| `testes/varredura_telas.py` — variáveis de template | 46 telas | ✅ 0 faltando |
| Responsividade (390 / 768 / 1024 px) | 24 telas × 3 larguras | ✅ Nenhuma rolagem lateral |
| `testes/robustez_formularios.py` | 90 envios (45 rotas POST × vazio/lixo) | ✅ 0 erros 500 |
| Isolamento entre empresas (automatizado + manual) | 14 verificações | ✅ Todas bloqueadas (404) |
| Perfis de acesso | 11 verificações | ✅ Todas conforme a regra |
| Migração de banco antigo | 3 cenários | ✅ OK, idempotente |
| Log do servidor durante os testes | — | ✅ 0 tracebacks |

**Defeitos encontrados no total: 83** (seção 10), **todos corrigidos e verificados novamente**.

---

## 2. Ambiente de teste

| Item | Versão |
|---|---|
| Sistema operacional | Linux (Ubuntu 24.04) |
| Python | 3.11 |
| Flask / Werkzeug / Jinja2 | 3.1 / 3.1 / 3.1 |
| mysql-connector-python | 8+ |
| Banco | MariaDB 10.11 (compatível com MySQL 8) |
| Navegador (testes de interface) | Chromium via Playwright |
| Resoluções testadas | 1300×750, 1400×850, 1500×1000 (desktop) e 390 px (celular) |
| Temas testados | Claro e escuro |

### Massa de dados

| Script | Cria |
|---|---|
| `empresa.py` | Empresa **Imbil** (CNPJ válido) + administrador `contato@imbil.com` / `654321` |
| `testes/dados_exemplo.py` | 1 galpão, 1 fornecedor, 1 cliente, 1 funcionário, 3 produtos (50 un. cada, mínimo 10), 1 pedido de entrada (R$ 125,00) e 1 de saída (R$ 50,00) |
| `EMPRESA=2 testes/dados_exemplo.py` | O mesmo conjunto em uma **segunda empresa**, com os mesmos SKUs e CNPJs, usado para testar o isolamento |

---

## 3. Como rodar os testes

```bash
cd "Software 4/Software2.0/Software"

# Tudo de uma vez (APAGA e recria o banco sistema_estoque)
MYSQL_PWD=suasenha bash testes/rodar_todos.sh

# Ou separadamente, com o banco já criado:
python testes_rotas.py                  # funcionais
python testes/varredura_telas.py        # todas as telas: erro 500 e variáveis faltando
python testes/robustez_formularios.py   # formulários vazios e inválidos (dispara exclusões!)
```

Os testes usam o `test_client` do Flask e não precisam do servidor rodando.
O `testes_rotas.py` pode ser rodado várias vezes seguidas: ele apaga o que cria.

---

## 4. Estratégia

| Nível | O que cobre | Como |
|---|---|---|
| **Fumaça** | Toda tela abre sem erro | Varredura automática de todas as rotas GET |
| **Contrato de template** | Rota envia todas as variáveis que a tela usa | Renderização com `StrictUndefined` |
| **Funcional** | Regras de negócio (estoque, pedidos, documentos, pesquisa) | `testes_rotas.py` + testes de fluxo no navegador |
| **Robustez** | Entradas vazias ou inválidas não derrubam o sistema | Envio de lixo em todas as rotas POST |
| **Segurança** | Isolamento entre empresas, perfis, sessão, log | Testes com duas empresas e três perfis |
| **Interface** | Layout, tema escuro, menu, header, modais, responsividade | Playwright com capturas de tela revisadas |
| **Migração** | Banco antigo continua funcionando | Carregar schema antigo + dados, subir o app, conferir |
| **Regressão** | Nada que foi corrigido volta a quebrar | Toda a bateria reexecutada depois de cada correção |

Critério de aprovação: **nenhum erro 500, nenhum traceback no log, e todas as asserções passando**.

---

## 5. Testes automatizados

### 5.1 `testes_rotas.py`

| ID | Grupo | O que verifica | Resultado |
|---|---|---|---|
| AUT-01 | Rotas | Todas as rotas GET (45) respondem sem erro 500 | ✅ |
| AUT-02 | Rotas | Nenhuma variável de template faltando (`StrictUndefined`) | ✅ |
| AUT-03 | Ações de produto | Desativar e reativar um produto a partir de **Itens por Fornecedor** volta para a mesma tela e altera o `ativo` no banco | ✅ |
| AUT-04 | Pesquisa | `?busca=` filtra Clientes, Fornecedores e Galpões (termo presente aparece, ausente some) | ✅ |
| AUT-05 | Pedidos do cliente | **Editar** abre o pedido certo e grava status, documento e observação | ✅ |
| AUT-06 | Documentos | CPF/CNPJ com pontuação aceitos; dígito errado, sequência repetida e tamanho errado recusados; o mesmo documento sem pontuação é detectado como duplicado; telefone, CEP e documento gravados só com números; edição de cliente e cadastro de fornecedor seguem a mesma regra | ✅ |
| AUT-07 | Números | `to_float`: `"12,50"`→12.5, `"1.234,56"`→1234.56, `"R$ 9,90"`→9.9, `"12.5"`→12.5, `""`→0, `"abc"`→0; `to_int("10.0")`→10 | ✅ |
| AUT-08 | Multiempresa | Cria uma 2ª empresa por `/cadastro`; ela recebe **404** em `/info_cliente` e `/pedidos_cliente` da 1ª; não vê o cliente na lista nem na busca; tentar excluir dá 404 e o cliente continua no banco; o mesmo CPF/CNPJ pode ser cadastrado nas duas empresas. Remove a 2ª empresa no final | ✅ |
| AUT-14 | Filtros | `/estoque?ordem=az` sai em ordem alfabética; `za` é o inverso exato; parâmetros inválidos não alteram a lista; Clientes, Fornecedores, Galpões e Pedidos aceitam todas as ordens e situações; a tabela de estoque tem o menu, a foto e o selo de situação | ✅ |
| AUT-15 | Cadastros | A empresa se cadastra com **CPF** formatado; funcionário com CPF inválido é recusado; salário "2.500,50" é gravado como 2500.50 | ✅ |
| AUT-16 | Notificações | Produto **desativado** com saldo 3 e mínimo 5 aparece no sininho e no dashboard; ao desligar "Incluir produtos inativos" ele sai. A migração cria as 5 colunas de preferência num banco antigo | ✅ |
| AUT-17 | Segurança e estoque | POST com `Origin` de outro site → 403 sem alterar dados; cabeçalhos de segurança presentes; 6ª tentativa de login errada → 429; quantidade 2,5 recusada; ajuste de inventário para 0 aceito; preço negativo recusado; galpão com histórico não é excluído e a mensagem não mostra erro técnico | ✅ |
| AUT-09 | Perfis | Admin cria um Operador por `/usuarios/salvar`; o Operador tenta excluir um cliente e é bloqueado (o cliente continua no banco); o Operador tenta abrir `/usuarios` e é bloqueado. Remove o usuário no final | ✅ |

### 5.2 `testes/varredura_telas.py`

| ID | O que verifica | Resultado |
|---|---|---|
| AUT-10 | As 45 telas logadas respondem sem erro 500 | ✅ 0 falhas |
| AUT-11 | As 45 telas renderizam com `StrictUndefined` (nenhum campo sai em branco por esquecimento da rota) | ✅ 0 faltando |

### 5.3 `testes/robustez_formularios.py`

| ID | O que verifica | Resultado |
|---|---|---|
| AUT-12 | As 45 rotas POST recebem formulário **vazio** e não quebram | ✅ |
| AUT-13 | As 45 rotas POST recebem **lixo** (`"abc"` em todos os campos: ids, datas, preços, quantidades) e não quebram | ✅ |

Na primeira execução desta suíte apareceram 7 erros 500 (defeitos D-46 e D-47), que foram corrigidos.

---

## 6. Casos de teste funcionais por módulo

Legenda: **A** = automatizado · **N** = navegador (Playwright) · **M** = requisição manual (script).

### 6.1 Cadastro, login e sessão

| ID | Caso | Passos | Esperado | Tipo | Resultado |
|---|---|---|---|---|---|
| FUN-01 | Login válido | E-mail e senha corretos | Vai para o dashboard com "Login realizado!" | N | ✅ |
| FUN-02 | Login inválido | Senha errada | "Email ou senha inválidos!" | M | ✅ |
| FUN-03 | Logout | Menu do usuário → Sair → confirmar | Volta para `/login` | N | ✅ |
| FUN-04 | Logout só por POST | GET em `/logout` | Não desloga (405) | M | ✅ |
| FUN-05 | Cadastro de empresa | CNPJ válido, e-mail, senha de 6+ | Cria a empresa e o admin e **já entra logado** no dashboard | A (AUT-08) | ✅ |
| FUN-06 | Cadastro com senha curta | Senha "123" | "A senha precisa ter pelo menos 6 caracteres." | M | ✅ |
| FUN-07 | Cadastro com CNPJ inválido | Dígito verificador errado | Recusado com mensagem | M | ✅ |
| FUN-08 | Mesmo e-mail em duas empresas | Duas contas com o mesmo e-mail e senhas diferentes | Cada senha entra na empresa certa | M | ✅ |
| FUN-09 | Sessão sobrevive ao reinício | Reiniciar o servidor com o usuário logado | Continua logado | M | ✅ |

### 6.2 Dashboard

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-10 | Cartões | Ganhos, gastos, produtos, fornecedores, clientes e galpões iguais ao banco | N | ✅ |
| FUN-11 | Ganhos ignoram cancelados | Pedido cancelado não soma | M | ✅ |
| FUN-12 | Gráfico de lucro | 6 colunas (mês atual e os 5 anteriores); lucro positivo verde acima da linha, prejuízo vermelho abaixo; o tooltip mostra ganhos, gastos e lucro | N | ✅ |
| FUN-13 | Mais vendidos / atividades / alertas | Listas preenchidas com os dados reais | N | ✅ |
| FUN-14 | Dashboard só da empresa | A 2ª empresa vê apenas os próprios números | M | ✅ |

### 6.3 Galpões, funcionários e empilhadeiras

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-15 | Clicar no card do galpão | Abre o **estoque** do galpão (`/estoque/<id>`) | N | ✅ |
| FUN-16 | Editar galpão | Salva todos os campos, inclusive o nome (antes havia dois campos "nome") | N | ✅ |
| FUN-17 | Galpão com CEP antigo "12345-000" | O formulário salva (antes o navegador bloqueava) | N | ✅ |
| FUN-18 | Imagem do galpão | Upload com pré-visualização; recusa arquivo inválido | N | ✅ |
| FUN-19 | Cadastrar funcionário e empilhadeira | Aparecem nas tabelas do galpão | N | ✅ |
| FUN-20 | Atribuir empilhadeira a funcionário | Grava o `funcionario_id` e mostra o nome | N | ✅ |
| FUN-21 | Excluir funcionário ou empilhadeira | Confirmação `_confirmar`; volta para o galpão | N | ✅ |
| FUN-22 | Formulário de funcionário sem galpão | Volta para a lista de galpões (antes dava erro 500) | A (AUT-12) | ✅ |

### 6.4 Estoque e produtos

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-23 | Estoque consolidado | Soma dos galpões, mínimo, preços e status | N | ✅ |
| FUN-24 | Cadastrar produto no galpão | Cria o produto e o saldo; um SKU existente na empresa reaproveita o produto | N | ✅ |
| FUN-25 | Preço com vírgula "12,50" | Grava 12,50 (antes gravava 0) | A (AUT-07) | ✅ |
| FUN-26 | Editar produto | Salva todos os campos e a imagem | N | ✅ |
| FUN-27 | Ajustar saldo | Atualiza o estoque e grava uma movimentação `ajuste_inventario` | N | ✅ |
| FUN-28 | Desativar / reativar | Sai da lista e aparece em Produtos Inativos, e vice-versa | A (AUT-03) | ✅ |
| FUN-29 | Excluir produto ainda ativo | Recusado: "Desative o produto antes de excluir." | M | ✅ |
| FUN-30 | Quantidades inteiras | Exibe "50" e não "50.000" | N | ✅ |
| FUN-31 | Sininho | O contador é igual ao número de produtos com saldo ≤ mínimo; os itens levam ao produto | N | ✅ |

### 6.5 Movimentações

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-32 | Listar | Tabela com data, tipo, produto, origem, destino, responsável | N | ✅ |
| FUN-33 | Nova movimentação (entrada de 7 un.) | Salva, aparece na lista, o saldo sobe | N | ✅ |
| FUN-34 | Filtros produto/galpão/tipo | Lista filtrada pelo servidor | N | ✅ |
| FUN-35 | Transferência sem destino | Recusada com mensagem | M | ✅ |

### 6.6 Fornecedores

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-36 | Cadastrar com CNPJ inválido | "CNPJ inválido" | A (AUT-06) | ✅ |
| FUN-37 | Itens por fornecedor | Lista o catálogo; desativar item pede confirmação e volta para a tela | A (AUT-03) + N | ✅ |
| FUN-38 | Pesquisa | Filtra por nome, contato, e-mail, CNPJ e telefone | A (AUT-04) | ✅ |

### 6.7 Clientes

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-39 | Cadastrar cliente com CPF pontuado | Aceito e gravado só com números | A (AUT-06) | ✅ |
| FUN-40 | CPF duplicado sem pontuação | "Já existe um cliente com este CPF/CNPJ." | A (AUT-06) | ✅ |
| FUN-41 | Editar CPF/CNPJ na tela do cliente | Campo editável e validado | A (AUT-06) | ✅ |
| FUN-42 | Total gasto | Não soma pedidos cancelados | M | ✅ |

### 6.8 Pedidos

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-43 | Pedido de saída: produtos | Travado até escolher o galpão; depois lista só os produtos com saldo | N | ✅ |
| FUN-44 | Pedido de saída: preço | Preenchido na hora ao escolher o produto; o máximo é o saldo | N | ✅ |
| FUN-45 | Pedido de saída: adicionar 3 un. | O total do pedido é recalculado | N | ✅ |
| FUN-46 | Pedido de entrada: produtos do fornecedor | Encontrados ao escolher o fornecedor (antes não achava) | N | ✅ |
| FUN-47 | Pedido de entrada: custo sugerido | Preenchido com o custo do fornecedor | N | ✅ |
| FUN-48 | Fechar pedido de saída | O estoque baixa e é gravada uma movimentação `saida` | N | ✅ |
| FUN-49 | Cancelar pedido de saída | "Pedido cancelado e estoque devolvido." | M | ✅ |
| FUN-50 | Excluir pedido de saída | Devolve o estoque (se não estava cancelado) | M | ✅ |
| FUN-51 | Olhinho (visualizar) | Abre o detalhe sem erro | N | ✅ |
| FUN-52 | Editar pedido do cliente | Abre o pedido certo (antes apontava para rota de fornecedor) | A (AUT-05) | ✅ |

### 6.9 Busca geral

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-53 | Buscar "a" | Resultados agrupados em Produtos, Clientes, Fornecedores e Galpões, com links | N | ✅ |
| FUN-54 | Termo sem resultado | "Nada encontrado para …" | N | ✅ |
| FUN-55 | Busca de outra empresa | Nenhum resultado da empresa vizinha | A (AUT-08) | ✅ |

### 6.10 Configuração e usuários

| ID | Caso | Esperado | Tipo | Resultado |
|---|---|---|---|---|
| FUN-56 | Salvar perfil | Nome, e-mail e telefone gravados | N | ✅ |
| FUN-57 | Alterar senha | Exige a senha atual e a confirmação igual, mínimo de 6 | M | ✅ |
| FUN-58 | Dados da empresa | Nome, CNPJ e logo salvos; o logo aparece no menu e no header; a foto atual é carregada (antes sempre mostrava a padrão) | N | ✅ |
| FUN-59 | Dados da empresa para Operador | Campos desabilitados com aviso | N | ✅ |
| FUN-60 | Preferências | Modo escuro e menu minimizado pelos interruptores | N | ✅ |
| FUN-61 | Criar usuário | Aparece na equipe; e-mail repetido na mesma empresa é recusado | M | ✅ |
| FUN-62 | Trocar perfil | "Perfil alterado para Gerente." e vale na hora | M | ✅ |
| FUN-63 | Desativar usuário | A pessoa é desconectada na próxima tela: "Sua conta foi desativada." | M | ✅ |
| FUN-64 | Alterar a si mesmo | "Você não pode alterar o próprio perfil ou desativar a própria conta." | M | ✅ |

---

## 7. Testes de segurança e multiempresa

Cenário: **Empresa A** (Imbil) e **Empresa B** (Outra SA), cada uma com os mesmos SKUs e CNPJs de exemplo, testadas com a sessão da B.

| ID | Tentativa da Empresa B | Esperado | Resultado |
|---|---|---|---|
| SEG-01 | Listar clientes | Não aparece nenhum cliente da A | ✅ |
| SEG-02 | Listar fornecedores | Só os próprios | ✅ |
| SEG-03 | `GET /info_cliente/1` (da A) | 404 | ✅ |
| SEG-04 | `GET /info_produto/1` | 404 | ✅ |
| SEG-05 | `GET /estoque/1` | 404 | ✅ |
| SEG-06 | `GET /info_fornecedor/1` | 404 | ✅ |
| SEG-07 | `GET /pedidos_cliente/1` | 404 | ✅ |
| SEG-08 | `GET /pedido-cliente/1` | 404 | ✅ |
| SEG-09 | `GET /pedidos_entrada/visualizar/1` | 404 | ✅ |
| SEG-10 | `GET /itens_fornecedores/1` | 404 | ✅ |
| SEG-11 | `POST /cliente/deletar/1` | 404 e o cliente da A continua existindo | ✅ |
| SEG-12 | `POST /produto/desativar/1` | 404 | ✅ |
| SEG-13 | `POST /movimentacao/salvar` com `produto_id` da A no formulário | 404 (id no corpo também é conferido) | ✅ |
| SEG-14 | Busca geral pelo nome do cliente da A | Nenhum resultado | ✅ |
| SEG-15 | Dashboard | Números só da B | ✅ |
| SEG-16 | Cadastrar SKU/CNPJ igual ao da A | Permitido (unicidade por empresa) | ✅ |

| ID | Perfis e sessão | Esperado | Resultado |
|---|---|---|---|
| SEG-17 | Operador em `/usuarios` | Bloqueado: "Somente o administrador da conta pode gerenciar usuários." | ✅ |
| SEG-18 | Operador exclui cliente | Bloqueado, volta para a página de origem com aviso | ✅ |
| SEG-19 | Operador desativa produto | Permitido | ✅ |
| SEG-20 | Operador não vê botões de excluir | Botões ocultos | ✅ |
| SEG-21 | Gerente exclui id inexistente | 404 | ✅ |
| SEG-22 | Conta desativada com sessão aberta | Desconectada na próxima requisição | ✅ |
| SEG-23 | Senha no log | O login não imprime mais a senha nem o hash | ✅ |
| SEG-24 | `voltar_para=//site-externo.com` | Ignorado; redireciona para uma página interna | ✅ |
| SEG-25 | Upload de arquivo que não é imagem | Recusado | ✅ |

---

## 8. Testes de interface (navegador)

Feitos com Playwright/Chromium, com captura de tela revisada. Não houve **nenhum erro de JavaScript** (`pageerror`) em nenhum dos testes.

| ID | Tela / componente | Verificação | Resultado |
|---|---|---|---|
| UI-01 | Header | Pesquisa à esquerda; lua/sol, voz, sininho, avatar, "Olá, Nome" e perfil à direita | ✅ |
| UI-02 | Tema | Trocar sem recarregar (a URL não muda), com transição; a escolha persiste depois do reload | ✅ |
| UI-03 | Menu lateral | Minimizar e expandir com animação; persiste depois do reload | ✅ |
| UI-04 | Menu lateral | O item do módulo fica destacado em todas as telas daquele módulo; hover alinhado | ✅ |
| UI-05 | Menu lateral | Rodapé com um único item "Configuração" | ✅ |
| UI-06 | Dropdowns | Sininho e usuário abrem com animação, sem JS (`<details>`) | ✅ |
| UI-07 | Confirmações | A janela abre só para o item clicado (antes abria todas as da página) | ✅ |
| UI-08 | Notificações | Sucesso, erro e aviso com ícone; sem `alert()` do navegador | ✅ |
| UI-09 | Tabelas | Botões de Ações lado a lado (antes empilhados) | ✅ |
| UI-10 | Barras de pesquisa | Mesmo padrão em todas as telas (lupa + Filtros + Limpar) | ✅ |
| UI-11 | Configuração | Empresa no topo; Perfil e Senha lado a lado; Equipe (admin); Preferências | ✅ |
| UI-12 | Usuários | Tabela da equipe, formulário e explicação dos perfis; claro e escuro | ✅ |
| UI-13 | Tema escuro | Todas as telas legíveis (cards, tabelas, campos, header, busca, gráfico) | ✅ |
| UI-14 | Celular (390 px) | Menu vira ☰; header compacto; a página não rola para o lado em 10 telas (tabelas largas rolam dentro do card) | ✅ (após D-59) |
| UI-15 | Movimentações | Botão principal no topo; filtros separados da tabela | ✅ |
| UI-16 | Links | Nenhum `<button>` dentro de `<a>` | ✅ |
| UI-17 | Menu Filtros | Abre embaixo do botão, com ordenação e chips de situação; "Aplicar" mantém a busca; contador de filtros ativos no botão | ✅ |
| UI-18 | Tabelas | Foto do produto recortada (sem esticar) e selo Ativo/Inativo | ✅ |
| UI-19 | Campo de imagem | Mesmo visual da foto da empresa: moldura, recorte, "Alterar foto" e dica | ✅ |
| UI-20 | Responsivo | 24 telas medidas em 390, 768 e 1024 px: nenhuma rola para o lado e nenhuma tabela fica cortada | ✅ |
| UI-21 | Header em 950 px | Tema, sininho e usuário continuam visíveis | ✅ |

---

## 9. Testes de migração do banco

| ID | Cenário | Passos | Esperado | Resultado |
|---|---|---|---|---|
| MIG-01 | Banco antigo com dados | Carregar o `banco.sql` anterior + dados e subir o app | `empresa_id` criado em 9 tabelas e preenchido com a 1ª empresa; índices únicos trocados por `(empresa_id, coluna)` | ✅ |
| MIG-02 | Rodar de novo | Subir o app uma segunda vez | Nenhuma alteração, nenhum erro | ✅ |
| MIG-03 | Banco novo | `banco.sql` atual do zero | Todas as tabelas já com `empresa_id` e chaves compostas; duas empresas com o mesmo SKU/CNPJ convivem | ✅ |

---

## 10. Registro de defeitos encontrados e corrigidos

Severidade: 🔴 crítico · 🟠 alto · 🟡 médio · 🟢 baixo.

### Segurança e SaaS

| ID | Defeito | Sev. | Correção |
|---|---|---|---|
| D-01 | Nenhuma separação entre empresas: qualquer empresa via e editava dados de todas | 🔴 | `empresa_id` + guarda central + consultas filtradas + migração |
| D-02 | Trocar o número na URL abria registros de outra empresa | 🔴 | Guarda `proteger_dados_da_empresa` (404) |
| D-03 | Login gravava a senha digitada e o hash no log | 🔴 | `print`s removidos |
| D-04 | Perfis (admin/gerente/operador) não tinham efeito | 🟠 | Regras por rota + botões ocultos |
| D-05 | Só era possível um usuário por empresa | 🟠 | Tela **Usuários** |
| D-06 | Chave de sessão aleatória: reiniciar o servidor deslogava todos | 🟠 | `FLASK_SECRET_KEY` ou `instance/secret_key` |
| D-07 | SKU, CNPJ e CPF únicos no banco inteiro (uma empresa bloqueava a outra) | 🟠 | Unicidade por empresa |
| D-08 | O mesmo e-mail em duas empresas entrava em conta aleatória | 🟡 | Login pela conta cuja senha confere |
| D-09 | Cadastro aceitava senha de 1 caractere | 🟡 | Mínimo de 6 |
| D-10 | Erros mostravam a mensagem técnica do banco | 🟢 | Mensagens amigáveis |

### Regras de negócio e dados

| ID | Defeito | Sev. | Correção |
|---|---|---|---|
| D-11 | Preço digitado com vírgula ("12,50") era gravado como **0** | 🟠 | `to_float` aceita o formato brasileiro |
| D-12 | Não era possível editar produto | 🟠 | Rota e formulário corrigidos |
| D-13 | Preço não aparecia no pedido de saída | 🟠 | Preço vindo do banco, preenchido na hora |
| D-14 | Pedido de entrada não encontrava os produtos do fornecedor | 🟠 | Consulta corrigida; sem botão "Carregar" |
| D-15 | Tela de movimentações não salvava/listava | 🟠 | Rota e campos alinhados ao banco |
| D-16 | "Editar" no pedido do cliente abria rota de pedido de fornecedor | 🟠 | Tela `editar_pedido_cliente` própria |
| D-17 | Desativar produto em Itens por Fornecedor não funcionava | 🟡 | Ação e retorno corrigidos |
| D-18 | Pesquisa sem filtro em várias telas | 🟡 | Busca no servidor |
| D-19 | CPF/CNPJ só testado como "preenchido"; o pontuado era recusado | 🟡 | `validar_documento` com dígitos verificadores |
| D-20 | CNPJ da empresa demo era inválido | 🟢 | CNPJ válido |
| D-21 | Configuração não salvava nada (sem rotas) | 🟠 | Rotas de perfil, senha e empresa |
| D-22 | Configuração não carregava a foto atual da empresa | 🟡 | Consulta inclui `imagem` |
| D-23 | Dashboard com números fixos | 🟠 | Dados reais |
| D-24 | "Total gasto" do cliente somava pedidos cancelados | 🟡 | Cancelados excluídos |
| D-25 | Empilhadeira não podia ser atribuída a funcionário | 🟡 | Campo `funcionario_id` |
| D-26 | Quantidades exibidas como "50.000" | 🟢 | Filtro `quantidade` |
| D-27 | Card do galpão abria as informações em vez do estoque | 🟢 | Link para `/estoque/<id>` |
| D-28 | Galpão: dois campos "nome"; a edição do segundo era ignorada | 🟡 | Campo duplicado removido |
| D-29 | Galpão com CEP antigo ("12345-000") não salvava | 🟡 | CEP normalizado no formulário |
| D-30 | Upload de imagem do produto sem validação | 🟡 | `salvar_imagem` compartilhado |
| D-31 | Imagens de fornecedor, galpão e produto não funcionavam | 🟡 | Upload e exibição corrigidos |
| D-32 | `find_all_consolidado` definido duas vezes | 🟢 | Duplicata removida |

### Interface

| ID | Defeito | Sev. | Correção |
|---|---|---|---|
| D-33 | Confirmação abria **todas** as janelas da página | 🟠 | Seletor `+ label +` |
| D-34 | Internal Server Error em várias telas (filtros Jinja com precedência errada) | 🟠 | Expressões entre parênteses |
| D-35 | Botão de modo escuro não funcionava | 🟡 | Tema na sessão + `tema.js` |
| D-36 | Menu escuro preto demais / item selecionado errado | 🟢 | Cinza e mapa `MODULOS` |
| D-37 | Hover do menu desalinhado | 🟢 | CSS |
| D-38 | `alert()` e `confirm()` do navegador | 🟢 | Notificações e `_confirmar` |
| D-39 | Botões de ação empilhados nas tabelas | 🟢 | `.acoes-linha` |
| D-40 | Barra de pesquisa com botão "Buscar" fora do padrão | 🟢 | Padrão único |
| D-41 | Configuração desorganizada | 🟢 | Layout novo |
| D-42 | Confirmações de exclusão dependiam do JS do Bootstrap | 🟡 | `_confirmar.html` |
| D-43 | `<button>` dentro de `<a>` (9 lugares) | 🟢 | Links com estilo de botão |
| D-44 | CSS do modo escuro espalhado em 8 arquivos (~220 regras) | 🟢 | Um arquivo com variáveis |
| D-45 | Includes quebravam com variáveis opcionais | 🟡 | Checagem `is defined` |

### Encontrados pelos testes de robustez e regressão

| ID | Defeito | Sev. | Correção |
|---|---|---|---|
| D-46 | Funcionário/empilhadeira sem galpão → erro 500 (`url_for` sem id) | 🟡 | `voltar_galpao()` |
| D-47 | Configuração quebrada por `endif` faltando (regressão) | 🟠 | Template corrigido; teste cobre |
| D-48 | Teste de documento falhava na 2ª execução (dado sobrando) | 🟢 | O teste limpa antes |
| D-49 | Helper de teste lia o resultado depois do commit | 🟢 | Ordem corrigida |
| D-50 | Falso positivo: a página de busca repete o termo | 🟢 | O teste olha só os resultados |
| D-51 | Formulário de exclusão órfão (sem botão) em `info_cliente` | 🟢 | Removido |
| D-52 | Arquivos `__pycache__` e imagens de teste entrando no commit | 🟢 | `.gitignore` |
| D-53 | Textos com gênero presumido ("para ele entrar") | 🟢 | Linguagem neutra |
| D-54 | Sininho e alertas contavam produtos de todas as empresas | 🔴 | Filtro por empresa |
| D-55 | Busca geral mostrava dados de todas as empresas | 🔴 | Filtro por empresa |
| D-56 | Validação de CPF/CNPJ duplicado olhava todas as empresas | 🟠 | Filtro por empresa |
| D-57 | Conta desativada continuava navegando até sair | 🟠 | Usuário relido a cada requisição |
| D-58 | Admin podia se rebaixar ou se desativar (empresa sem admin) | 🟡 | Bloqueado |
| D-59 | No celular, Dashboard, Usuários e Galpões rolavam para o lado (cards e header mais largos que a tela) | 🟡 | `min-width: 0` nos cards e header do Galpões sem margem negativa |
| D-60 | Cadastro de empresa dizia "CPF ou CNPJ", mas exigia 14 dígitos | 🟠 | Aceita CPF (11) ou CNPJ (14) |
| D-61 | CPF do funcionário gravado sem validação; salário "3.000,00" dava erro | 🟡 | `validar_cpf_funcionario` + `to_float` |
| D-62 | Foto da empresa esticada no menu lateral (logo não quadrado) | 🟢 | `object-fit: cover` |
| D-63 | Campo de imagem de produto/galpão/fornecedor fora do padrão da Configuração | 🟢 | `_imagem_upload.html` redesenhado |
| D-64 | Botão "Filtros" só reenviava a busca, sem nenhuma opção | 🟡 | Menu de ordenação e situação (`_filtros.html`) |
| D-65 | Itens por Fornecedor: busca, Filtros e Exportar não faziam nada | 🟡 | Busca no servidor, menu de filtros e exportação CSV |
| D-66 | Estoque mostrava produtos inativos sem indicar a situação | 🟡 | Coluna Situação, linha acinzentada e botão Reativar |
| D-67 | Atualizar galpão recusava telefone com pontuação | 🟡 | `validar_telefone_campo` |
| D-68 | Telefone aparecia sem máscara nos formulários de edição | 🟢 | Filtro `telefone` nos campos |
| D-69 | Header perdia tema, sininho e usuário em janelas médias | 🟡 | Busca encolhe; controles com `flex-shrink: 0` |
| D-70 | Telas de detalhe (galpão, produto, fornecedor, cliente) estouravam no celular | 🟡 | Regras responsivas gerais (tabelas com rolagem, botões quebrando linha) |
| D-71 | Produto abaixo do mínimo não aparecia no sininho nem no dashboard quando estava desativado ou com a situação em branco | 🟠 | Regra única `alertas_estoque()` + preferência "Incluir produtos inativos" |
| D-72 | Não havia como configurar as notificações | 🟢 | Card **Notificações** na Configuração |
| D-73 | Teste de pesquisa dava falso positivo com o nome do cliente no sininho | 🟢 | O teste ignora o header |
| D-74 | CSRF: página de outro site conseguia enviar POST com a sessão do usuário (desativou um produto no teste) | 🔴 | Checagem de origem + cookie `SameSite=Lax` |
| D-75 | Login sem limite de tentativas (força bruta) | 🟠 | Bloqueio de 15 min após 5 erros |
| D-76 | Saldo lido sem trava: saídas simultâneas podiam deixar o estoque negativo | 🟠 | `SELECT ... FOR UPDATE` |
| D-77 | Entrada de 2,5 unidades virava 3 no estoque (coluna inteira) sem aviso | 🟡 | Quantidades inteiras obrigatórias |
| D-78 | Ajuste de inventário em Movimentações não permitia zerar o saldo | 🟡 | Ajuste aceita 0 |
| D-79 | Pedido de entrada aceitava preço negativo | 🟡 | Validação |
| D-80 | Excluir galpão com histórico mostrava o erro do MySQL (1451 … foreign key) | 🟢 | Mensagem explicando e sugerindo Inativo |
| D-81 | Mensagens de duplicado ficaram genéricas depois da unicidade por empresa | 🟢 | Índices nomeados `uq_<tabela>_empresa_<coluna>` |
| D-82 | 6 mensagens de erro ainda mostravam a exceção crua | 🟢 | `mensagem_erro()` |
| D-83 | Sem cabeçalhos contra clickjacking e MIME sniffing | 🟢 | `after_request` com os cabeçalhos |

---

## 11. Não coberto / riscos residuais

| Item | Motivo | Mitigação sugerida |
|---|---|---|
| Envio real de e-mail de recuperação | O sistema não tem serviço de e-mail (o link vai para o log) | Testar depois de integrar SMTP |
| Modais de "Adicionar" com o CDN do Bootstrap bloqueado | Dependem de JS externo | Converter para páginas ou modais só com CSS |
| Carga e concorrência (muitos usuários simultâneos) | Fora do escopo | Teste de carga antes da produção |
| Navegadores além do Chromium | Só o Chromium foi automatizado | Conferência manual no Firefox e no Safari |
| Acessibilidade completa (leitor de tela) | Só a leitura por voz foi conferida | Auditoria com Lighthouse/axe |
