document.addEventListener("DOMContentLoaded", function () {

    const menuToggle = document.getElementById("menu-toggle");
    const menu = document.querySelector(".menu");
    const menuLinks = document.querySelectorAll(".menu a");

    // Verifica se os elementos existem
    if (!menuToggle || !menu) {
        console.log("ERRO: botão ou menu não encontrado!");
        return;
    }

    console.log("MENU JS CARREGADO!");

    // Abrir / fechar menu
    menuToggle.addEventListener("click", function (event) {

        event.stopPropagation();

        menu.classList.toggle("active");

        if (menu.classList.contains("active")) {
            menuToggle.innerHTML = "✕";
        } else {
            menuToggle.innerHTML = "☰";
        }

    });

    // Fechar ao clicar em um link
    menuLinks.forEach(function (link) {

        link.addEventListener("click", function () {

            menu.classList.remove("active");
            menuToggle.innerHTML = "☰";

        });

    });

    // Fechar ao clicar fora
    document.addEventListener("click", function (event) {

        const clicouNoMenu = menu.contains(event.target);
        const clicouNoBotao = menuToggle.contains(event.target);

        if (!clicouNoMenu && !clicouNoBotao) {

            menu.classList.remove("active");
            menuToggle.innerHTML = "☰";

        }

    });

    // Fechar ao voltar para desktop
    window.addEventListener("resize", function () {

        if (window.innerWidth > 768) {

            menu.classList.remove("active");
            menuToggle.innerHTML = "☰";

        }

    });

});