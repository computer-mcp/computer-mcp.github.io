const header = document.querySelector("[data-header]");
const menu = document.querySelector("[data-menu]");
const menuToggle = document.querySelector("[data-menu-toggle]");
const copyToast = document.querySelector("[data-copy-toast]");

const closeMenu = () => {
  if (!(menu instanceof HTMLElement) || !(menuToggle instanceof HTMLButtonElement)) {
    return;
  }

  menu.classList.remove("open");
  menuToggle.setAttribute("aria-expanded", "false");
};

if (menu instanceof HTMLElement && menuToggle instanceof HTMLButtonElement) {
  menuToggle.addEventListener("click", () => {
    const nextExpanded = menuToggle.getAttribute("aria-expanded") !== "true";
    menu.classList.toggle("open", nextExpanded);
    menuToggle.setAttribute("aria-expanded", String(nextExpanded));
  });

  menu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", closeMenu);
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 780) {
      closeMenu();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeMenu();
      menuToggle.focus();
    }
  });
}

const updateHeader = () => {
  header?.classList.toggle("scrolled", window.scrollY > 12);
};

updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

let toastTimer;

document.querySelectorAll("[data-copy]").forEach((control) => {
  if (!(control instanceof HTMLButtonElement)) {
    return;
  }

  const defaultLabel = control.textContent?.trim() || "Copy";
  control.setAttribute("aria-label", `Copy ${control.dataset.copy ?? "command"}`);

  control.addEventListener("click", async () => {
    const value = control.dataset.copy;
    if (!value) {
      return;
    }

    try {
      await navigator.clipboard.writeText(value);
      control.textContent = "Copied";
      if (copyToast instanceof HTMLElement) {
        copyToast.classList.add("visible");
      }
      window.clearTimeout(toastTimer);
      toastTimer = window.setTimeout(() => {
        control.textContent = defaultLabel;
        copyToast?.classList.remove("visible");
      }, 1600);
    } catch {
      control.textContent = "Select text";
      window.clearTimeout(toastTimer);
      toastTimer = window.setTimeout(() => {
        control.textContent = defaultLabel;
      }, 1600);
    }
  });
});
