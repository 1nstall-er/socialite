(() => {
  "use strict";
  document.querySelectorAll("[data-avatar-image], .avatar-con-foto img").forEach((image) => {
    const fallback = () => {
      image.hidden = true;
      if (!image.hasAttribute("data-avatar-image")) {
        const text = image.alt.replace(/^Foto de\s+/i, "") || image.parentElement.title || "UPC";
        image.parentElement.textContent = text.split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase();
      }
    };
    image.addEventListener("error", fallback, { once: true });
    if (image.complete && !image.naturalWidth) fallback();
  });
  document.querySelectorAll(".campus-picture > img").forEach((image) => {
    const fallback = () => { image.hidden = true; image.parentElement.classList.add("campus-unavailable"); };
    image.addEventListener("error", fallback, { once: true });
    if (image.complete && !image.naturalWidth) fallback();
  });
})();
