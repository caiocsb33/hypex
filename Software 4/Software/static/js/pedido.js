// ============================================================
// PEDIDO DE SAÍDA - HYPEX
// ============================================================

// Lista de itens adicionados ao pedido
let itensPedido = [];

// Guarda o galpão atualmente selecionado
let galpaoSelecionado = null;


// ============================================================
// ELEMENTOS DO HTML
// ============================================================

const selectGalpao = document.getElementById("select-galpao");
const selectProduto = document.getElementById("select-produto");

const inputPreco = document.getElementById("produto-preco");
const inputQtd = document.getElementById("produto-qtd");

const btnAdicionar = document.getElementById("btn-add-produto");

const corpoTabela = document.getElementById("corpo-tabela-itens");
const totalPedido = document.getElementById("total-pedido-valor");

const inputItensJson = document.getElementById("itens-json");
const formPedido = document.getElementById("form-pedido");


// ============================================================
// FORMATAÇÃO DE MOEDA
// ============================================================

function formatarMoeda(valor) {

    return Number(valor || 0).toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    });

}


// ============================================================
// CARREGAR PRODUTOS DO GALPÃO
// ============================================================

async function atualizarProdutosDoGalpao() {

    const galpaoId = selectGalpao.value;


    // --------------------------------------------------------
    // LIMPA CAMPOS
    // --------------------------------------------------------

    selectProduto.innerHTML = `
        <option value="">
            -- Selecione primeiro o galpão --
        </option>
    `;

    selectProduto.disabled = true;

    inputPreco.value = "";
    inputQtd.value = 1;

    btnAdicionar.disabled = true;


    // --------------------------------------------------------
    // SE NÃO SELECIONOU GALPÃO
    // --------------------------------------------------------

    if (!galpaoId) {

        galpaoSelecionado = null;

        return;
    }


    // --------------------------------------------------------
    // VERIFICA SE TROCOU O GALPÃO
    // --------------------------------------------------------

    if (
        itensPedido.length > 0 &&
        galpaoSelecionado !== null &&
        String(galpaoSelecionado) !== String(galpaoId)
    ) {

        const confirmar = confirm(
            "Ao mudar o galpão, os produtos já adicionados ao pedido serão removidos.\n\nDeseja continuar?"
        );


        if (!confirmar) {

            selectGalpao.value = galpaoSelecionado;

            return;
        }


        itensPedido = [];

        renderizarTabela();
    }


    galpaoSelecionado = galpaoId;


    // --------------------------------------------------------
    // LOADING
    // --------------------------------------------------------

    selectProduto.innerHTML = `
        <option value="">
            Carregando produtos...
        </option>
    `;


    try {

        console.log("================================");
        console.log("BUSCANDO PRODUTOS");
        console.log("GALPÃO:", galpaoId);
        console.log("================================");


        // ----------------------------------------------------
        // CHAMA A SUA API DO FLASK
        // ----------------------------------------------------

        const resposta = await fetch(
            `/api/produtos_do_galpao/${galpaoId}`
        );


        if (!resposta.ok) {

            throw new Error(
                `Erro HTTP ${resposta.status}`
            );
        }


        const produtos = await resposta.json();


        console.log("PRODUTOS RECEBIDOS:", produtos);


        // ----------------------------------------------------
        // LIMPA SELECT
        // ----------------------------------------------------

        selectProduto.innerHTML = `
            <option value="">
                -- Selecione um produto --
            </option>
        `;


        // ----------------------------------------------------
        // TRATA ERRO RETORNADO PELA API
        // ----------------------------------------------------

        if (!Array.isArray(produtos)) {

            console.error(
                "Resposta inesperada da API:",
                produtos
            );

            throw new Error(
                "A API não retornou uma lista de produtos."
            );
        }


        // ----------------------------------------------------
        // NENHUM PRODUTO
        // ----------------------------------------------------

        if (produtos.length === 0) {

            selectProduto.innerHTML = `
                <option value="">
                    Nenhum produto disponível neste galpão
                </option>
            `;

            return;
        }


        // ----------------------------------------------------
        // ADICIONA OS PRODUTOS AO SELECT
        // ----------------------------------------------------

        produtos.forEach(produto => {

            const option =
                document.createElement("option");


            // ID
            option.value = produto.id;


            // ------------------------------------------------
            // DADOS DO PRODUTO
            // ------------------------------------------------

            option.dataset.nome =
                produto.nome || "";

            option.dataset.sku =
                produto.sku || "";


            // PREÇO DE VENDA
            option.dataset.preco =
                produto.preco_venda !== null &&
                produto.preco_venda !== undefined
                    ? produto.preco_venda
                    : 0;


            // ESTOQUE
            option.dataset.estoque =
                produto.estoque_disponivel !== null &&
                produto.estoque_disponivel !== undefined
                    ? produto.estoque_disponivel
                    : 0;


            // ------------------------------------------------
            // TEXTO DO SELECT
            // ------------------------------------------------

            option.textContent =
                `${produto.sku || "SEM SKU"} - ${produto.nome} ` +
                `(Estoque: ${produto.estoque_disponivel || 0})`;


            selectProduto.appendChild(option);

        });


        selectProduto.disabled = false;


    } catch (erro) {

        console.error(
            "ERRO AO CARREGAR PRODUTOS:",
            erro
        );


        selectProduto.innerHTML = `
            <option value="">
                Erro ao carregar produtos
            </option>
        `;


        alert(
            "Não foi possível carregar os produtos deste galpão."
        );
    }

}


