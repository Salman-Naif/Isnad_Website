/* Isnad — public page: verify a text, then ask the model about it. */

const API = "/api";
const MAX_HISTORY = 10; // must not exceed ChatRequest.history max_length

const $ = (id) => document.getElementById(id);

let lastQuery = ""; // the last verified text (or idea searched), sent to the chat as context
let mode = "verify"; // "verify" one text, or "explore" the hadiths about an idea

const MODES = {
  verify: { label: "تحقّق", placeholder: "اكتب الحديث أو الاقتباس هنا…", empty: "اكتب نصًا للتحقق منه" },
  explore: {
    label: "ابحث",
    placeholder: "اكتب فكرة أو موضوعًا، مثل: الصلاة أهم شيء، أو بر الوالدين…",
    empty: "اكتب فكرة أو موضوعًا للبحث عنه",
  },
};
let chatBusy = false; // one question at a time, so answers stay in order
const history = []; // chat turns: {role, content}

const VERDICT_ICONS = { verified: "check", found: "book", distorted: "alert", no_match: "x" };
const MATCH_TYPES = {
  exact: "تطابق حرفي",
  close: "تطابق شبه تام",
  reworded: "صياغة مختلفة",
  none: "لا تطابق",
};
const NO_RULING = "لا يتوفر حكم موثّق لهذا النص في المصادر المرفوعة";

// ---------- helpers ----------

function el(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined && text !== null) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function icon(name, cls = "icon") {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
  use.setAttribute("href", `#i-${name}`);
  svg.append(use);
  return svg;
}

