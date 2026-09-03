/* =========================================================
   TELAS DE PEDIDO: FILTRO DE PRODUTOS E PREÇO
   =========================================================

   A página recebe do servidor TODOS os produtos, cada <option> marcada com o
   galpão (saída) ou o fornecedor (entrada) a que pertence. Este arquivo apenas
   esconde as opções que não servem e preenche o preço ao escolher o produto —
   por isso trocar de galpão ou de fornecedor não recarrega a tela.

   A regra de negócio continua toda no servidor: o preço gravado e a conferência
   de saldo são feitos na rota, não aqui. Sem JavaScript a tela continua
   utilizável, apenas mostrando a lista completa de produtos.
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    var selectProduto = document.getElementById("select-produto");

    if (!selectProduto) {
        return;
    }

    var selectGalpao     = document.getElementById("select-galpao");
    var selectFornecedor = document.getElementById("select-fornecedor");
    var campoPreco       = document.getElementById("campo-preco");
    var campoQuantidade  = document.getElementById("campo-quantidade");

    // Campos escondidos do formulário que fecha o pedido
    var galpaoDoPedido     = document.getElementById("galpao-do-pedido");
    var fornecedorDoPedido = document.getElementById("fornecedor-do-pedido");

    // Guarda todas as opções: as escondidas precisam voltar quando o
    // usuário troca de galpão ou de fornecedor.
    var todasAsOpcoes = [];

    Array.prototype.forEach.call(selectProduto.options, function (opcao) {
        if (opcao.value) {
            todasAsOpcoes.push(opcao);
        }
    });

    var textoInicial = selectProduto.options.length
        ? selectProduto.options[0].textContent
        : "-- Selecione o produto --";

    function filtrarProdutos() {

        // Na saída o filtro é por galpão; na entrada, por fornecedor
        var filtroGalpao = selectGalpao ? selectGalpao.value : "";
        var filtroFornecedor = selectFornecedor ? selectFornecedor.value : "";
        var chaveAtiva = selectFornecedor ? filtroFornecedor : filtroGalpao;

        var selecionadoAntes = selectProduto.value;
        var disponiveis = [];

        todasAsOpcoes.forEach(function (opcao) {
            var serve;

            if (selectFornecedor) {
                var doFornecedor = opcao.getAttribute("data-fornecedor") || "";
                // Produto sem vínculo serve para qualquer fornecedor
                serve = !filtroFornecedor
                    || doFornecedor === ""
                    || doFornecedor === filtroFornecedor;
            } else {
                serve = opcao.getAttribute("data-galpao") === filtroGalpao;
            }

            if (serve) {
                disponiveis.push(opcao);
            }
        });

        // Remonta a lista
        selectProduto.innerHTML = "";

        var vazia = document.createElement("option");
        vazia.value = "";

        if (!chaveAtiva) {
            vazia.textContent = textoInicial;
        } else if (!disponiveis.length) {
            vazia.textContent = selectFornecedor
                ? "-- Nenhum produto para este fornecedor --"
                : "-- Nenhum produto com saldo neste galpão --";
        } else {
            vazia.textContent = "-- Selecione o produto --";
        }

        selectProduto.appendChild(vazia);

        disponiveis.forEach(function (opcao) {
            selectProduto.appendChild(opcao);
        });

        // Mantém a escolha anterior, se ela ainda fizer sentido
        if (selecionadoAntes) {
            selectProduto.value = selecionadoAntes;
        }

        selectProduto.disabled = !chaveAtiva || !disponiveis.length;

        // Espelha as escolhas no formulário de fechamento
        if (galpaoDoPedido && selectGalpao) {
            galpaoDoPedido.value = selectGalpao.value;
        }

        if (fornecedorDoPedido && selectFornecedor) {
            fornecedorDoPedido.value = selectFornecedor.value;
        }

        preencherPreco();
    }

    function preencherPreco() {

        var opcao = selectProduto.options[selectProduto.selectedIndex];

        if (!selectProduto.value || !opcao) {
            if (campoPreco) {
                campoPreco.value = "";
            }
            return;
        }

        var preco = opcao.getAttribute("data-preco");
        var saldo = opcao.getAttribute("data-saldo");

        if (campoPreco && preco !== null) {
            // Na saída o campo é somente leitura e mostra o valor formatado;
            // na entrada é editável e recebe o número puro, para poder somar.
            campoPreco.value = campoPreco.readOnly
                ? parseFloat(preco).toFixed(2).replace(".", ",")
                : parseFloat(preco).toFixed(2);
        }

        // Na saída o saldo limita a quantidade que pode ser pedida
        if (campoQuantidade && saldo !== null) {
            campoQuantidade.max = saldo;

            if (parseFloat(campoQuantidade.value) > parseFloat(saldo)) {
                campoQuantidade.value = saldo;
            }
        }
    }

    if (selectGalpao) {
        selectGalpao.addEventListener("change", filtrarProdutos);
    }

    if (selectFornecedor) {
        selectFornecedor.addEventListener("change", filtrarProdutos);
    }

    selectProduto.addEventListener("change", preencherPreco);

    // Estado inicial (inclusive ao voltar para a página com algo já escolhido)
    filtrarProdutos();
});
