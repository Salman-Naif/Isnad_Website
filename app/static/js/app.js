/* Isnad — public page: verify a text, then ask the model about it. In Arabic or English: the page
   is rendered in Arabic, and every [data-i18n] text follows the visitor's choice (STRINGS). */

const API = "/api";
const MAX_HISTORY = 10; // must not exceed ChatRequest.history max_length

const $ = (id) => document.getElementById(id);

let lastQuery = ""; // the last verified text (or idea searched), sent to the chat as context
let mode = "verify"; // "verify" one text, or "explore" the hadiths about an idea

let chatBusy = false; // one question at a time, so answers stay in order
const history = []; // chat turns: {role, content}

const VERDICT_ICONS = { verified: "check", found: "book", distorted: "alert", meaning: "book", no_match: "x" };

// ---------- language ----------

const STRINGS = {
  ar: {
    title: "إسناد — التحقق من الأحاديث والاقتباسات",
    brand_home: "إسناد — الصفحة الرئيسية",
    brand_name: "إسناد",
    brand_sub: "التحقق من الأحاديث والاقتباسات",
    hero_title: "تحقّق من حديث أو اقتباس",
    hero_sub: "اكتب النص بأي صياغة، ونطابقه دلاليًا مع المصادر المعتمدة، ونعرض الحكم منسوبًا لقائله مع السند.",
    mode_group: "نوع البحث",
    mode_verify: "تحقّق من نص",
    mode_explore: "ابحث بالمعنى",
    query_label: "النص المراد التحقق منه",
    verify_label: "تحقّق",
    verify_placeholder: "اكتب الحديث أو الاقتباس هنا… (بالعربية أو الإنجليزية)",
    verify_empty: "اكتب نصًا للتحقق منه",
    explore_label: "ابحث",
    explore_placeholder: "اكتب فكرة أو موضوعًا، مثل: الصلاة أهم شيء، أو بر الوالدين…",
    explore_empty: "اكتب فكرة أو موضوعًا للبحث عنه",
    searching: "جارٍ البحث في المصادر…",
    exploring: "جارٍ البحث عن الأحاديث في هذا المعنى…",
    search_off: "البحث متوقف مؤقتًا، يرجى المحاولة لاحقًا.",
    verdict_verified: "وُجد هذا النص في المصادر — حكمه موضّح أدناه",
    verdict_found: "النص موجود في المصادر، لكن لا يتوفر له حكم موثّق",
    verdict_distorted: "تنبيه: هذا يشبه نصًا معروفًا بصياغة مختلفة",
    verdict_meaning: "وُجد في المصادر حديث بهذا المعنى — هذا لفظه العربي من مصدره",
    verdict_no_match: "لا يوجد تطابق قوي في المصادر المعتمدة",
    searched_as: "كتبتَ بالإنجليزية، فبُحث في المصادر بهذا اللفظ العربي:",
    searched_as_note: "النص المعروض هو لفظ الحديث العربي من مصدره، وليس ترجمة.",
    similarity: "نسبة التشابه",
    match_exact: "تطابق حرفي",
    match_close: "تطابق شبه تام",
    match_reworded: "صياغة مختلفة",
    match_meaning: "بالمعنى",
    match_none: "لا تطابق",
    overlap: (n) => `الألفاظ المشتركة ${n}%`,
    shubha_title: "موضع الشبهة",
    shubha_note: "الكلمات المظلّلة في نصك لا ترد في النص الموثّق أعلاه.",
    ruling: "الحكم",
    scholar: "المحدّث",
    topic: "الموضوع",
    source: "المصدر",
    also_in: "ورد أيضًا في",
    compiler: "المصنّف",
    no_ruling: "لا يتوفر حكم موثّق لهذا النص في المصادر المرفوعة",
    sanad_title: "شجرة الإسناد",
    sanad_aria: "شجرة الإسناد من النبي ﷺ إلى مصنّف الكتاب",
    sanad_merged: (books) => `أسانيد ${books.join("، ")} مجتمعة؛ الراوي المشترك يظهر مرة واحدة.`,
    sanad_extracted: "استُخرج السند آليًا من نص الرواية، وقد يحتاج إلى مراجعة.",
    other_matches: "نصوص أخرى مشابهة",
    other_similarity: (n) => `تشابه ${n}%`,
    subject_searched: "ما كتبته عنوان لا نصّ حديث، فعُرضت الأحاديث في هذا المعنى.",
    explore_title: "أحاديث في هذا المعنى",
    explore_count: (n) => `${n === 1 ? "نص واحد" : n === 2 ? "نصّان" : `${n} نصوص`}، من الأقرب إلى معنى ما كتبت. الحكم منسوب لقائله كما ورد في المصدر.`,
    explore_none: "لا توجد في المصادر المعتمدة نصوص قريبة من هذا المعنى. جرّب صياغة أخرى.",
    closeness: (n) => `قرب المعنى ${n}%`,
    check_it: "تحقّق منه واعرض السند",
    chat_title: "اسأل عن حديث",
    chat_note: "مساعد آلي مدعوم بالذكاء الاصطناعي: يجيب من المصادر المعتمدة فقط، وينسب كل حكم لقائله، وقد يخطئ؛ فراجع النصوص المعروضة مع كل إجابة.",
    chat_empty: "ابحث عن نص أولًا ثم اسأل عنه، أو اكتب سؤالك مباشرة.",
    suggestions: "أسئلة مقترحة",
    chat_label: "سؤالك",
    chat_placeholder: "مثال: ما حكم هذا الحديث؟ ومن رواه؟",
    send: "إرسال",
    chat_off: "الحوار متوقف مؤقتًا، يرجى المحاولة لاحقًا.",
    suggest_subject: ["من رواه؟", "ما حكمه؟ ومن حكم عليه؟", "ما معنى هذا الحديث؟", "هل ورد بلفظ آخر؟"],
    suggest_general: ["ما فضل الصدقة؟", "ما حكم ترك الصلاة؟", "ما جزاء بر الوالدين؟"],
    passages: (n) => `النصوص التي اعتمدت عليها الإجابة (${n})`,
    too_many: "طلبات كثيرة، انتظر دقيقة ثم حاول مرة أخرى",
    error: (status) => `حدث خطأ (${status})`,
    no_answer: "لم يُرجع النموذج إجابة، حاول مرة أخرى",
    footer_rulings: "الأحكام منسوبة لقائليها من المحدّثين كما وردت في المصادر المعتمدة. «إسناد» أداة مدعومة بالذكاء الاصطناعي، وليست مفتيًا ولا بديلًا عن أهل العلم.",
    privacy: "الخصوصية",
    privacy_text: "لا نطلب اسمًا ولا بريدًا ولا نحفظ عنوان جهازك. نحفظ نص البحث والسؤال، ومعرّفًا عشوائيًا مجهولًا من ملف تعريف (cookie) لا يُخزَّن إلا بعد تجزئته (hash)، لإحصاءات الاستخدام فقط. يُرسل نص البحث والسؤال إلى OpenRouter لمعالجته بنماذج الذكاء الاصطناعي، فلا تكتب فيه بيانات شخصية.",
    footer_team: "مشروع فريق إسناد (Isnad) المشارك في تحدي الذكاء الاصطناعي في خدمة المحتوى الإسلامي.",
    footer_copyright: "© فريق إسناد (Isnad)",
    switch_label: "English",
    switch_aria: "Switch to English",
  },
  en: {
    title: "Isnad — Verify hadiths and quotes",
    brand_home: "Isnad — home",
    brand_name: "Isnad",
    brand_sub: "Verify hadiths and quotes",
    hero_title: "Verify a hadith or a quote",
    hero_sub: "Write the text in any wording, in Arabic or English. We match it by meaning against the approved sources and show the ruling, attributed to the scholar who gave it, with the chain of narration.",
    mode_group: "Search type",
    mode_verify: "Verify a text",
    mode_explore: "Search by meaning",
    query_label: "The text to verify",
    verify_label: "Verify",
    verify_placeholder: "Write the hadith or quote here… (English or Arabic)",
    verify_empty: "Write a text to verify",
    explore_label: "Search",
    explore_placeholder: "Write an idea or a topic, e.g. kindness to parents, or the reward of charity…",
    explore_empty: "Write an idea or a topic to search for",
    searching: "Searching the sources…",
    exploring: "Looking for hadiths with this meaning…",
    search_off: "Search is paused for now, please try again later.",
    verdict_verified: "This text is in the sources — its ruling is shown below",
    verdict_found: "This text is in the sources, but no documented ruling is available for it",
    verdict_distorted: "Caution: this resembles a known hadith, with a different wording or meaning",
    verdict_meaning: "A hadith with this meaning is in the sources — shown in its Arabic words, from its source",
    verdict_no_match: "No hadith with this meaning was found in the approved sources",
    searched_as: "Your text was searched in the sources as this Arabic wording:",
    searched_as_note: "The text shown is the hadith's Arabic wording from its source, not a translation.",
    similarity: "Similarity",
    match_exact: "Word for word",
    match_close: "Nearly word for word",
    match_reworded: "Different wording",
    match_meaning: "Same meaning",
    match_none: "No match",
    overlap: (n) => `Shared words ${n}%`,
    shubha_title: "Where it differs",
    shubha_note: "The highlighted words of your text are not in the verified text above.",
    ruling: "Ruling",
    scholar: "Scholar",
    topic: "Chapter",
    source: "Source",
    also_in: "Also in",
    compiler: "Compiler",
    no_ruling: "No documented ruling for this text in the uploaded sources",
    sanad_title: "Chain of narration (isnad)",
    sanad_aria: "The chain of narration, from the Prophet ﷺ to the compiler of the book",
    sanad_merged: (books) => `The chains of ${books.join(", ")} together; a narrator they share appears once.`,
    sanad_extracted: "This chain was read automatically from the narration's wording and may need review.",
    other_matches: "Other similar texts",
    other_similarity: (n) => `Similarity ${n}%`,
    subject_searched: "What you wrote is a subject, not the words of a hadith, so the hadiths about it are shown.",
    explore_title: "Hadiths with this meaning",
    explore_count: (n) => `${n === 1 ? "One text" : `${n} texts`}, closest to what you wrote first. Each ruling is attributed to its scholar as the source records it.`,
    explore_none: "The approved sources hold no texts close to this meaning. Try another wording.",
    closeness: (n) => `Closeness ${n}%`,
    check_it: "Verify it and show its chain",
    chat_title: "Ask about a hadith",
    chat_note: "An AI assistant: it answers from the approved sources only, attributes every ruling to its scholar, and can make mistakes — check the texts shown with each answer. Hadiths are quoted in their Arabic words; an English meaning is an explanation, not a translation.",
    chat_empty: "Search for a text first and then ask about it, or ask your question directly.",
    suggestions: "Suggested questions",
    chat_label: "Your question",
    chat_placeholder: "e.g. Who narrated this hadith? What is its ruling?",
    send: "Send",
    chat_off: "Chat is paused for now, please try again later.",
    suggest_subject: ["Who narrated it?", "What is its ruling, and who gave it?", "What does this hadith mean?", "Is it narrated in other words?"],
    suggest_general: ["What is the virtue of charity?", "What is said about leaving the prayer?", "What is the reward of kindness to parents?"],
    passages: (n) => `The texts this answer rests on (${n})`,
    too_many: "Too many requests — wait a minute and try again",
    error: (status) => `Something went wrong (${status})`,
    no_answer: "The model returned no answer, please try again",
    footer_rulings: "Rulings are attributed to the hadith scholars who gave them, as the approved sources record them. Isnad is an AI-supported tool, not a mufti, and no substitute for scholars.",
    privacy: "Privacy",
    privacy_text: "We ask for no name or email and keep no device address. We keep the text of searches and questions, and an anonymous random cookie id stored only as a hash, for usage statistics. Searches and questions are sent to OpenRouter to be processed by AI models (an English text is also rendered in Arabic by the chat model to search the sources), so do not write personal data in them.",
    footer_team: "A project of the Isnad team (فريق إسناد) in the AI Challenge in Serving Islamic Content.",
    footer_copyright: "© Isnad team (فريق إسناد)",
    switch_label: "العربية",
    switch_aria: "التبديل إلى العربية",
  },
};