async function post(path, body) {
  const res = await fetch(`${API}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (res.ok) return res.json();
  if (res.status === 429) throw new Error("طلبات كثيرة، انتظر دقيقة ثم حاول مرة أخرى");
  let detail = `حدث خطأ (${res.status})`;
  try {
    const data = await res.json();
    if (typeof data.detail === "string") detail = data.detail;
  } catch {}
  throw new Error(detail);
}

function setStatus(text, kind = "info") {
  const node = $("status");
  node.textContent = text;
  node.className = `alert ${kind}`;
  node.hidden = !text;
}

// ---------- verification ----------

function setMode(next) {
  mode = next;
  for (const button of document.querySelectorAll(".mode-switch .mode")) {
    button.setAttribute("aria-pressed", String(button.dataset.mode === next));
  }
  $("verify-label").textContent = MODES[next].label;
  $("query").placeholder = MODES[next].placeholder;
}

function submitSearch(event) {
  return mode === "explore" ? explore(event) : verify(event);
}

async function verify(event) {
  event.preventDefault();
  const query = $("query").value.trim();
  if (!query) {
    setStatus(MODES.verify.empty, "error");
    $("query").focus();
    return;
  }

  const button = $("verify-btn");
  button.disabled = true;
  button.classList.add("loading");
  setStatus("جارٍ البحث في المصادر…");

  try {
    const data = await post("/search", { query, top_k: 5 });
    lastQuery = query;
    renderSuggestions();
    $("explore").hidden = true;
    renderResult(data);
    setStatus("");
    $("result").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
  }
}

function renderResult(data) {
  $("result").hidden = false;
  const verdict = $("verdict");
  verdict.dataset.verdict = data.verdict;
  $("verdict-icon").replaceChildren(icon(VERDICT_ICONS[data.verdict] || "info"));
  $("verdict-text").textContent = data.verdict_message;

  const [best, ...others] = data.results;
  const showBest = Boolean(best) && data.verdict !== "no_match";
  $("best-match").hidden = !showBest;

  if (showBest) {
    $("matched-text").textContent = best.text;
    const percent = Math.round(best.similarity * 100);
    $("similarity-text").textContent = `${percent}%`;
    $("similarity-bar").style.width = "0";
    requestAnimationFrame(() => ($("similarity-bar").style.width = `${percent}%`));

    $("match-type").textContent = MATCH_TYPES[best.match_type] || "";
    $("match-type").dataset.type = best.match_type;
    $("word-overlap").textContent =
      best.word_overlap === null || best.word_overlap === undefined
        ? ""
        : `الألفاظ المشتركة ${Math.round(best.word_overlap * 100)}%`;

    renderShubha(best.words || []);

    // The ruling is always shown: its absence is information too.
    const details = $("details");
    details.replaceChildren();
    for (const [label, value, cls] of [
      ["الحكم", best.hukm || NO_RULING, best.hukm ? "ruling" : "ruling missing"],
      ["المحدّث", best.mohaddith],
      ["الموضوع", best.topic],
      ["المصدر", best.source],
      ["المصنّف", best.compiler],
    ]) {
      if (!value) continue;
      const item = el("div", undefined, cls);
      item.append(el("dt", label), el("dd", value));
      details.append(item);
    }

    renderIsnad(data);
  }

  const rest = showBest ? others : data.results;
  const list = $("other-list");
  list.replaceChildren();
  for (const item of rest) {
    const li = el("li");
    const meta = [`تشابه ${Math.round(item.similarity * 100)}%`, item.hukm, item.source].filter(Boolean);
    li.append(el("span", item.text, "other-text"), el("span", meta.join(" · "), "other-meta"));
    list.append(li);
  }
  $("other-matches").hidden = rest.length === 0;
}

// ---------- search by meaning ----------

async function explore(event) {
  event.preventDefault();
  const query = $("query").value.trim();
  if (!query) {
    setStatus(MODES.explore.empty, "error");
    $("query").focus();
    return;
  }

  const button = $("verify-btn");
  button.disabled = true;
  button.classList.add("loading");
  setStatus("جارٍ البحث عن الأحاديث في هذا المعنى…");

  try {
    const data = await post("/explore", { query, top_k: 10 });
    lastQuery = query;
    renderSuggestions();
    $("result").hidden = true;
    renderExplore(data);
    setStatus("");
    $("explore").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (err) {
    setStatus(err.message, "error");
  } finally {
    button.disabled = false;
    button.classList.remove("loading");
  }
}

function renderExplore(data) {
  $("explore").hidden = false;
  const count = data.results.length;
  $("explore-summary").textContent = count
    ? `${count === 1 ? "نص واحد" : count === 2 ? "نصّان" : `${count} نصوص`}، من الأقرب إلى معنى ما كتبت. الحكم منسوب لقائله كما ورد في المصدر.`
    : "لا توجد في المصادر المعتمدة نصوص قريبة من هذا المعنى. جرّب صياغة أخرى.";

  const list = $("explore-list");
  list.replaceChildren();
  for (const item of data.results) {
    const li = el("li", undefined, "explore-item");
    li.append(el("p", item.text, "explore-text"));

    const meta = el("div", undefined, "explore-meta");
    const ruling = item.hukm ? (item.mohaddith ? `${item.hukm} — ${item.mohaddith}` : item.hukm) : NO_RULING;
    meta.append(el("span", ruling, item.hukm ? "ruling-badge" : "ruling-badge missing"));
    for (const value of [item.source, item.topic]) if (value) meta.append(el("span", value, "muted"));
    meta.append(el("span", `قرب المعنى ${Math.round(item.similarity * 100)}%`, "muted"));
    li.append(meta);

    // The same text through verification: its match, ruling and isnad tree.
    const check = el("button", undefined, "btn ghost small");
    check.type = "button";
    check.append(icon("layers", "icon sm"), el("span", "تحقّق منه واعرض السند"));
    check.addEventListener("click", () => {
      $("query").value = item.text;
      $("query").dispatchEvent(new Event("input"));
      setMode("verify");
      $("search-form").requestSubmit();
    });
    li.append(check);
    list.append(li);
  }
}

// The visitor's text, with the words that are not in the source highlighted.
function renderShubha(words) {
  const box = $("shubha-text");
  box.replaceChildren();
  const changed = words.some((w) => w.changed);
  $("shubha-block").hidden = !changed;
  if (!changed) return;
  words.forEach((w, i) => {
    if (i) box.append(" ");
    box.append(w.changed ? el("mark", w.word) : w.word);
  });
}

// The isnad as a tree: the Prophet ﷺ at the top, a chain runs down to the compiler, and
// branches split side by side where the books' (or a «ح») chains part.
function chainList(node) {
  const list = el("ol", undefined, "chain");
  let current = node;
  while (current) {
    const li = el("li", undefined, "node");
    const box = el("span", undefined, "node-box");
    box.append(el("span", current.name, "name"));
    if (current.grade) box.append(el("span", current.grade, "grade"));
    li.append(box);
    list.append(li);
    const children = current.children || [];
    if (children.length > 1) {
      const fork = el("li", undefined, "fork");
      const branches = el("div", undefined, "branches");
      for (const child of children) branches.append(chainList(child));
      fork.append(branches);
      list.append(fork);
    }
    current = children.length === 1 ? children[0] : null;
  }
  return list;
}

function renderIsnad(data) {
  const tree = $("sanad-tree");
  tree.replaceChildren();
  $("sanad-block").hidden = !data.sanad_tree;
  if (!data.sanad_tree) return;
  tree.append(chainList(data.sanad_tree));
  // A tree wider than the screen scrolls in its box: start with its trunk in view.
  const overflow = tree.scrollWidth - tree.clientWidth;
  if (overflow > 0) tree.scrollLeft = getComputedStyle(tree).direction === "rtl" ? -overflow / 2 : overflow / 2;

  const notes = [];
  if (data.sanad_sources.length > 1) {
    notes.push(`أسانيد ${data.sanad_sources.join("، ")} مجتمعة؛ الراوي المشترك يظهر مرة واحدة.`);
  }
  if (data.sanad_extracted) notes.push("استُخرج السند آليًا من نص الرواية، وقد يحتاج إلى مراجعة.");
  $("sanad-note").textContent = notes.join(" ");
  $("sanad-note").hidden = !notes.length;
}

// ---------- chat ----------

// Ready questions: about the text just searched, or a start for a visitor who hasn't searched.
const SUGGESTIONS = {
  subject: ["من رواه؟", "ما حكمه؟ ومن حكم عليه؟", "ما معنى هذا الحديث؟", "هل ورد بلفظ آخر؟"],
  general: ["ما فضل الصدقة؟", "ما حكم ترك الصلاة؟", "ما جزاء بر الوالدين؟"],
};

function renderSuggestions() {
  const box = $("chat-suggestions");
  if (!box) return;
  box.replaceChildren();
  for (const question of lastQuery ? SUGGESTIONS.subject : SUGGESTIONS.general) {
    const chip = el("button", question, "chip");
    chip.type = "button";
    chip.addEventListener("click", () => {
      if (chatBusy) return;
      $("chat-input").value = question;
      $("chat-form").requestSubmit();
    });
    box.append(chip);
  }
}

function plain(text) {
  // The page shows text only (never HTML); drop Markdown emphasis the model may still add.
  return text.replace(/\*\*(.+?)\*\*/g, "$1").replace(/^#+\s*/gm, "");
}

function addMessage(role, text) {
  $("chat-empty")?.remove();
  const box = el("div", undefined, `msg ${role}`);
  box.append(el("p", plain(text)));
  $("chat-log").append(box);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return box;
}

// The passages the answer was written from, numbered as the answer cites them ([1], [2]…).
function addPassages(box, passages) {
  if (!passages.length) return;
  const details = el("details", undefined, "msg-passages");
  details.append(el("summary", `النصوص التي اعتمدت عليها الإجابة (${passages.length})`));
  const list = el("ol");
  for (const p of passages) {
    const li = el("li");
    li.value = p.number;
    li.append(el("span", p.text, "passage-text"));
    const ruling = p.hukm ? (p.mohaddith ? `${p.hukm} — ${p.mohaddith}` : p.hukm) : "";
    const meta = [p.source, ruling].filter(Boolean).join(" · ");
    if (meta) li.append(el("span", meta, "passage-meta"));
    list.append(li);
  }
  details.append(list);
  box.append(details);
}

// What the server's check of the answer found: a quotation not in the sources, a wrong citation…
function addWarnings(box, warnings) {
  if (!warnings.length) return;
  const list = el("ul", undefined, "msg-warnings");
  list.setAttribute("role", "note");
  for (const text of warnings) list.append(el("li", text));
  box.append(list);
}

// POST that reads the answer line by line as the model writes it.
async function streamChat(body, onEvent) {
  const res = await fetch(`${API}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    if (res.status === 429) throw new Error("طلبات كثيرة، انتظر دقيقة ثم حاول مرة أخرى");
    let detail = `حدث خطأ (${res.status})`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") detail = data.detail;
    } catch {}
    throw new Error(detail);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  for (;;) {
    const { value, done } = await reader.read();
    buffered += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffered.split("\n");
    buffered = lines.pop();
    for (const line of lines) if (line.trim()) onEvent(JSON.parse(line));
    if (done) break;
  }
}