// ============================================================
// QUANDO O PRODUTO É SELECIONADO
// ============================================================

function verificarPrecoItem() {

    const optionSelecionada =
        selectProduto.options[
            selectProduto.selectedIndex
        ];


    // --------------------------------------------------------
    // NENHUM PRODUTO
    // --------------------------------------------------------

    if (
        !optionSelecionada ||
        !optionSelecionada.value
    ) {

        inputPreco.value = "";

        btnAdicionar.disabled = true;

        return;
    }


    // --------------------------------------------------------
    // PEGA PREÇO
    // --------------------------------------------------------

    const preco =
        parseFloat(
            optionSelecionada.dataset.preco
        ) || 0;


    // --------------------------------------------------------
    // PEGA ESTOQUE
    // --------------------------------------------------------

    const estoque =
        parseInt(
            optionSelecionada.dataset.estoque
        ) || 0;


    // --------------------------------------------------------
    // DEBUG
    // --------------------------------------------------------

    console.log("================================");
    console.log("PRODUTO SELECIONADO");
    console.log("ID:", optionSelecionada.value);
    console.log("NOME:", optionSelecionada.dataset.nome);
    console.log("SKU:", optionSelecionada.dataset.sku);
    console.log("PREÇO:", preco);
    console.log("ESTOQUE:", estoque);
    console.log("================================");


    // --------------------------------------------------------
    // MOSTRA O PREÇO
    // --------------------------------------------------------

    inputPreco.value =
        formatarMoeda(preco);


    // --------------------------------------------------------
    // SEM ESTOQUE
    // --------------------------------------------------------

    if (estoque <= 0) {

        btnAdicionar.disabled = true;

        alert(
            "Este produto não possui estoque disponível neste galpão."
        );

        return;
    }


    // --------------------------------------------------------
    // LIBERA BOTÃO
    // --------------------------------------------------------

    btnAdicionar.disabled = false;


    // Verifica quantidade
    verificarQuantidade();

}


// ============================================================
// VERIFICAR QUANTIDADE
// ============================================================

function verificarQuantidade() {

    const optionSelecionada =
        selectProduto.options[
            selectProduto.selectedIndex
        ];


    if (
        !optionSelecionada ||
        !optionSelecionada.value
    ) {

        btnAdicionar.disabled = true;

        return;
    }


    const estoque =
        parseInt(
            optionSelecionada.dataset.estoque
        ) || 0;


    const quantidade =
        parseInt(
            inputQtd.value
        ) || 0;


    // --------------------------------------------------------
    // QUANTIDADE INVÁLIDA
    // --------------------------------------------------------

    if (quantidade < 1) {

        btnAdicionar.disabled = true;

        inputQtd.setCustomValidity(
            "A quantidade deve ser maior que zero."
        );

        return;
    }


    // --------------------------------------------------------
    // QUANTIDADE MAIOR QUE ESTOQUE
    // --------------------------------------------------------

    if (quantidade > estoque) {

        btnAdicionar.disabled = true;

        inputQtd.setCustomValidity(
            `Estoque disponível: ${estoque}`
        );

        return;
    }


    // --------------------------------------------------------
    // QUANTIDADE VÁLIDA
    // --------------------------------------------------------

    inputQtd.setCustomValidity("");

    btnAdicionar.disabled = false;

}


// ============================================================
// EVENTO DA QUANTIDADE
// ============================================================

inputQtd.addEventListener(
    "input",
    verificarQuantidade
);


// ============================================================
// ADICIONAR PRODUTO AO PEDIDO
// ============================================================