let lang = "ar";
let shown = null; // the result on the page, redrawn in the other language: {kind, data}

function t(key, ...args) {
  const value = STRINGS[lang][key] ?? STRINGS.ar[key];
  return typeof value === "function" ? value(...args) : value;
}

function savedLanguage() {
  const asked = new URLSearchParams(location.search).get("lang");
  if (asked === "en" || asked === "ar") return asked;
  try {
    const kept = localStorage.getItem("isnad_lang");
    if (kept === "en" || kept === "ar") return kept;
  } catch {}
  return "ar";
}

function applyLanguage(next) {
  lang = next;
  document.documentElement.lang = next;
  document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
  document.title = t("title");
  for (const node of document.querySelectorAll("[data-i18n]")) node.textContent = t(node.dataset.i18n);
  for (const node of document.querySelectorAll("[data-i18n-placeholder]")) node.placeholder = t(node.dataset.i18nPlaceholder);
  for (const node of document.querySelectorAll("[data-i18n-aria]")) node.setAttribute("aria-label", t(node.dataset.i18nAria));
  const toggle = $("lang-toggle");
  toggle.textContent = t("switch_label");
  toggle.lang = next === "ar" ? "en" : "ar";
  toggle.setAttribute("aria-label", t("switch_aria"));
  if ($("search-form")) setMode(mode);
  renderSuggestions();
  if (shown?.kind === "verify") renderResult(shown.data);
  if (shown?.kind === "explore") renderExplore(shown.data);
  try {
    localStorage.setItem("isnad_lang", next);
  } catch {}
}

