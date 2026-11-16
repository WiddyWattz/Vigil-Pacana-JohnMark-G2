// Small UI helpers only. All validation and permissions are enforced by Django on the server.
document.addEventListener("DOMContentLoaded", () => {
  // Toast messages: close button + auto-hide after 5 seconds.
  document.querySelectorAll(".toast").forEach((toast) => {
    const hide = () => { toast.classList.add("hide"); setTimeout(() => toast.remove(), 260); };
    toast.querySelector(".toast-close")?.addEventListener("click", hide);
    setTimeout(hide, 5000);
  });

  // Mobile sidebar toggle on dashboard pages.
  const toggle = document.querySelector("[data-sidebar-toggle]");
  const sidebar = document.querySelector(".sidebar");
  toggle?.addEventListener("click", () => {
    const open = sidebar.classList.toggle("open");
    toggle.setAttribute("aria-expanded", open);
  });

  // Profile photo: preview the chosen image before saving.
  const photoInput = document.querySelector("#id_profile_photo");
  const preview = document.querySelector("[data-photo-preview]");
  photoInput?.addEventListener("change", () => {
    const file = photoInput.files[0];
    if (!file || !preview) return;
    preview.innerHTML = "";
    const img = document.createElement("img");
    img.src = URL.createObjectURL(file);
    img.alt = "New profile photo preview";
    preview.appendChild(img);
  });
});