function adicionarItemNaTabela() {

    const optionSelecionada =
        selectProduto.options[
            selectProduto.selectedIndex
        ];


    // --------------------------------------------------------
    // VERIFICA PRODUTO
    // --------------------------------------------------------

    if (
        !optionSelecionada ||
        !optionSelecionada.value
    ) {

        alert(
            "Selecione um produto."
        );

        return;
    }


    // --------------------------------------------------------
    // DADOS
    // --------------------------------------------------------

    const produtoId =
        Number(
            optionSelecionada.value
        );


    const nome =
        optionSelecionada.dataset.nome || "";


    const sku =
        optionSelecionada.dataset.sku || "SEM SKU";


    const preco =
        parseFloat(
            optionSelecionada.dataset.preco
        ) || 0;


    const estoque =
        parseInt(
            optionSelecionada.dataset.estoque
        ) || 0;


    const quantidade =
        parseInt(
            inputQtd.value
        ) || 0;


    // --------------------------------------------------------
    // VALIDAÇÃO QUANTIDADE
    // --------------------------------------------------------

    if (quantidade < 1) {

        alert(
            "Informe uma quantidade válida."
        );

        return;
    }


    // --------------------------------------------------------
    // VALIDAÇÃO ESTOQUE
    // --------------------------------------------------------

    if (quantidade > estoque) {

        alert(
            `Estoque insuficiente.\n\n` +
            `Estoque disponível: ${estoque}\n` +
            `Quantidade solicitada: ${quantidade}`
        );

        return;
    }


    // --------------------------------------------------------
    // VERIFICA SE JÁ EXISTE NO PEDIDO
    // --------------------------------------------------------

    const itemExistente =
        itensPedido.find(
            item =>
                Number(item.produto_id) === produtoId
        );


    if (itemExistente) {

        const novaQuantidade =
            itemExistente.quantidade +
            quantidade;


        // ----------------------------------------------
        // NÃO PODE PASSAR DO ESTOQUE
        // ----------------------------------------------

        if (
            novaQuantidade >
            itemExistente.estoque_disponivel
        ) {

            alert(
                `Quantidade maior que o estoque disponível.\n\n` +
                `Produto: ${itemExistente.nome}\n` +
                `Estoque: ${itemExistente.estoque_disponivel}\n` +
                `Já no pedido: ${itemExistente.quantidade}`
            );

            return;
        }


        itemExistente.quantidade =
            novaQuantidade;


    } else {

        // ----------------------------------------------
        // NOVO ITEM
        // ----------------------------------------------

        itensPedido.push({

            produto_id: produtoId,

            sku: sku,

            nome: nome,

            quantidade: quantidade,

            preco_unitario: preco,

            estoque_disponivel: estoque

        });

    }


    // --------------------------------------------------------
    // ATUALIZA TABELA
    // --------------------------------------------------------

    renderizarTabela();


    // --------------------------------------------------------
    // LIMPA CAMPOS
    // --------------------------------------------------------

    selectProduto.value = "";

    inputPreco.value = "";

    inputQtd.value = 1;

    btnAdicionar.disabled = true;

}


// ============================================================
// RENDERIZAR TABELA
// ============================================================

function renderizarTabela() {

    corpoTabela.innerHTML = "";


    // --------------------------------------------------------
    // NENHUM ITEM
    // --------------------------------------------------------

    if (itensPedido.length === 0) {

        corpoTabela.innerHTML = `
            <tr id="linha-vazia">

                <td
                    colspan="6"
                    class="text-center text-muted py-4"
                >

                    Nenhum produto adicionado ao pedido ainda.

                </td>

            </tr>
        `;


        atualizarTotal();

        return;
    }


    // --------------------------------------------------------
    // CRIA CADA LINHA
    // --------------------------------------------------------

    itensPedido.forEach(
        (item, index) => {

            const subtotal =
                item.quantidade *
                item.preco_unitario;


            const linha =
                document.createElement("tr");


            linha.innerHTML = `

                <!-- SKU -->

                <td>
                    ${escapeHtml(item.sku)}
                </td>


                <!-- PRODUTO -->

                <td>
                    ${escapeHtml(item.nome)}
                </td>


                <!-- QUANTIDADE -->

                <td>

                    <input
                        type="number"
                        min="1"
                        max="${item.estoque_disponivel}"
                        value="${item.quantidade}"
                        class="form-control form-control-sm"
                        style="width: 90px;"
                        onchange="alterarQuantidade(${index}, this.value)"
                    >

                </td>


                <!-- PREÇO -->

                <td>

                    R$
                    ${formatarMoeda(
                        item.preco_unitario
                    )}

                </td>


                <!-- SUBTOTAL -->

                <td>

                    R$
                    ${formatarMoeda(
                        subtotal
                    )}

                </td>


                <!-- AÇÕES -->

                <td>

                    <button
                        type="button"
                        class="btn btn-sm btn-danger"
                        onclick="removerItem(${index})"
                        title="Remover produto"
                    >

                        <i class="bi bi-trash"></i>

                    </button>

                </td>

            `;


            corpoTabela.appendChild(
                linha
            );

        }
    );


    // Atualiza total
    atualizarTotal();

}


