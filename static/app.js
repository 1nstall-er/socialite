(function () {
  "use strict";

  var boton = document.querySelector(".menu-boton");
  var menu = document.getElementById("menu-principal");
  if (!boton || !menu) return;

  function cerrar() {
    menu.classList.remove("abierto");
    boton.setAttribute("aria-expanded", "false");
    boton.setAttribute("aria-label", "Abrir menú");
  }

  boton.addEventListener("click", function () {
    var abierto = menu.classList.toggle("abierto");
    boton.setAttribute("aria-expanded", String(abierto));
    boton.setAttribute("aria-label", abierto ? "Cerrar menú" : "Abrir menú");
  });

  menu.addEventListener("click", function (evento) {
    if (evento.target.closest("a")) cerrar();
  });

  document.addEventListener("keydown", function (evento) {
    if (evento.key === "Escape") cerrar();
  });
})();