async function ask(event) {
  event.preventDefault();
  const input = $("chat-input");
  const question = input.value.trim();
  if (!question || chatBusy) return;
  chatBusy = true;

  input.value = "";
  $("chat-btn").disabled = true;
  addMessage("user", question);
  const box = addMessage("assistant pending", "");
  const text = box.querySelector("p");
  let answer = "";
  let passages = [];
  let check = { warnings: [], refused: false };

  try {
    await streamChat(
      { question, context_query: lastQuery, history: history.slice(-MAX_HISTORY) },
      (e) => {
        if (e.type === "passages") passages = e.passages;
        else if (e.type === "check") check = e;
        else if (e.type === "delta") {
          answer += e.text;
          box.classList.remove("pending");
          text.textContent = plain(answer);
          $("chat-log").scrollTop = $("chat-log").scrollHeight;
        } else if (e.type === "error") throw new Error(e.detail);
      },
    );
    if (!answer) throw new Error("لم يُرجع النموذج إجابة، حاول مرة أخرى");
    addWarnings(box, check.warnings);
    // A refusal or referral rests on no passage: showing the retrieved ones would suggest it did.
    if (!check.refused) addPassages(box, passages);
    history.push({ role: "user", content: question }, { role: "assistant", content: answer });
  } catch (err) {
    // What arrived before a failure stays visible; the error says it is incomplete.
    if (!answer) box.remove();
    addMessage("error", err.message);
  } finally {
    box.classList.remove("pending");
    chatBusy = false;
    $("chat-btn").disabled = false;
    input.focus();
  }
}

// ---------- startup ----------

document.addEventListener("DOMContentLoaded", () => {
  const form = $("search-form");
  if (form) {
    form.addEventListener("submit", submitSearch);
    for (const button of document.querySelectorAll(".mode-switch .mode")) {
      button.addEventListener("click", () => {
        setMode(button.dataset.mode);
        $("query").focus();
      });
    }
    $("query").addEventListener("input", () => {
      $("query-count").textContent = `${$("query").value.length} / 2000`;
    });
    // Ctrl/Cmd + Enter searches from inside the text box
    $("query").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) form.requestSubmit();
    });
  }
  $("chat-form")?.addEventListener("submit", ask);
  renderSuggestions();
});
