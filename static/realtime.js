(function () {
  "use strict";

  var tokenMeta = document.querySelector('meta[name="csrf-token"]');
  var userMeta = document.querySelector('meta[name="current-user-id"]');
  if (!tokenMeta || !userMeta || typeof window.io !== "function") return;

  var currentUserId = Number(userMeta.content);
  var socket = window.io({
    auth: { csrf_token: tokenMeta.content },
    transports: ["websocket", "polling"],
  });

  function updateNotificationCount(total) {
    document.querySelectorAll("[data-notification-count]").forEach(function (badge) {
      badge.textContent = String(total);
      badge.classList.toggle("oculto", total < 1);
    });
  }

  function showToast(title, body, destination) {
    var region = document.querySelector("[data-toast-region]");
    if (!region) {
      region = document.createElement("div");
      region.className = "toast-region";
      region.dataset.toastRegion = "";
      region.setAttribute("aria-live", "polite");
      document.body.appendChild(region);
    }
    var toast = document.createElement(destination ? "a" : "div");
    toast.className = "toast-notificacion";
    if (destination) toast.href = destination;
    var strong = document.createElement("strong");
    strong.textContent = title;
    var text = document.createElement("span");
    text.textContent = body || "Tienes una nueva notificación.";
    toast.append(strong, text);
    region.appendChild(toast);
    window.setTimeout(function () { toast.remove(); }, 6000);
  }

  socket.on("socket_ready", function (data) {
    updateNotificationCount(Number(data.notificaciones_no_leidas) || 0);
  });

  socket.on("notification_received", function (notification) {
    updateNotificationCount(Number(notification.total_no_leidas) || 0);
    showToast(notification.titulo, notification.contenido, notification.destino_url);
  });

  socket.on("notifications_synced", function (data) {
    updateNotificationCount(Number(data.total_no_leidas) || 0);
  });

  var chat = document.querySelector("[data-realtime-chat]");
  if (!chat) return;

  var contactId = Number(chat.dataset.contactId);
  var list = chat.querySelector("[data-message-list]");
  var form = chat.querySelector("[data-message-form]");
  var textarea = form && form.querySelector('textarea[name="texto"]');
  var submit = form && form.querySelector('button[type="submit"]');
  var status = chat.querySelector("[data-realtime-status]");
  var seenMessages = new Set(
    Array.from(chat.querySelectorAll("[data-message-id]")).map(function (item) {
      return Number(item.dataset.messageId);
    })
  );

  function setStatus(text, connected) {
    if (!status) return;
    status.textContent = text;
    status.classList.toggle("realtime-activo", Boolean(connected));
  }

  function belongsToChat(message) {
    return (
      (message.emisor_id === currentUserId && message.receptor_id === contactId) ||
      (message.emisor_id === contactId && message.receptor_id === currentUserId)
    );
  }

  function appendMessage(message) {
    if (!list || seenMessages.has(message.id) || !belongsToChat(message)) return;
    seenMessages.add(message.id);
    var empty = list.querySelector("[data-empty-chat]");
    if (empty) empty.remove();

    var own = message.emisor_id === currentUserId;
    var article = document.createElement("article");
    article.className = "burbuja-mensaje " + (own ? "mensaje-propio" : "mensaje-ajeno");
    article.dataset.messageId = String(message.id);
    article.dataset.senderId = String(message.emisor_id);
    var paragraph = document.createElement("p");
    paragraph.textContent = message.texto;
    var time = document.createElement("small");
    var date = new Date(message.enviado_en);
    time.textContent = Number.isNaN(date.getTime())
      ? "Ahora"
      : date.toLocaleTimeString("es-PE", { hour: "2-digit", minute: "2-digit" });
    article.append(paragraph, time);
    list.appendChild(article);
    list.scrollTop = list.scrollHeight;
  }

  socket.on("connect", function () {
    socket.emit("join_room", { contacto_id: contactId }, function (response) {
      if (response && response.ok) setStatus("En línea · mensajes en tiempo real", true);
      else setStatus("No se pudo abrir el canal en tiempo real.", false);
    });
  });

  socket.on("disconnect", function () {
    setStatus("Reconectando… Puedes seguir enviando por el canal seguro.", false);
  });

  socket.on("connect_error", function () {
    setStatus("Chat en modo clásico. Recarga la página para reconectar.", false);
  });

  socket.on("message_received", function (message) {
    appendMessage(message);
    if (message.emisor_id === contactId) {
      socket.emit("mark_read", { contacto_id: contactId });
    }
  });

  socket.on("messages_read", function (data) {
    if (data.lector_id !== contactId) return;
    chat.querySelectorAll('[data-sender-id="' + currentUserId + '"] small').forEach(
      function (item) {
        if (!item.textContent.includes("Leído")) item.textContent += " · Leído";
      }
    );
  });

  socket.on("socket_error", function (error) {
    if (error && error.mensaje) setStatus(error.mensaje, false);
  });

  if (form && textarea && submit) {
    form.addEventListener("submit", function (event) {
      if (!socket.connected) return;
      event.preventDefault();
      var text = textarea.value.trim();
      if (!text) return;
      submit.disabled = true;
      socket.emit(
        "send_message",
        { contacto_id: contactId, texto: text },
        function (response) {
          submit.disabled = false;
          if (response && response.ok) {
            textarea.value = "";
            textarea.focus();
          } else if (response && response.error) {
            setStatus(response.error.mensaje, false);
          }
        }
      );
    });
  }

  window.addEventListener("pagehide", function () {
    if (socket.connected) socket.emit("leave_room", { contacto_id: contactId });
  });
})();
