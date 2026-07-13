const fs = require("fs");
const vm = require("vm");

const source = fs.readFileSync("anti_bot.js", "utf8");
const html = fs.readFileSync("anti_bot_page.html", "utf8");
const scriptStartToken = "<script type=\"text/javascript\" r='m'>";
const scriptStart = html.indexOf(scriptStartToken);
const scriptEnd = scriptStart >= 0 ? html.indexOf("</script>", scriptStart) : -1;
const inlineBootstrap =
  scriptStart >= 0 && scriptEnd >= 0
    ? html.slice(scriptStart + scriptStartToken.length, scriptEnd)
    : "";

const logs = [];
const created = [];
const windowEvents = {};
const evalSources = [];

function record(type, payload) {
  logs.push({ type, payload });
}

const fakeLocation = {
  href: "https://www.nmpa.gov.cn/datasearch/home-index.html#category=hzp",
  protocol: "https:",
  host: "www.nmpa.gov.cn",
  hostname: "www.nmpa.gov.cn",
  pathname: "/datasearch/home-index.html",
  search: "",
  hash: "#category=hzp",
  assign(value) {
    record("location.assign", value);
    this.href = value;
  },
  replace(value) {
    record("location.replace", value);
    this.href = value;
  },
  reload() {
    record("location.reload", true);
  },
  toString() {
    return this.href;
  },
};

const fakeDocument = {
  readyState: "complete",
  body: {
    appendChild(node) {
      created.push({ action: "body.appendChild", node });
      return node;
    },
    removeChild(node) {
      created.push({ action: "body.removeChild", node });
      return node;
    },
  },
  head: {
    appendChild(node) {
      created.push({ action: "head.appendChild", node });
      return node;
    },
  },
  documentElement: {
    clientWidth: 1366,
    clientHeight: 900,
  },
  currentScript: null,
  cookie: "",
  createElement(tag) {
    const node = {
      tagName: String(tag).toUpperCase(),
      style: {},
      children: [],
      attributes: {},
      parentNode: null,
      appendChild(child) {
        this.children.push(child);
        child.parentNode = this;
        created.push({ action: "appendChild", tag, childTag: child.tagName || typeof child });
        return child;
      },
      remove() {
        created.push({ action: "remove", tag });
      },
      setAttribute(name, value) {
        this.attributes[name] = value;
        record("setAttribute", { tag, name, value });
      },
      getAttribute(name) {
        return this.attributes[name];
      },
      addEventListener(name) {
        record("element.addEventListener", { tag, name });
      },
      removeEventListener(name) {
        record("element.removeEventListener", { tag, name });
      },
      submit() {
        record("form.submit", { tag, attributes: this.attributes, children: this.children });
      },
      click() {
        record("element.click", { tag, attributes: this.attributes });
      },
      cloneNode() {
        return this;
      },
    };
    created.push({ action: "createElement", tag });
    return node;
  },
  getElementById(id) {
    record("getElementById", id);
    return null;
  },
  getElementsByTagName(tag) {
    record("getElementsByTagName", tag);
    return [];
  },
  querySelector(selector) {
    record("querySelector", selector);
    return null;
  },
  querySelectorAll(selector) {
    record("querySelectorAll", selector);
    return [];
  },
  addEventListener(name) {
    record("document.addEventListener", name);
  },
  removeEventListener(name) {
    record("document.removeEventListener", name);
  },
  attachEvent(name) {
    record("document.attachEvent", name);
  },
  detachEvent(name) {
    record("document.detachEvent", name);
  },
};

const fakeNavigator = {
  userAgent:
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/137.0.0.0 Safari/537.36",
  language: "zh-CN",
  languages: ["zh-CN", "zh"],
  platform: "MacIntel",
  cookieEnabled: true,
};