// Arabic text from the sources keeps its direction inside an English page.
function arabic(node) {
  node.lang = "ar";
  node.dir = "rtl";
  return node;
}

// For an English text: the Arabic it was searched with, and that what is shown is not a translation.
function renderSearchedAs(node, searchedAs, showsSources) {
  node.replaceChildren();
  node.hidden = !searchedAs;
  if (!searchedAs) return;
  node.append(el("span", t("searched_as")), arabic(el("q", searchedAs)));
  if (showsSources) node.append(el("span", t("searched_as_note"), "muted"));
}

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
  if (res.status === 429) throw new Error(t("too_many"));
  let detail = t("error", res.status);
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

// A few words naming a subject, not a text to verify (the database ranks it by its words too).
const SUBJECT_MAX_WORDS = 6;

function isSubject(query) {
  const words = query.split(/\s+/).filter(Boolean);
  return words.length > 0 && words.length <= SUBJECT_MAX_WORDS;
}

// ---------- verification ----------

function setMode(next) {
  mode = next;
  for (const button of document.querySelectorAll(".mode-switch .mode")) {
    button.setAttribute("aria-pressed", String(button.dataset.mode === next));
  }
  $("verify-label").textContent = t(`${next}_label`);
  $("query").placeholder = t(`${next}_placeholder`);
}

