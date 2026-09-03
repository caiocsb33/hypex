const menuToggle = document.getElementById('menuToggle');
const menu = document.getElementById('menu');
const overlay = document.getElementById('menuOverlay');

if (menuToggle && menu && overlay) {
    menuToggle.addEventListener('click', () => {
        menuToggle.classList.toggle('active');
        menu.classList.toggle('active');
        overlay.classList.toggle('active');
    });

    overlay.addEventListener('click', () => {
        menuToggle.classList.remove('active');
        menu.classList.remove('active');
        overlay.classList.remove('active');
    });

    // Fecha o menu ao clicar em algum link
    menu.querySelectorAll('a').forEach(link => {
        link.addEventListener('click', () => {
            menuToggle.classList.remove('active');
            menu.classList.remove('active');
            overlay.classList.remove('active');
        });
    });
}