const context = {
  window: null,
  document: fakeDocument,
  location: fakeLocation,
  navigator: fakeNavigator,
  history: {
    replaceState(...args) {
      record("history.replaceState", args);
    },
  },
  addEventListener(name, fn) {
    record("window.addEventListener", name);
    windowEvents[name] = fn;
  },
  removeEventListener(name) {
    record("window.removeEventListener", name);
    delete windowEvents[name];
  },
  attachEvent(name, fn) {
    record("window.attachEvent", name);
    windowEvents[name] = fn;
  },
  detachEvent(name) {
    record("window.detachEvent", name);
    delete windowEvents[name];
  },
  screen: { width: 1440, height: 900 },
  innerWidth: 1366,
  innerHeight: 900,
  devicePixelRatio: 2,
  localStorage: {
    getItem(key) {
      record("localStorage.getItem", key);
      return null;
    },
    setItem(key, value) {
      record("localStorage.setItem", { key, value });
    },
    removeItem(key) {
      record("localStorage.removeItem", key);
    },
  },
  sessionStorage: {
    getItem(key) {
      record("sessionStorage.getItem", key);
      return null;
    },
    setItem(key, value) {
      record("sessionStorage.setItem", { key, value });
    },
    removeItem(key) {
      record("sessionStorage.removeItem", key);
    },
  },
  console: {
    log: (...args) => record("console.log", args),
    clear: () => record("console.clear", true),
    warn: (...args) => record("console.warn", args),
    error: (...args) => record("console.error", args),
  },
  setTimeout(fn, delay, ...args) {
    record("setTimeout", { delay });
    if (typeof fn === "function") {
      try {
        return fn(...args);
      } catch (error) {
        record("setTimeout.error", String(error));
      }
    }
    return 0;
  },
  clearTimeout() {},
  setInterval(fn, delay, ...args) {
    record("setInterval", { delay });
    if (typeof fn === "function") {
      try {
        return fn(...args);
      } catch (error) {
        record("setInterval.error", String(error));
      }
    }
    return 0;
  },
  clearInterval() {},
  performance: { now: () => 12345 },
  Image: function Image() {
    return fakeDocument.createElement("img");
  },
  MouseEvent: function MouseEvent(type, init = {}) {
    return { type, ...init };
  },
  Event: function Event(type, init = {}) {
    return { type, ...init };
  },
  XMLHttpRequest: function XMLHttpRequest() {
    this.headers = {};
    this.open = (...args) => record("xhr.open", args);
    this.setRequestHeader = (name, value) => {
      this.headers[name] = value;
      record("xhr.setRequestHeader", { name, value });
    };
    this.send = (body) => record("xhr.send", body);
    this.abort = () => record("xhr.abort", true);
  },
  fetch: (...args) => {
    record("fetch", args);
    return Promise.resolve({
      ok: false,
      status: 400,
      text: async () => "",
      json: async () => ({}),
    });
  },
  atob: (value) => Buffer.from(value, "base64").toString("binary"),
  btoa: (value) => Buffer.from(value, "binary").toString("base64"),
  getComputedStyle() {
    return {
      display: "block",
      visibility: "visible",
      opacity: "1",
    };
  },
};

context.window = context;
context.self = context;
context.top = context;
context.parent = context;
context.globalThis = context;
context.eval = function interceptedEval(code) {
  const text = typeof code === "string" ? code : String(code);
  evalSources.push(text);
  record("eval", { length: text.length, preview: text.slice(0, 200) });
  return vm.runInContext(text, context, { timeout: 5000, filename: "anti_bot_eval.js" });
};
context.Function = function interceptedFunction(...args) {
  const body = args.length ? String(args[args.length - 1]) : "";
  evalSources.push(`Function(${args.map((item) => JSON.stringify(String(item))).join(",")})`);
  record("Function", { argc: args.length, bodyPreview: body.slice(0, 200) });
  return Function(...args);
};

vm.createContext(context);

try {
  if (inlineBootstrap) {
    vm.runInContext(inlineBootstrap, context, { timeout: 5000, filename: "anti_bot_inline.js" });
  }
  vm.runInContext(source, context, { timeout: 5000, filename: "anti_bot.js" });
  if (typeof context._$_4 === "function") {
    record("invoke", "_$_4");
    context._$_4();
  }
  if (typeof context._$dI === "function") {
    record("invoke", "_$dI");
    context._$dI();
  }
} catch (error) {
  record("runtime.error", { message: String(error), stack: error && error.stack });
}

fs.writeFileSync(
  "output/deob_probe_output.json",
  JSON.stringify(
    {
      location: fakeLocation,
      cookie: fakeDocument.cookie,
      created,
      logs,
      eval_source_lengths: evalSources.map((item) => item.length),
      globals: Object.keys(context).filter((key) => key.startsWith("_$") || key.startsWith("$_")).slice(0, 100),
    },
    null,
    2
  )
);

if (evalSources.length) {
  fs.writeFileSync("output/deob_eval_0.js", evalSources[0]);
}
if (evalSources.length > 1) {
  fs.writeFileSync("output/deob_eval_1.js", evalSources[1]);
}

console.log("wrote output/deob_probe_output.json");
