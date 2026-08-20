const btnMenuMobile = document.getElementById("btnMenuMobile");
const menu = document.getElementById("menu");
const btnMinimizar = document.getElementById("btn-minimizar");


/* =========================================
   RESTAURAR ESTADO DA SIDEBAR
========================================= */

if (menu) {

    const sidebarMinimizada = localStorage.getItem("sidebarMinimizada");

    if (sidebarMinimizada === "true") {

        menu.classList.add("minimizada");
        document.body.classList.add("sidebar-minimizada");

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

        menu.classList.toggle("menu-aberto");

    });

}


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

        localStorage.setItem(
            "sidebarMinimizada",
            minimizada
        );

    });

}