// ============================================================
// ALTERAR QUANTIDADE DE ITEM
// ============================================================

function alterarQuantidade(
    index,
    novaQuantidade
) {

    const item =
        itensPedido[index];


    if (!item) {
        return;
    }


    novaQuantidade =
        parseInt(novaQuantidade) || 0;


    // --------------------------------------------------------
    // MÍNIMO
    // --------------------------------------------------------

    if (novaQuantidade < 1) {

        alert(
            "A quantidade mínima é 1."
        );

        renderizarTabela();

        return;
    }


    // --------------------------------------------------------
    // ESTOQUE
    // --------------------------------------------------------

    if (
        novaQuantidade >
        item.estoque_disponivel
    ) {

        alert(
            `Estoque disponível: ${item.estoque_disponivel}`
        );

        renderizarTabela();

        return;
    }


    // --------------------------------------------------------
    // SALVA NOVA QUANTIDADE
    // --------------------------------------------------------

    item.quantidade =
        novaQuantidade;


    renderizarTabela();

}


// ============================================================
// REMOVER ITEM
// ============================================================

function removerItem(index) {

    if (!itensPedido[index]) {
        return;
    }


    itensPedido.splice(
        index,
        1
    );


    renderizarTabela();

}


// ============================================================
// CALCULAR TOTAL
// ============================================================

function atualizarTotal() {

    const total =
        itensPedido.reduce(
            (soma, item) => {

                return soma +
                    (
                        Number(item.quantidade) *
                        Number(item.preco_unitario)
                    );

            },
            0
        );


    totalPedido.textContent =
        formatarMoeda(total);


    atualizarJson();

}


// ============================================================
// ATUALIZAR INPUT HIDDEN COM JSON
// ============================================================

function atualizarJson() {

    const itensParaEnviar =
        itensPedido.map(
            item => ({

                produto_id:
                    Number(item.produto_id),

                quantidade:
                    Number(item.quantidade),

                preco_unitario:
                    Number(item.preco_unitario)

            })
        );


    inputItensJson.value =
        JSON.stringify(
            itensParaEnviar
        );


    console.log(
        "JSON DO PEDIDO:",
        inputItensJson.value
    );

}


// ============================================================
// ESCAPAR HTML
// ============================================================

function escapeHtml(texto) {

    const div =
        document.createElement("div");


    div.textContent =
        texto ?? "";


    return div.innerHTML;

}


// ============================================================
// ENVIO DO FORMULÁRIO
// ============================================================

formPedido.addEventListener(
    "submit",
    function(event) {

        // ----------------------------------------------------
        // VERIFICA GALPÃO
        // ----------------------------------------------------

        if (!selectGalpao.value) {

            event.preventDefault();

            alert(
                "Selecione o galpão de retirada."
            );

            return;
        }


        // ----------------------------------------------------
        // VERIFICA ITENS
        // ----------------------------------------------------

        if (
            !itensPedido ||
            itensPedido.length === 0
        ) {

            event.preventDefault();

            alert(
                "Adicione pelo menos um produto ao pedido."
            );

            return;
        }


        // ----------------------------------------------------
        // ATUALIZA JSON
        // ----------------------------------------------------

        atualizarJson();


        console.log(
            "================================"
        );

        console.log(
            "ENVIANDO PEDIDO"
        );

        console.log(
            "GALPÃO:",
            selectGalpao.value
        );

        console.log(
            "ITENS:",
            itensPedido
        );

        console.log(
            "JSON:",
            inputItensJson.value
        );

        console.log(
            "================================"
        );

    }
);


// ============================================================
// DATA AUTOMÁTICA
// ============================================================

document.addEventListener(
    "DOMContentLoaded",
    function() {

        const campoData =
            document.querySelector(
                'input[name="data_saida"]'
            );


        if (
            campoData &&
            !campoData.value
        ) {

            const hoje =
                new Date();


            const ano =
                hoje.getFullYear();


            const mes =
                String(
                    hoje.getMonth() + 1
                ).padStart(2, "0");


            const dia =
                String(
                    hoje.getDate()
                ).padStart(2, "0");


            campoData.value =
                `${ano}-${mes}-${dia}`;
        }

    }
);