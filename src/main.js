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

const showCopyStatus = (message) => {
  if (!(copyToast instanceof HTMLElement)) {
    return;
  }

  copyToast.textContent = message;
  copyToast.classList.add("visible");
};

const selectCommandText = (control) => {
  const command = control.parentElement?.querySelector("code");
  const selection = window.getSelection();
  if (!(command instanceof HTMLElement) || !selection) {
    return false;
  }

  const range = document.createRange();
  range.selectNodeContents(command);
  selection.removeAllRanges();
  selection.addRange(range);
  return selection.toString() === command.textContent;
};

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
      showCopyStatus("Copied");
      window.clearTimeout(toastTimer);
      toastTimer = window.setTimeout(() => {
        control.textContent = defaultLabel;
        copyToast?.classList.remove("visible");
      }, 1600);
    } catch {
      const selected = selectCommandText(control);
      control.textContent = selected ? "Text selected" : "Copy unavailable";
      showCopyStatus(
        selected ? "Clipboard unavailable. Command selected." : "Clipboard unavailable.",
      );
      window.clearTimeout(toastTimer);
      toastTimer = window.setTimeout(() => {
        control.textContent = defaultLabel;
        copyToast?.classList.remove("visible");
      }, 1600);
    }
  });
});
