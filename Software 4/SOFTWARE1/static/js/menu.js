const btnMenuMobile = document.getElementById("btnMenuMobile");
const menu = document.getElementById("menu");
const btnMinimizar = document.getElementById("btn-minimizar");

const btnVoz = document.getElementById("btnVoz");
const iconeVoz = document.getElementById("iconeVoz");


/* =========================================
   RESTAURAR ESTADO DA SIDEBAR
========================================= */

if (menu) {

    const sidebarMinimizada = localStorage.getItem("sidebarMinimizada");

    if (sidebarMinimizada === "true") {

        menu.classList.add("minimizada");
        document.body.classList.add("sidebar-minimizada");

        if (btnMinimizar) {
            btnMinimizar.setAttribute("aria-expanded", "false");
            btnMinimizar.setAttribute("aria-label", "Expandir menu");
            btnMinimizar.setAttribute("title", "Expandir menu");
        }

    }

}


/* =========================================
   LIBERAR ANIMAÇÕES
========================================= */

requestAnimationFrame(() => {

    requestAnimationFrame(() => {

        document.documentElement.classList.remove(
            "sidebar-pre-minimizada"
        );

    });

});


/* =========================================
   MENU MOBILE
========================================= */

if (btnMenuMobile && menu) {

    btnMenuMobile.addEventListener("click", function () {

        const aberto = menu.classList.toggle("menu-aberto");

        btnMenuMobile.setAttribute(
            "aria-expanded",
            aberto
        );

        btnMenuMobile.setAttribute(
            "aria-label",
            aberto ? "Fechar menu" : "Abrir menu"
        );

        btnMenuMobile.setAttribute(
            "title",
            aberto ? "Fechar menu" : "Abrir menu"
        );

        if (aberto) {

            const primeiroLink = menu.querySelector("nav a");

            if (primeiroLink) {
                primeiroLink.focus();
            }

        }

    });

}


/* =========================================
   ESC FECHA MENU MOBILE
========================================= */

document.addEventListener("keydown", function (event) {

    if (event.key === "Escape") {

        if (menu && menu.classList.contains("menu-aberto")) {

            menu.classList.remove("menu-aberto");

            btnMenuMobile.setAttribute(
                "aria-expanded",
                "false"
            );

            btnMenuMobile.setAttribute(
                "aria-label",
                "Abrir menu"
            );

            btnMenuMobile.setAttribute(
                "title",
                "Abrir menu"
            );

            btnMenuMobile.focus();

        }

    }

});


/* =========================================
   MINIMIZAR SIDEBAR
========================================= */

if (btnMinimizar && menu) {

    btnMinimizar.addEventListener("click", function () {

        const minimizada = menu.classList.toggle("minimizada");

        document.body.classList.toggle(
            "sidebar-minimizada",
            minimizada
        );

        btnMinimizar.setAttribute(
            "aria-expanded",
            !minimizada
        );

        btnMinimizar.setAttribute(
            "aria-label",
            minimizada
                ? "Expandir menu"
                : "Minimizar menu"
        );

        btnMinimizar.setAttribute(
            "title",
            minimizada
                ? "Expandir menu"
                : "Minimizar menu"
        );

        localStorage.setItem(
            "sidebarMinimizada",
            minimizada
        );

    });

}


