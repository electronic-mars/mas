// The strings live in locales/<code>.json, one file per language, and the list
// of languages in locales/index.json. Keeping them all in this file worked while
// there were three; with fourteen it would be a two-thousand-line wall where
// every new string has to be added in fourteen places, and one stray quote takes
// down the whole program instead of one language.
//
// English is always loaded and is the fallback: a key missing from a translation
// shows English rather than Russian, and only if it is missing there too does the
// key name itself appear — which is loud enough to be noticed and fixed.

export let LANGUAGES = [];

const FALLBACK = 'en';
const tables = {};
let current = FALLBACK;

async function fetchLocale(code) {
  const res = await fetch(`locales/${code}.json`);
  if (!res.ok) throw new Error(`locale ${code}: ${res.status}`);
  const doc = await res.json();
  tables[code] = doc.strings || {};
  return tables[code];
}

/** The list for the dropdown, and English in memory. Once, at startup. */
export async function loadLanguages() {
  try {
    const res = await fetch('locales/index.json');
    LANGUAGES = (await res.json()).map((l) => [l.code, l.name]);
  } catch (e) {
    LANGUAGES = [['en', 'English']];
  }
  try {
    await fetchLocale(FALLBACK);
  } catch (e) { /* nothing to fall back to; t() will show key names */ }
}

/** Load a language if it is not loaded yet. Await this before drawing. */
export async function ensureLang(code) {
  if (!code || tables[code]) return;
  try {
    await fetchLocale(code);
  } catch (e) {
    // A missing or broken file must not take the interface down with it: the
    // page simply stays in the language it already had.
  }
}

/** Switch to an already loaded language. Deliberately not async: it is called
 *  from drawing code, which cannot wait. */
export function setLang(code) {
  if (tables[code]) current = code;
}

export function t(key) {
  const mine = tables[current];
  if (mine && mine[key] !== undefined) return mine[key];
  const base = tables[FALLBACK];
  if (base && base[key] !== undefined) return base[key];
  return key;
}