function submitSearch(event) {
  return mode === "explore" ? explore(event) : verify(event);
}

async function verify(event) {
  event.preventDefault();
  const query = $("query").value.trim();
  if (!query) {
    setStatus(t("verify_empty"), "error");
    $("query").focus();
    return;
  }

  const button = $("verify-btn");
  button.disabled = true;
  button.classList.add("loading");
  setStatus(t("searching"));

  try {
    const data = await post("/search", { query, top_k: 5 });
    lastQuery = query;
    renderSuggestions();
    // A subject («فضل الأم», «بر الوالدين») is not a text to verify: when nothing matches it as a
    // text, the hadiths about it are shown instead of an empty verdict.
    if (data.verdict === "no_match" && isSubject(query)) {
      $("result").hidden = true;
      renderExplore(await post("/explore", { query, top_k: 10 }));
      setStatus(t("subject_searched"));
      $("explore").scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
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
  shown = { kind: "verify", data };
  $("result").hidden = false;
  const verdict = $("verdict");
  verdict.dataset.verdict = data.verdict;
  $("verdict-icon").replaceChildren(icon(VERDICT_ICONS[data.verdict] || "info"));
  $("verdict-text").textContent = t(`verdict_${data.verdict}`) || data.verdict_message;
  renderSearchedAs($("searched-as"), data.searched_as, data.verdict !== "no_match");

  const [best, ...others] = data.results;
  const showBest = Boolean(best) && data.verdict !== "no_match";
  $("best-match").hidden = !showBest;

  if (showBest) {
    $("matched-text").textContent = best.text;
    const percent = Math.round(best.similarity * 100);
    $("similarity-text").textContent = `${percent}%`;
    $("similarity-bar").style.width = "0";
    requestAnimationFrame(() => ($("similarity-bar").style.width = `${percent}%`));

    $("match-type").textContent = t(`match_${best.match_type}`) || "";
    $("match-type").dataset.type = best.match_type;
    $("word-overlap").textContent =
      best.word_overlap === null || best.word_overlap === undefined
        ? ""
        : data.language === "en"
          ? "" // the visitor's words and the hadith's are in two languages
          : t("overlap", Math.round(best.word_overlap * 100));

    renderShubha(best.words || []);

    // The ruling is always shown: its absence is information too.
    const details = $("details");
    details.replaceChildren();
    for (const [label, value, cls] of [
      [t("ruling"), best.hukm, best.hukm ? "ruling" : "ruling missing"],
      [t("scholar"), best.mohaddith],
      [t("topic"), best.topic],
      [t("source"), best.source],
      [t("also_in"), alsoIn(best)],
      [t("compiler"), best.compiler],
    ]) {
      if (!value && cls !== "ruling missing") continue;
      const item = el("div", undefined, cls);
      item.append(el("dt", label), value ? arabic(el("dd", value)) : el("dd", t("no_ruling")));
      details.append(item);
    }

    renderIsnad(data);
  }

  const rest = showBest ? others : data.results;
  const list = $("other-list");
  list.replaceChildren();
  for (const item of rest) {
    const li = el("li");
    const meta = [t("other_similarity", Math.round(item.similarity * 100)), item.hukm, item.source, alsoIn(item, true)].filter(Boolean);
    li.append(arabic(el("span", item.text, "other-text")), el("span", meta.join(" · "), "other-meta"));
    list.append(li);
  }
  $("other-matches").hidden = rest.length === 0;
}

// The other books the same hadith is in: it is shown once (app/services/grouping.py).
function alsoIn(item, labelled = false) {
  const books = (item.also_in || []).join("، ");
  return books && labelled ? `${t("also_in")}: ${books}` : books;
}

// ---------- search by meaning ----------

async function explore(event) {
  event.preventDefault();
  const query = $("query").value.trim();
  if (!query) {
    setStatus(t("explore_empty"), "error");
    $("query").focus();
    return;
  }

  const button = $("verify-btn");
  button.disabled = true;
  button.classList.add("loading");
  setStatus(t("exploring"));

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
  shown = { kind: "explore", data };
  $("explore").hidden = false;
  const count = data.results.length;
  $("explore-summary").textContent = count ? t("explore_count", count) : t("explore_none");
  renderSearchedAs($("explore-searched-as"), data.searched_as, count > 0);

  const list = $("explore-list");
  list.replaceChildren();
  for (const item of data.results) {
    const li = el("li", undefined, "explore-item");
    li.append(arabic(el("p", item.text, "explore-text")));

    const meta = el("div", undefined, "explore-meta");
    const ruling = item.hukm ? (item.mohaddith ? `${item.hukm} — ${item.mohaddith}` : item.hukm) : t("no_ruling");
    const badge = el("span", ruling, item.hukm ? "ruling-badge" : "ruling-badge missing");
    meta.append(item.hukm ? arabic(badge) : badge);
    for (const value of [item.source, alsoIn(item, true), item.topic]) if (value) meta.append(arabic(el("span", value, "muted")));
    meta.append(el("span", t("closeness", Math.round(item.similarity * 100)), "muted"));
    li.append(meta);

    // The same text through verification: its match, ruling and isnad tree.
    const check = el("button", undefined, "btn ghost small");
    check.type = "button";
    check.append(icon("layers", "icon sm"), el("span", t("check_it")));
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
  if (data.sanad_sources.length > 1) notes.push(t("sanad_merged", data.sanad_sources));
  if (data.sanad_extracted) notes.push(t("sanad_extracted"));
  $("sanad-note").textContent = notes.join(" ");
  $("sanad-note").hidden = !notes.length;
}

// ---------- chat ----------

// Ready questions: about the text just searched, or a start for a visitor who hasn't searched.
function renderSuggestions() {
  const box = $("chat-suggestions");
  if (!box) return;
  box.replaceChildren();
  for (const question of lastQuery ? t("suggest_subject") : t("suggest_general")) {
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
  const p = el("p", plain(text));
  p.dir = "auto"; // an English answer quotes the hadith in Arabic: each paragraph finds its direction
  box.append(p);
  $("chat-log").append(box);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
  return box;
}

// The passages the answer was written from, numbered as the answer cites them ([1], [2]…).
function addPassages(box, passages) {
  if (!passages.length) return;
  const details = el("details", undefined, "msg-passages");
  details.append(el("summary", t("passages", passages.length)));
  const list = el("ol");
  for (const p of passages) {
    const li = el("li");
    li.value = p.number;
    li.append(arabic(el("span", p.text, "passage-text")));
    const ruling = p.hukm ? (p.mohaddith ? `${p.hukm} — ${p.mohaddith}` : p.hukm) : "";
    const meta = [p.source, ruling].filter(Boolean).join(" · ");
    if (meta) li.append(arabic(el("span", meta, "passage-meta")));
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
  for (const text of warnings) {
    const item = el("li", text);
    item.dir = "auto";
    list.append(item);
  }
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
    if (res.status === 429) throw new Error(t("too_many"));
    let detail = t("error", res.status);
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
    if (!answer) throw new Error(t("no_answer"));
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
  $("lang-toggle").addEventListener("click", () => applyLanguage(lang === "ar" ? "en" : "ar"));
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
  applyLanguage(savedLanguage());
});
