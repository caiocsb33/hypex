document.addEventListener("DOMContentLoaded", function () {

    const btnTema = document.getElementById("btnTema");
    const iconeTema = document.getElementById("iconeTema");

    if (!btnTema) {
        return;
    }


    // Verifica se o usuário já escolheu um tema

    const temaSalvo = localStorage.getItem("tema");


    // Se o tema salvo for escuro, ativa

    if (temaSalvo === "escuro") {

        document.body.classList.add("modo-escuro");

        iconeTema.classList.remove("bi-circle-half");
        iconeTema.classList.add("bi-sun-fill");

    }


    btnTema.addEventListener("click", function () {

        document.body.classList.toggle("modo-escuro");


        if (document.body.classList.contains("modo-escuro")) {

            localStorage.setItem("tema", "escuro");

            iconeTema.classList.remove("bi-circle-half");
            iconeTema.classList.add("bi-sun-fill");

        } else {

            localStorage.setItem("tema", "claro");

            iconeTema.classList.remove("bi-sun-fill");
            iconeTema.classList.add("bi-circle-half");

        }

    });

});