const header = document.querySelector("[data-header]");
const menu = document.querySelector("[data-menu]");
const menuToggle = document.querySelector("[data-menu-toggle]");
const languageToggle = document.querySelector("[data-language]");
const copyToast = document.querySelector("[data-copy-toast]");
const translations = [...document.querySelectorAll("[data-en]")].map((element) => ({
  element,
  zh: element.textContent,
  en: element.dataset.en,
}));
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
  if (window.innerWidth > 780) closeMenu();
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
languageToggle?.addEventListener("click", () => {
  language = language === "zh" ? "en" : "zh";
  document.documentElement.lang = language === "zh" ? "zh-CN" : "en";
  translations.forEach(({ element, zh, en }) => {
    element.textContent = language === "zh" ? zh : en;
  });
  languageToggle.textContent = message("EN", "中文");
  languageToggle.setAttribute("aria-label", message("Switch to English", "切换为中文"));
  document.title = message(
    "Computer MCP — 让 ChatGPT，用上你的本机工具。",
    "Computer MCP — Let ChatGPT use your local tools.",
  );
  document
    .querySelector('meta[name="description"]')
    ?.setAttribute(
      "content",
      message(
        "连接 CLI、Codex、MCP 和 Skills，在 ChatGPT 对话里写代码、处理文件、运行你的 Mac 工具。按需接入，权限由你配置。",
        "Connect ChatGPT to your Mac's CLI tools, Codex, MCP servers and Skills. Write code, work with files and run your tools, with permissions you choose.",
      ),
    );
  window.clearTimeout(toastTimer);
  copyToast?.classList.remove("visible");
  updateCopyLabels();
});
updateCopyLabels();

const tabs = [...document.querySelectorAll("[data-tool]")];
const selectTool = (selected) => {
  tabs.forEach((tab) => {
    const active = tab === selected;
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    const panel = document.getElementById(tab.getAttribute("aria-controls"));
    if (panel) panel.hidden = !active;
  });
};
tabs.forEach((tab, index) => {
  tab.addEventListener("click", () => selectTool(tab));
  tab.addEventListener("keydown", (event) => {
    let next;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next !== undefined) {
      event.preventDefault();
      selectTool(tabs[next]);
      tabs[next].focus();
    }
  });
});

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
