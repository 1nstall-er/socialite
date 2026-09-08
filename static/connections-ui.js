(function () {
  "use strict";
  document.querySelectorAll("[data-chat-starter]").forEach(function (button) {
    button.addEventListener("click", function () {
      var input = document.querySelector('textarea[name="texto"]');
      if (!input) return;
      if (!input.value.trim()) input.value = button.textContent.trim();
      input.focus();
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
  });
  var dialog = document.querySelector("[data-match-dialog]");
  if (!dialog || !dialog.showModal) return;
  document.querySelectorAll("[data-accept-connection]").forEach(function (form) {
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      var button = form.querySelector("button");
      button.disabled = true;
      var error = document.querySelector("[data-connection-error]");
      error.textContent = "";
      try {
        var response = await fetch(form.action, {method: "POST", body: new FormData(form), headers: {Accept: "application/json"}});
        var data = await response.json();
        if (!response.ok || !data.ok) throw new Error(data.error || "No pudimos aceptar la invitación.");
        if (!data.match) { window.location.reload(); return; }
        dialog.querySelector("[data-match-name]").textContent = data.conexion.persona.nombre;
        dialog.querySelector("[data-match-plan]").textContent = data.conexion.plan_tema || "Ya pueden conversar y organizarse.";
        dialog.querySelector("[data-match-chat]").href = "/mensajes/" + data.conexion.persona.id;
        dialog.showModal();
      } catch (failure) {
        error.textContent = failure.message || "Comprueba tu conexión e inténtalo nuevamente.";
        button.disabled = false;
      }
    });
  });
  dialog.addEventListener("close", function () { window.location.reload(); });
})();
