const header = document.querySelector("[data-header]");
const menu = document.querySelector("[data-menu]");
const menuToggle = document.querySelector("[data-menu-toggle]");
const languageToggle = document.querySelector("[data-language]");
const copyToast = document.querySelector("[data-copy-toast]");
const storageKey = "computer-mcp-language";
const translations = [
  ["data-en", null],
  ["data-en-href", "href"],
  ["data-en-content", "content"],
].flatMap(([source, target]) =>
  [...document.querySelectorAll(`[${source}]`)].map((element) => {
    const zh = target ? element.getAttribute(target) : element.textContent;
    const en = element.getAttribute(source);
    return (english) => {
      const value = english ? en : zh;
      if (target) element.setAttribute(target, value);
      else element.textContent = value;
    };
  }),
);
let language = "zh";
let toastTimer;
const message = (zh, en) => (language === "zh" ? zh : en);

const closeMenu = () => {
  menu?.classList.remove("open");
  menuToggle?.setAttribute("aria-expanded", "false");
};

menuToggle?.addEventListener("click", () => {
  const expanded = menuToggle.getAttribute("aria-expanded") !== "true";
  menu?.classList.toggle("open", expanded);
  menuToggle.setAttribute("aria-expanded", String(expanded));
});
menu?.querySelectorAll("a").forEach((link) => link.addEventListener("click", closeMenu));
window.addEventListener("resize", () => {
  if (window.innerWidth > 900) closeMenu();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && menuToggle?.getAttribute("aria-expanded") === "true") {
    closeMenu();
    menuToggle.focus();
  }
});
const updateHeader = () => header?.classList.toggle("scrolled", window.scrollY > 12);
updateHeader();
window.addEventListener("scroll", updateHeader, { passive: true });

const updateCopyLabels = () => {
  document.querySelectorAll("[data-copy]").forEach((control) => {
    control.setAttribute("aria-label", message("复制 ", "Copy ") + control.dataset.copy);
  });
};

const setLanguage = (next) => {
  language = next;
  const english = language === "en";
  document.documentElement.lang = english ? "en" : "zh-CN";
  translations.forEach((apply) => apply(english));
  if (languageToggle) {
    languageToggle.textContent = message("EN", "中文");
    languageToggle.lang = english ? "zh-CN" : "en";
    languageToggle.setAttribute("aria-label", message("Switch to English", "切换为中文"));
  }
  window.clearTimeout(toastTimer);
  copyToast?.classList.remove("visible");
  updateCopyLabels();
};

const storedLanguage = () => {
  const requested = new URLSearchParams(window.location.search).get("lang");
  if (requested === "en" || requested === "zh-CN") return requested === "en" ? "en" : "zh";
  try {
    return window.localStorage.getItem(storageKey) === "en" ? "en" : "zh";
  } catch {
    return "zh";
  }
};

languageToggle?.addEventListener("click", () => {
  setLanguage(language === "zh" ? "en" : "zh");
  try {
    window.localStorage.setItem(storageKey, language);
  } catch {
    // The choice still applies to this page when storage is unavailable.
  }
});
if (storedLanguage() === "en") setLanguage("en");
updateCopyLabels();

const selectCommandText = (control) => {
  const command = control.parentElement?.querySelector("code");
  const selection = window.getSelection();
  if (!(command instanceof HTMLElement) || !selection) return false;
  const range = document.createRange();
  range.selectNodeContents(command);
  selection.removeAllRanges();
  selection.addRange(range);
  return selection.toString() === command.textContent;
};
document.querySelectorAll("[data-copy]").forEach((control) => {
  control.addEventListener("click", async () => {
    const value = control.dataset.copy;
    if (!value) return;
    let status;
    try {
      await navigator.clipboard.writeText(value);
      control.textContent = message("已复制", "Copied");
      status = message("已复制", "Copied");
    } catch {
      const selected = selectCommandText(control);
      control.textContent = selected
        ? message("已选中文本", "Text selected")
        : message("无法复制", "Copy unavailable");
      status = selected
        ? message("剪贴板不可用，已选中命令。", "Clipboard unavailable. Command selected.")
        : message("剪贴板不可用。", "Clipboard unavailable.");
    }
    if (copyToast) {
      copyToast.textContent = status;
      copyToast.classList.add("visible");
    }
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => {
      control.textContent = message("复制", "Copy");
      copyToast?.classList.remove("visible");
    }, 1800);
  });
});
