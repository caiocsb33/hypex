const btnMenuMobile = document.getElementById("btnMenuMobile");
const menu = document.getElementById("menu");

if (btnMenuMobile && menu) {

    btnMenuMobile.addEventListener("click", function () {

        menu.classList.toggle("menu-aberto");

    });

}