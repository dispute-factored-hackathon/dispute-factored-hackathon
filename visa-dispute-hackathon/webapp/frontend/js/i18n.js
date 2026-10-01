const DEFAULT_LOCALE = "en-US";
const CUSTOMER_LOCALE_KEY = "factored_locale";
const LOCALE_RESOURCE_VERSION = "v1";
const TRANSLATABLE_ATTRIBUTES = ["aria-label", "placeholder", "title"];

let currentLocale = DEFAULT_LOCALE;
let englishMessages = {};
let messages = {};
let sourceIndex = new Map();
let observer = null;
const textNodeKeys = new WeakMap();
const attributeKeys = new WeakMap();

export const i18nMetrics = {
    fallbackCount: 0,
    missingKeyCount: 0,
};

function languageFor(locale) {
    const language = String(locale || "").toLowerCase().split("-")[0];
    return ["en", "pt", "es"].includes(language) ? language : "en";
}

export function normalizeLocale(locale) {
    const value = String(locale || "").trim();
    const language = languageFor(value);
    if (language === "pt") return "pt-BR";
    if (language === "es") {
        const supported = ["es-AR", "es-CO", "es-MX", "es-419"];
        return supported.includes(value) ? value : "es-419";
    }
    return DEFAULT_LOCALE;
}

async function loadMessages(locale) {
    const language = languageFor(locale);
    const response = await fetch(
        `/static/locales/${LOCALE_RESOURCE_VERSION}/${language}.json`,
        { headers: { Accept: "application/json" } },
    );
    if (!response.ok) throw new Error(`Unable to load locale ${language}.`);
    return response.json();
}

function compact(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
}

function indexMessageSources(catalog) {
    for (const [key, value] of Object.entries(catalog)) {
        const source = compact(value);
        if (source && !source.includes("{")) sourceIndex.set(source, key);
    }
}

function buildSourceIndex() {
    sourceIndex = new Map();
    indexMessageSources(englishMessages);
}

function interpolate(value, parameters) {
    return value.replace(/\{(\w+)\}/g, (match, name) => (
        Object.hasOwn(parameters, name) ? String(parameters[name]) : match
    ));
}

export function t(key, parameters = {}) {
    const localized = messages[key];
    const fallback = englishMessages[key];
    if (localized === undefined && fallback === undefined) {
        i18nMetrics.missingKeyCount += 1;
        return key;
    }
    if (localized === undefined) i18nMetrics.fallbackCount += 1;
    return interpolate(localized ?? fallback, parameters);
}

export function translateValue(value) {
    const key = sourceIndex.get(compact(value));
    return key ? t(key) : value;
}

function translateTextNode(node) {
    const source = compact(node.nodeValue);
    if (!source) return;
    const key = textNodeKeys.get(node) || sourceIndex.get(source);
    if (!key) return;
    textNodeKeys.set(node, key);
    const translated = t(key);
    if (translated === source) return;
    const leading = node.nodeValue.match(/^\s*/)?.[0] ?? "";
    const trailing = node.nodeValue.match(/\s*$/)?.[0] ?? "";
    node.nodeValue = `${leading}${translated}${trailing}`;
}

function translateElementAttributes(element) {
    const knownKeys = attributeKeys.get(element) || new Map();
    for (const attribute of TRANSLATABLE_ATTRIBUTES) {
        const value = element.getAttribute(attribute);
        if (!value) continue;
        const key = knownKeys.get(attribute) || sourceIndex.get(compact(value));
        if (key) knownKeys.set(attribute, key);
        const translated = key ? t(key) : value;
        if (translated !== value) element.setAttribute(attribute, translated);
    }
    if (knownKeys.size > 0) attributeKeys.set(element, knownKeys);
}

export function translateDocument(root = document.documentElement) {
    if (root.nodeType === Node.TEXT_NODE) {
        translateTextNode(root);
        return;
    }
    if (!(root instanceof Element)) return;
    translateElementAttributes(root);
    const walker = document.createTreeWalker(
        root,
        NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
    );
    while (walker.nextNode()) {
        const node = walker.currentNode;
        if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
        else translateElementAttributes(node);
    }
}

function watchDynamicContent() {
    observer?.disconnect();
    observer = new MutationObserver((mutations) => {
        for (const mutation of mutations) {
            for (const node of mutation.addedNodes) translateDocument(node);
            if (mutation.type === "attributes") translateElementAttributes(mutation.target);
        }
    });
    observer.observe(document.documentElement, {
        attributes: true,
        attributeFilter: TRANSLATABLE_ATTRIBUTES,
        childList: true,
        subtree: true,
    });
}

export async function setLocale(locale, { persistCustomer = false } = {}) {
    let normalized = normalizeLocale(locale);
    let nextMessages;
    try {
        nextMessages = await loadMessages(normalized);
    } catch (error) {
        if (normalized === DEFAULT_LOCALE) throw error;
        console.warn(`Unable to load ${normalized}; falling back to English.`, error);
        i18nMetrics.fallbackCount += 1;
        normalized = DEFAULT_LOCALE;
        nextMessages = englishMessages;
    }
    indexMessageSources(messages);
    currentLocale = normalized;
    messages = nextMessages;
    document.documentElement.lang = normalized;
    if (persistCustomer) localStorage.setItem(CUSTOMER_LOCALE_KEY, normalized);
    translateDocument();
    watchDynamicContent();
    window.dispatchEvent(new CustomEvent("factored:locale-changed", {
        detail: { locale: normalized },
    }));
    return normalized;
}

export function clearCustomerLocale() {
    localStorage.removeItem(CUSTOMER_LOCALE_KEY);
}

export function getLocale() {
    return currentLocale;
}

export function getLanguage() {
    return languageFor(currentLocale);
}

export function formatCurrency(value, currency = "USD") {
    return new Intl.NumberFormat(currentLocale, {
        style: "currency",
        currency,
    }).format(value);
}

export function formatDate(value, options = { dateStyle: "medium" }) {
    return new Intl.DateTimeFormat(currentLocale, options).format(new Date(value));
}

async function detectIpLocale() {
    try {
        const response = await fetch("/api/localization/context", {
            headers: { Accept: "application/json" },
        });
        if (response.ok) return normalizeLocale((await response.json()).locale);
    } catch (error) {
        console.warn("Unable to infer interface locale from IP context:", error);
    }
    i18nMetrics.fallbackCount += 1;
    return DEFAULT_LOCALE;
}

async function initialize() {
    englishMessages = await loadMessages(DEFAULT_LOCALE);
    buildSourceIndex();
    const publicEntryPage = ["/", "/login", "/signup"].includes(
        window.location.pathname,
    );
    const rememberedCustomerLocale = publicEntryPage
        ? null
        : localStorage.getItem(CUSTOMER_LOCALE_KEY);
    const initialLocale = rememberedCustomerLocale || await detectIpLocale();
    await setLocale(initialLocale);
}

export const i18nReady = initialize();
