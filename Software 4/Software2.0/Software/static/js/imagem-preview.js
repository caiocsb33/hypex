/* =========================================================
   PRÉ-VISUALIZAÇÃO DA IMAGEM ESCOLHIDA
   =========================================================

   Mostra a imagem antes de salvar e avisa quando o arquivo não serve.
   O aviso aparece na própria tela, e não em uma caixa do navegador.

   A validação de verdade é feita no servidor (salvar_imagem, em app.py);
   aqui é só para o usuário não descobrir o problema depois de enviar.
========================================================= */

document.addEventListener("DOMContentLoaded", function () {

    var TIPOS_PERMITIDOS = [
        "image/png",
        "image/jpeg",
        "image/jpg",
        "image/webp",
        "image/gif"
    ];

    var TAMANHO_MAXIMO = 5 * 1024 * 1024; // 5 MB

    var campos = document.querySelectorAll(".campo-imagem .input-imagem");

    Array.prototype.forEach.call(campos, function (campo) {

        var bloco = campo.closest(".campo-imagem");
        var preview = bloco ? bloco.querySelector(".preview-imagem") : null;

        // Espaço para o aviso, criado uma vez por bloco
        var aviso = document.createElement("p");
        aviso.className = "aviso-imagem";
        aviso.hidden = true;
        campo.parentNode.insertBefore(aviso, campo.nextSibling);

        function mostrarAviso(texto) {
            aviso.textContent = texto;
            aviso.hidden = false;
        }

        function limparAviso() {
            aviso.textContent = "";
            aviso.hidden = true;
        }

        campo.addEventListener("change", function () {

            var arquivo = this.files && this.files[0];

            if (!arquivo) {
                limparAviso();
                return;
            }

            if (TIPOS_PERMITIDOS.indexOf(arquivo.type) === -1) {
                mostrarAviso("Formato inválido. Use PNG, JPG, WEBP ou GIF.");
                this.value = "";
                return;
            }

            if (arquivo.size > TAMANHO_MAXIMO) {
                mostrarAviso("A imagem deve ter no máximo 5 MB.");
                this.value = "";
                return;
            }

            limparAviso();

            if (preview) {
                var anterior = preview.dataset.urlTemporaria;

                if (anterior) {
                    URL.revokeObjectURL(anterior);
                }

                var url = URL.createObjectURL(arquivo);
                preview.src = url;
                preview.dataset.urlTemporaria = url;
            }
        });
    });
});
