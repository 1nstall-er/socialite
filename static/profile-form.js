(function () {
  "use strict";

  function normalizar(texto) {
    return String(texto || "")
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .trim();
  }

  function iniciarCiclos(formulario) {
    var carrera = formulario.querySelector("[data-career-select]");
    var ciclo = formulario.querySelector("[data-cycle-select]");
    var ayuda = formulario.querySelector("[data-cycle-help]");
    if (!carrera || !ciclo) return;

    function actualizarCiclos(esInicial) {
      var opcionCarrera = carrera.options[carrera.selectedIndex];
      var maximo = Number(opcionCarrera && opcionCarrera.dataset.ciclos) || 0;
      var valorPrevio = esInicial ? ciclo.dataset.selected : ciclo.value;

      Array.from(ciclo.options).forEach(function (opcion) {
        if (!opcion.value) return;
        var disponible = maximo > 0 && Number(opcion.value) <= maximo;
        opcion.hidden = !disponible;
        opcion.disabled = !disponible;
      });

      ciclo.disabled = maximo === 0;
      ciclo.value = valorPrevio && Number(valorPrevio) <= maximo ? valorPrevio : "";
      if (ayuda) {
        ayuda.textContent = maximo
          ? "Esta carrera tiene " + maximo + " ciclos disponibles."
          : "Elige primero tu carrera.";
      }
    }

    carrera.addEventListener("change", function () {
      actualizarCiclos(false);
    });
    actualizarCiclos(true);
  }

  function iniciarIntereses(formulario) {
    var selector = formulario.querySelector("[data-interest-picker]");
    if (!selector) return;

    var buscador = formulario.querySelector("[data-interest-search]");
    var contador = formulario.querySelector("[data-interest-count]");
    var vacio = selector.querySelector("[data-interest-empty]");
    var opciones = Array.from(selector.querySelectorAll("[data-interest-option]"));
    var checks = opciones.map(function (opcion) {
      return opcion.querySelector('input[type="checkbox"]');
    });
    var maximo = Number(selector.dataset.max) || 12;

    if (contador) contador.setAttribute("aria-live", "polite");

    function actualizarLimite() {
      var elegidos = checks.filter(function (check) {
        return check.checked;
      }).length;
      var completo = elegidos >= maximo;
      checks.forEach(function (check) {
        check.disabled = completo && !check.checked;
        check.closest("[data-interest-option]").classList.toggle(
          "chip-deshabilitado",
          check.disabled
        );
      });
      if (contador) {
        contador.textContent = elegidos + " / " + maximo;
        contador.classList.toggle("limite-alcanzado", completo);
      }
    }

    function filtrar() {
      var consulta = normalizar(buscador ? buscador.value : "");
      var visibles = 0;
      opciones.forEach(function (opcion) {
        var coincide = !consulta || normalizar(opcion.dataset.search).includes(consulta);
        opcion.hidden = !coincide;
        if (coincide) visibles += 1;
      });
      selector.querySelectorAll("[data-interest-group]").forEach(function (grupo) {
        var contieneVisibles = Array.from(
          grupo.querySelectorAll("[data-interest-option]")
        ).some(function (opcion) {
          return !opcion.hidden;
        });
        grupo.hidden = !contieneVisibles;
        if (consulta && contieneVisibles) grupo.open = true;
      });
      if (vacio) vacio.hidden = visibles !== 0;
    }

    checks.forEach(function (check) {
      check.addEventListener("change", actualizarLimite);
    });
    if (buscador) buscador.addEventListener("input", filtrar);
    actualizarLimite();
  }

  function iniciarFoto(formulario) {
    var entrada = formulario.querySelector("[data-photo-input]");
    var vista = formulario.querySelector("[data-photo-preview]");
    if (!entrada || !vista) return;

    var imagen = vista.querySelector("[data-photo-image]");
    var fallback = vista.querySelector("[data-photo-fallback]");
    entrada.addEventListener("change", function () {
      var archivo = entrada.files && entrada.files[0];
      if (!archivo || !imagen) return;
      if (archivo.size > 5 * 1024 * 1024) {
        entrada.setCustomValidity("La foto debe pesar como máximo 5 MB.");
        entrada.reportValidity();
        entrada.value = "";
        return;
      }
      entrada.setCustomValidity("");
      var lector = new FileReader();
      lector.addEventListener("load", function () {
        imagen.src = lector.result;
        imagen.hidden = false;
        if (fallback) fallback.hidden = true;
        vista.classList.add("avatar-con-foto");
      });
      lector.readAsDataURL(archivo);
    });
  }

  function iniciarContador(formulario) {
    var entrada = formulario.querySelector("[data-character-input]");
    var contador = formulario.querySelector("[data-character-count]");
    if (!entrada || !contador) return;
    function actualizar() {
      contador.textContent = entrada.value.length + " / " + entrada.maxLength;
    }
    entrada.addEventListener("input", actualizar);
    actualizar();
  }

  document.querySelectorAll("[data-profile-form]").forEach(function (formulario) {
    iniciarCiclos(formulario);
    iniciarIntereses(formulario);
    iniciarFoto(formulario);
    iniciarContador(formulario);
  });
})();
