import { call } from './api.js';
import { LANGUAGES, ensureLang, loadLanguages, setLang, t } from './i18n.js';

// The order defines how the palette looks: sound first, then screens, then what
// goes on your head, then connectors, and marks at the end. The names are keys:
// they are stored in the device config, so every old one stays even if the
// drawing has changed.
const GLYPHS = [
  'speakers', 'edifier-r1700bts', 'soundbar', 'jbl-charge',
  'marshall-emberton-ii', 'homepod-mini', 'sonos-era-100',
  'tv', 'monitor', 'laptop', 'thinkpad', 'alienware-m18-r2',
  'headphones', 'headset', 'hyperx-cloud', 'earbuds', 'galaxy-buds',
  'sony-xm5', 'razer-kraken', 'powerbeats-pro-2',
  'microphone', 'hdmi', 'usb', 'bluetooth',
  'mark-cat', 'mark-clover', 'mark-duck', 'mark-wink', 'mark-ghost',
  'mark-skull', 'mark-reactor', 'mark-brain', 'mark-gamepad', 'mark-joystick',
  'mark-nintendo', 'mark-spotify', 'mark-vr', 'mark-ipod', 'mark-cassette',
  'mark-nfc', 'mark-crown', 'mark-bird', 'speaker-desk', 'speaker-radio'];

const AVATAR_COLORS = ['#F0453A', '#4A154B', '#1DB954', '#5865F2', '#0A84FF', '#E9711C', '#8E44AD'];

let state = null;
let mixerData = null;
let activeTab = 'devices';
let knobValue = 0;
let knobBusy = false;

const $ = (id) => document.getElementById(id);
const playBtn = document.querySelector('.tbtn[data-media="play"]');
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
// Icon next to a section heading. Through a mask rather than <img>: the colour
// has to come from the text, otherwise the icon would stay black on the dark
// panel.
const secIcon = (n) => `<span class="secico" style="-webkit-mask-image:url(icons/ui/${n}.svg);mask-image:url(icons/ui/${n}.svg)"></span>`;
// The palette shows the icon at 31 CSS pixels, so it needs the native 32-pixel
// version. Downscaling the 64-pixel one here eats the thin lines.
const iconDark = (n, size = 32) => `icons/devices/${GLYPHS.includes(n) ? n : 'speakers'}_dark_${size}.png`;
const iconLight = (n, size = 32) => `icons/devices/${GLYPHS.includes(n) ? n : 'speakers'}_light_${size}.png`;
const glyphSrc = (n, size = 32) => (document.documentElement.dataset.theme === 'light'
  ? iconLight(n, size) : iconDark(n, size));
const ICON_DENSITIES = [[32, 1], [40, 1.25], [48, 1.5], [64, 2]];
const glyphSrcset = (n, forceLight = false) => ICON_DENSITIES.map(([size, density]) => {
  const light = forceLight || document.documentElement.dataset.theme === 'light';
  return `${light ? iconLight(n, size) : iconDark(n, size)} ${density}x`;
}).join(', ');

// --------------------------------------------------------------- LCD windows
// Seven segments, like on a real panel: three volume digits and a percent sign.
const SEG_BOX = { a: [3, 0, 8, 3], b: [11, 3.4, 3, 6.7], c: [11, 13.9, 3, 6.7],
  d: [3, 21, 8, 3], e: [0, 13.9, 3, 6.7], f: [0, 3.4, 3, 6.7], g: [3, 10.5, 8, 3] };
const DIGITS = ['abcdef', 'bc', 'abdeg', 'abcdg', 'bcfg', 'acdfg', 'acdefg',
  'abc', 'abcdefg', 'abcdfg'];
const SEG_ORDER = 'abcdefg';

// Ten bars — as many as on the instrument meters of those years, and exactly as
// many as fit in the narrowest position of the window.
const BARS = 10, BAR_W = 4, BAR_GAP = 2.6, BAR_MIN = 7, BAR_MAX = 24, BAR_H = 25;

function buildDigit() {
  const rects = [...SEG_ORDER].map((s) => {
    const [x, y, w, h] = SEG_BOX[s];
    return `<rect class="lseg" data-seg="${s}" x="${x}" y="${y}" width="${w}" height="${h}" rx="1"/>`;
  }).join('');
  return `<svg viewBox="0 0 14 24" width="14" height="24">${rects}</svg>`;
}

function buildLcd() {
  // Left: three digits and a percent sign. The sign is always lit — it belongs
  // to the scale, not to the value, exactly like a symbol printed on the glass.
  $('lcd-vol').innerHTML = buildDigit().repeat(3)
    + `<svg viewBox="0 0 10 24" width="10" height="24" style="margin-left:2px">
         <rect class="pct" x="0" y="4" width="3.4" height="3.4" rx=".9"/>
         <rect class="pct" x="6.6" y="16.6" width="3.4" height="3.4" rx=".9"/>
         <line class="pct" x1="1.5" y1="20.4" x2="8.5" y2="4.6"
               stroke-width="2.1" stroke-linecap="round"/>
       </svg>`
    // Sound switched off: a crossed speaker in place of the number, in the
    // same ink. The knob keeps the level, as Windows does.
    + `<svg class="lcdmute" viewBox="0 0 30 24" width="30" height="24">
         <path class="pct" d="M2 8.5h5l6-5v17l-6-5H2z" stroke-width="1" stroke-linejoin="round"/>
         <path class="pct" d="M17.5 8l7.5 8M25 8l-7.5 8" fill="none" stroke-width="2.4" stroke-linecap="round"/>
       </svg>`;

  // Right: a staircase of bars. It grows to the right, so one glance shows how
  // loud it is without counting segments.
  const w = BARS * BAR_W + (BARS - 1) * BAR_GAP;
  const bars = Array.from({ length: BARS }, (_, i) => {
    const h = BAR_MIN + (BAR_MAX - BAR_MIN) * i / (BARS - 1);
    const x = i * (BAR_W + BAR_GAP);
    return `<rect class="lseg" data-bar="${i}" x="${x}" y="${(BAR_H - h).toFixed(2)}"
              width="${BAR_W}" height="${h.toFixed(2)}" rx="1"/>`;
  }).join('');
  $('lcd-lvl').innerHTML = `<svg viewBox="0 0 ${w} ${BAR_H}" width="${w}" height="${BAR_H}">${bars}</svg>`;
}

function paintVolume(pct) {
  const text = String(Math.round(pct)).padStart(3, ' ');
  $('lcd-vol').querySelectorAll('svg').forEach((svg, i) => {
    if (i > 2) return;                       // the fourth one is the percent sign
    const ch = text[i];
    const lit = ch === ' ' ? '' : DIGITS[+ch];
    svg.querySelectorAll('.lseg').forEach((r) => {
      r.classList.toggle('on', lit.includes(r.dataset.seg));
    });
  });
}

/** Level in decibels, not in fractions: quiet sound is otherwise invisible. */
function toLevel(peak) {
  if (peak <= 0.0005) return 0;
  return Math.max(0, Math.min(1, (20 * Math.log10(peak) + 50) / 50));
}

function paintLevel(level, hold) {
  const lit = Math.round(level * BARS);
  const peakBar = hold > 0.02 ? Math.min(BARS - 1, Math.round(hold * BARS) - 1) : -1;
  $('lcd-lvl').querySelectorAll('.lseg').forEach((r, i) => {
    const on = i < lit;
    r.classList.toggle('on', on);
    // The peak mark is a hollow segment: that is how real meters show it, and
    // it does not compete with the filled bars.
    r.classList.toggle('peak', !on && i === peakBar);
  });
}

// The bridge is polled five times a second — too rarely for a needle. Between
// answers the level is eased along: fast rise, slow fall, like a real meter.
// The peak is held and then quietly settles.
let lvlTarget = 0, lvlNow = 0, lvlHold = 0, lvlHoldAt = 0;

// A hidden window keeps painting: WebView2 does not consider it invisible, and
// document.hidden stays false. So Python is the one that reports the hiding and
// we stop the frames — otherwise the program draws 165 frames per second around
// the clock for a picture nobody sees.
let painting = false;

function meterFrame(t) {
  if (!painting) return;
  lvlNow += (lvlTarget - lvlNow) * (lvlTarget > lvlNow ? 0.45 : 0.07);
  if (lvlNow >= lvlHold) { lvlHold = lvlNow; lvlHoldAt = t; }
  else if (t - lvlHoldAt > 850) lvlHold = Math.max(lvlNow, lvlHold - 0.005);
  paintLevel(lvlNow, lvlHold);
  requestAnimationFrame(meterFrame);
}

function setPainting(on) {
  if (on === painting) return;
  painting = on;
  if (on) requestAnimationFrame(meterFrame);
}

// -------------------------------------------------------------------- knob
const TICKS = 41, ARC_START = -135, ARC_SPAN = 270, C = 65, R = 55;

function buildTicks() {
  const svg = $('ticks');
  svg.innerHTML = '';
  for (let i = 0; i < TICKS; i++) {
    const a = (ARC_START + ARC_SPAN * i / (TICKS - 1)) * Math.PI / 180;
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('cx', (C + R * Math.sin(a)).toFixed(2));
    c.setAttribute('cy', (C - R * Math.cos(a)).toFixed(2));
    c.setAttribute('r', i % 10 === 0 ? 1.9 : 1.2);
    svg.appendChild(c);
  }
}

// The ring shows volume only. The signal level moved to the right-hand window
// and the "breathing" of the ticks is gone: the same value must not live in two
// places.
function paintKnob(value) {
  const lit = Math.round(value / 100 * (TICKS - 1));
  $('ticks').childNodes.forEach((d, i) => {
    d.setAttribute('fill', i <= lit ? 'var(--acc)' : 'rgba(128,128,128,.22)');
  });
  $('ind').style.transform = `rotate(${ARC_START + ARC_SPAN * value / 100}deg)`;
  $('knob').setAttribute('aria-valuenow', Math.round(value));
  paintVolume(value);
}

// One call in flight per lane; the extra ones on the way collapse into the last
// value. Without this every mouse move spawned its own request: a hundred
// requests per second, each on its own thread and three milliseconds per COM
// write, arriving out of order — and the volume settled on a stale value even
// though the knob on screen stood in the right place.
const inFlight = new Map();

function push(lane, method, payload) {
  const job = inFlight.get(lane);
  if (job) { job.next = payload; return; }
  const state = { next: null };
  inFlight.set(lane, state);
  (async () => {
    let send = payload;
    while (send) {
      try { await call(method, send); } catch { /* window is closing */ }
      send = state.next;
      state.next = null;
    }
    inFlight.delete(lane);
  })();
}

function setKnob(value, { push: send = true } = {}) {
  knobValue = Math.max(0, Math.min(100, value));
  paintKnob(knobValue);
  if (send) {
    push('master', 'set_master', { value: knobValue / 100 });
    // Turning switches the sound back on (see set_volume in Python); the
    // number comes back now rather than at the next poll.
    $('lcd-vol').classList.remove('muted');
  }
}

const FINE = 0.25;      // with Shift held down — fine adjustment
const R_DEAD = 8;       // right at the axis the cursor angle is undefined
const OVER = 15;        // how many points of "overturn" past the stop we tolerate

/** Angle of a point relative to the knob centre: 0 at the top, clockwise. */
function angleAt(cx, cy, x, y) {
  return Math.atan2(x - cx, cy - y) * 180 / Math.PI;
}

/** Angle difference reduced to the nearest direction: ±180°. */
const shortest = (d) => ((d + 540) % 360) - 180;

function wireKnob() {
  const el = $('knob');
  let dragging = false, cx = 0, cy = 0, prev = 0, raw = 0;

  el.addEventListener('pointerdown', (e) => {
    // The grab point is bound hard to the cursor: from there the knob follows
    // its angle exactly, as if it were held by that point. The offset between
    // the grab point and the pointer mark is kept, so the mark does not jump
    // under the cursor.
    const r = el.getBoundingClientRect();
    cx = r.left + r.width / 2;
    cy = r.top + r.height / 2;
    prev = angleAt(cx, cy, e.clientX, e.clientY);
    raw = knobValue;
    dragging = knobBusy = true;
    el.classList.add('grabbing');
    el.setPointerCapture(e.pointerId);
    e.preventDefault();
  });

  el.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    if (Math.hypot(e.clientX - cx, e.clientY - cy) < R_DEAD) return;
    // The angle is unwrapped step by step: the difference from the PREVIOUS
    // angle is always small, so reducing it to ±180° is safe and going round
    // through the bottom of the knob does not flip the sign. The old code
    // measured the angle from the grab point, and there that reduction cut off
    // half the scale and flipped the sign on a swing larger than 180°.
    const a = angleAt(cx, cy, e.clientX, e.clientY);
    const step = shortest(a - prev) * 100 / ARC_SPAN;
    prev = a;
    // The raw value goes past the stop, but no further than OVER: the binding
    // to the grab point is kept (the knob picks up at the same angle where the
    // stop was left), yet you can no longer wind it up "on credit" for half a
    // turn.
    raw = Math.max(-OVER, Math.min(100 + OVER, raw + step * (e.shiftKey ? FINE : 1)));
    setKnob(raw);
  });

  const release = () => {
    if (!dragging) return;
    dragging = false;
    el.classList.remove('grabbing');
    setTimeout(() => { knobBusy = false; }, 250);
  };
  el.addEventListener('pointerup', release);
  el.addEventListener('pointercancel', release);

  el.addEventListener('wheel', (e) => {
    e.preventDefault();
    knobBusy = true;
    setKnob(knobValue + (e.deltaY < 0 ? 2 : -2));
    clearTimeout(el._t);
    el._t = setTimeout(() => { knobBusy = false; }, 400);
  }, { passive: false });

  el.addEventListener('keydown', (e) => {
    // The arrows were here; the rest is what anyone who reaches a slider by
    // keyboard tries next, and what every other slider in Windows answers to.
    const step = { ArrowUp: 2, ArrowRight: 2, ArrowDown: -2, ArrowLeft: -2,
      PageUp: 10, PageDown: -10 }[e.key];
    if (step) { e.preventDefault(); return setKnob(knobValue + step); }
    if (e.key === 'Home') { e.preventDefault(); return setKnob(0); }
    if (e.key === 'End') { e.preventDefault(); return setKnob(100); }
  });
}

// ----------------------------------------------------------------- mini view
// The order matters and is the same in both directions: first fix up the page,
// wait for a frame, and only then ask Python to resize the window. When
// expanding, the page manages to lay itself out while the window is still
// clipped, and the new area arrives with the content already in place —
// otherwise you see an empty background for a frame.
let mini = false;
let miniBusy = false;

function applyMini(on) {
  mini = on;
  document.documentElement.classList.toggle('mini', on);
}

async function toggleMini(on) {
  if (miniBusy) return;
  miniBusy = true;
  try {
    if (on) openTab('devices');
    applyMini(on);
    await new Promise(requestAnimationFrame);
    const height = on ? Math.ceil($('console').getBoundingClientRect().bottom + 12) : null;
    await call('set_mini', { on, height });
  } catch (e) { /* window is closing */ } finally { miniBusy = false; }
}

// ---------------------------------------------------------------------- tabs
function openTab(name) {
  if (!['devices', 'mixer', 'settings', 'about'].includes(name)) name = 'devices';
  activeTab = name;
  document.querySelectorAll('.tab').forEach((b) =>
    b.setAttribute('aria-selected', String(b.dataset.tab === name)));
  for (const p of ['devices', 'mixer', 'settings', 'about'])
    $(`panel-${p}`).classList.toggle('hidden', p !== name);
  $('console').classList.toggle('hidden', name !== 'devices');
  $('scroller').scrollTop = 0;
  if (name === 'mixer') refreshMixer();
  updateFade();
}

function updateFade() {
  const s = $('scroller');
  $('fade').classList.toggle('hidden', s.scrollHeight - s.clientHeight < 6);
}

// -------------------------------------------------------------- devices tab
// The drag grip is drawn with dots rather than the ⣿ character: the character
// has its own width in every font, its box had to be clipped, and the bottom
// row of dots was cut in half.
const GRIP = `<svg viewBox="0 0 6 16" width="6" height="16">${
  [1.6, 5.8, 10, 14.2].map((y) => `<circle cx="1" cy="${y}" r="1"/><circle cx="5" cy="${y}" r="1"/>`).join('')
}</svg>`;

function deviceRow(d, { draggable = false, active = false } = {}) {
  // The slot for the drag grip is always occupied: microphones do not have one,
  // and without the blank space their icons would sit further left than those
  // of output devices.
  return `<div class="row ${active ? 'active' : ''}" data-id="${esc(d.id)}" ${draggable ? 'data-order' : ''}>
      <span class="grip ${draggable ? '' : 'blank'}">${GRIP}</span>
      <button class="ic" data-act="icon" title="${t('icon_title')}">
        <img src="${glyphSrc(d.icon)}" srcset="${glyphSrcset(d.icon)}" alt="">
        <span class="pen"><svg viewBox="0 0 24 24"><path d="M3 17.25V21h3.75L17.8 9.94l-3.75-3.75L3 17.25z"/></svg></span>
      </button>
      <div class="col">
        <span class="dot ${active ? '' : 'ghost'}"></span>
        <span class="nm" title="${esc(d.name)}">${esc(d.name)}</span>
      </div>
      <button class="chk" data-act="cycle" role="checkbox" aria-checked="${d.in_cycle}"
              title="${t('in_cycle')}">
        <svg viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>
      </button>
    </div>`;
}

function renderDevices() {
  // The order is exactly the one the devices are switched in — otherwise
  // dragging is pointless: the list would re-sort itself right afterwards.
  // What is playing right now is shown by the green dot and the row highlight.
  const outs = state.outputs;
  const mics = state.inputs;
  const expanded = !!state.settings.mics_expanded;

  const hint = state.settings.switch_button === 'right' ? t('cycle_hint_right') : t('cycle_hint');
  $('panel-devices').innerHTML =
    `<h2 class="lbl micro">${secIcon('ui-toggle')}${hint}</h2>
     ${outs.length ? outs.map((d) => deviceRow(d, { draggable: true, active: d.is_default })).join('')
      : `<div class="empty">${t('no_devices')}</div>`}
     <button class="fold" id="fold-mics" aria-expanded="${expanded}">
       <span class="arw"><svg viewBox="0 0 24 24"><path d="M9 5l7 7-7 7"/></svg></span>
       ${secIcon('ui-mic')}<span class="micro">${t('microphones')}</span>
       <span class="micro cnt">${mics.length}</span>
     </button>
     <div id="mics" class="${expanded ? '' : 'hidden'}">
       ${mics.map((d) => deviceRow(d, { active: d.is_default })).join('')}
     </div>`;
}

// ----------------------------------------------------------------- mixer tab
function avatarColor(name) {
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

// The master volume icon is large, level with the device icons on the first
// tab. The old fifteen-pixel one got lost inside the orange tile.
const SPEAKER_SVG = '<span class="mxico" style="-webkit-mask-image:url(icons/ui/vol-high.svg);mask-image:url(icons/ui/vol-high.svg)"></span>';
const SPEAKER_OFF_SVG = SPEAKER_SVG.replaceAll('vol-high', 'vol-x');
// An application's own icon is not touched: the mute mark sits in its corner.
const MUTE_BADGE = '<span class="mbadge"><svg viewBox="0 0 24 24"><path d="M3 9h4l5-4.5v15L7 15H3z"/><path d="M15.5 9l6 6m0-6l-6 6" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" fill="none"/></svg></span>';

function sliderRow({ key, label, volume, muted, kind, icon }) {
  const pct = Math.round(volume * 100);
  const face = kind === 'master' ? (muted ? SPEAKER_OFF_SVG : SPEAKER_SVG)
    : icon ? `<img src="appicon/${esc(icon)}" alt="">`
      : esc((label[0] || '?'));
  const bg = kind === 'master' ? 'var(--acc)' : icon ? 'transparent' : avatarColor(label);
  return `<div class="mx ${muted ? 'muted' : ''}" data-key="${esc(key)}" data-kind="${kind}">
      <button class="ap" data-act="mute" style="background:${bg}"
              title="${muted ? t('unmute') : t('mute')}" aria-pressed="${muted}">
        ${face}${kind === 'master' ? '' : MUTE_BADGE}
      </button>
      <div class="col">
        <div class="top"><span class="nm">${esc(label)}</span>
          <span class="pc">${pct}%</span></div>
        <div class="slider" data-act="vol">
          <div class="track"></div>
          <div class="fill" style="width:${pct}%"></div>
          <div class="knb" style="left:${pct}%"></div>
        </div>
      </div>
    </div>`;
}

function renderMixer() {
  if (!mixerData) { $('panel-mixer').innerHTML = ''; return; }
  const apps = mixerData.sessions.map((s) => sliderRow({
    key: s.key,
    label: s.key === 'System sounds' ? t('system_sounds') : s.name,
    volume: s.volume, muted: s.muted, kind: 'app', icon: s.icon,
  })).join('');
  $('panel-mixer').innerHTML =
    `<h2 class="lbl micro">${secIcon('vol-high')}${t('master')}</h2>
     ${sliderRow({ key: '', label: mixerData.device || t('master'),
      volume: mixerData.master.volume, muted: mixerData.master.muted, kind: 'master' })}
     <h2 class="sec micro">${secIcon('ui-apps')}${t('apps')}</h2>
     ${apps || `<div class="empty">${t('no_apps')}</div>`}`;
  updateFade();
}

async function refreshMixer() {
  try {
    mixerData = await call('get_mixer');
    renderMixer();
  } catch (e) { /* window is closing */ }
}

// -------------------------------------------------------------- settings tab
// A settings row: name and explanation on the left, the control on the right.
// All rows of a section live in one `group` panel, so the right column lines
// itself up without any fixed widths.
function stRow(label, desc, ctl, { stack = false } = {}) {
  return `<div class="st ${stack ? 'stack' : ''}">
      <div class="col"><div class="nm">${label}</div>${desc ? `<div class="ds">${desc}</div>` : ''}</div>
      <div class="ctl">${ctl}</div>
    </div>`;
}

function toggle(key, label, desc) {
  return stRow(label, desc,
    `<button class="sw" data-set="${key}" role="switch" aria-checked="${!!state.settings[key]}"><i></i></button>`);
}

const group = (rows) => `<div class="group">${rows.filter(Boolean).join('')}</div>`;

// ------------------------------------------------------ keyboard shortcut capture
// The names match the ones hotkey.py parses on the Python side.
const KEY_NAMES = {
  ' ': 'Space', Enter: 'Enter', Tab: 'Tab', Escape: 'Esc', Backspace: 'Backspace',
  ArrowLeft: 'Left', ArrowUp: 'Up', ArrowRight: 'Right', ArrowDown: 'Down',
  Home: 'Home', End: 'End', PageUp: 'PgUp', PageDown: 'PgDn',
  Insert: 'Ins', Delete: 'Del',
};

let capturing = false;

/** "Ctrl+Alt+H" from a keyboard event. null means the key is unfit for a combo. */
function comboFrom(e) {
  const key = e.key;
  if (['Control', 'Alt', 'Shift', 'Meta'].includes(key)) return null;
  let name = null;
  if (/^[a-zA-Zа-яА-Я0-9]$/.test(key)) name = (e.code.startsWith('Key') ? e.code.slice(3)
    : e.code.startsWith('Digit') ? e.code.slice(5) : key.toUpperCase());
  else if (/^F([1-9]|1[0-9]|2[0-4])$/.test(key)) name = key;
  else if (KEY_NAMES[key]) name = KEY_NAMES[key];
  if (!name) return null;
  const mods = [];
  if (e.ctrlKey) mods.push('Ctrl');
  if (e.altKey) mods.push('Alt');
  if (e.shiftKey) mods.push('Shift');
  if (e.metaKey) mods.push('Win');
  // A key with no modifier takes it away from the whole system — only the
  // F row is allowed.
  if (!mods.length && !/^F\d+$/.test(name)) return null;
  return [...mods, name].join('+');
}

function startCapture(btn, key) {
  capturing = true;
  btn.textContent = t('hk_press');
  btn.classList.add('armed');
  // Armed means two things are suspended: every keystroke in the window is
  // swallowed, and the settings stop refreshing so the button does not lose its
  // state mid-capture. Both have to end even when the person simply changes
  // their mind — a click elsewhere, another window, or walking away. Without
  // this the panel stayed frozen and the next stray keystroke was written into
  // a setting nobody was looking at any more.
  const done = () => {
    capturing = false;
    clearTimeout(timer);
    document.removeEventListener('keydown', onKey, true);
    document.removeEventListener('pointerdown', onElsewhere, true);
    window.removeEventListener('blur', done);
    renderAll();
  };
  const onElsewhere = (e) => { if (!e.target.closest('[data-capture]')) done(); };
  const onKey = async (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.key === 'Escape' && !e.ctrlKey && !e.altKey && !e.shiftKey) return done();
    const combo = comboFrom(e);
    if (!combo) return;
    done();
    state = await call('set_setting', { key, value: combo });
    renderAll();
  };
  const timer = setTimeout(done, 15000);
  document.addEventListener('keydown', onKey, true);
  document.addEventListener('pointerdown', onElsewhere, true);
  window.addEventListener('blur', done);
}

function renderSettings() {
  const theme = state.settings.theme || 'system';
  // The attribute is data-set-theme on purpose: data-theme sits on the page
  // root, and closest('[data-theme]') would find it on any click in the window.
  const seg = (v, label) => `<button class="seg" data-set-theme="${v}" aria-selected="${theme === v}">${label}</button>`;
  const langOptions = LANGUAGES.map(([code, label]) =>
    `<option value="${code}" ${state.settings.language === code ? 'selected' : ''}>${label}</option>`).join('');

  const btn = state.settings.switch_button || 'left';
  const btnSeg = (v, label) =>
    `<button class="seg" data-set-button="${v}" aria-selected="${btn === v}">${label}</button>`;

  const hk = state.settings.hotkey || '';
  const auto = state.settings.auto_device || '';
  // The ones connected right now go on top as a separate group: people look for
  // their headphones with their eyes, they do not read the whole list of ports
  // Windows has piled up over the years.
  const known = state.known_outputs || [];
  const optGroup = (label, list) => (list.length
    ? `<optgroup label="${label}">${list.map((d) =>
      `<option value="${esc(d.id)}" ${auto === d.id ? 'selected' : ''}>${esc(d.name)}</option>`).join('')}</optgroup>`
    : '');
  const autoOptions = `<option value="" ${auto ? '' : 'selected'}>${t('auto_none')}</option>`
    + optGroup(t('auto_here'), known.filter((d) => d.active))
    + optGroup(t('auto_away'), known.filter((d) => !d.active));

  // The keyboard shortcut and the mouse button are about the same thing: what
  // to switch sound with. That is why they share a section, and the row names
  // talk about the control itself — otherwise the panel would read "Switch
  // sound" twice in a row.
  const keyRow = (setting, combo, taken) => ({
    ctl: `<button class="seg key" data-capture="${setting}">${combo ? esc(combo) : t('hk_none')}</button>`
      + (combo ? `<button class="seg drop" data-uncapture="${setting}">${t('hk_clear')}</button>` : ''),
    warn: combo && taken === false
      ? `<div class="st"><div class="ds warn">${t('hk_taken')}</div></div>` : '',
  });
  const hkKey = keyRow('hotkey', hk, state.settings.hotkey_ok);
  const hkCtl = hkKey.ctl;
  const hkWarn = hkKey.warn;

  // The nominated player. Only those we have actually seen are offered: a list
  // of everything installed would be a list of guesses, and the chosen one stays
  // in it even while it is not running.
  const player = state.settings.priority_player || '';
  const seen = state.settings.players || [];
  const playerOptions = `<option value="" ${player ? '' : 'selected'}>${t('player_none')}</option>`
    + seen.map((p) => `<option value="${esc(p.id)}" ${player === p.id ? 'selected' : ''}>${esc(p.name)}</option>`).join('');
  const hkPlay = keyRow('hotkey_play', state.settings.hotkey_play || '',
    state.settings.hotkey_play_ok);

  // Long lists are left under the name at full width: a device name like
  // "Headphones (HyperX Cloud Flight S)" would have to be truncated in the
  // right column.
  $('panel-settings').innerHTML =
    `<h2 class="lbl micro">${secIcon('sec-startup')}${t('startup')}</h2>
     ${group([state.settings.from_store
    ? stRow(t('autostart'), t('autostart_store'),
      `<button class="seg drop" data-act="startup">${t('open_btn')}</button>`)
    : toggle('autostart', t('autostart'), t('autostart_d'))])}
     <h2 class="sec micro">${secIcon('sec-auto')}${t('auto')}</h2>
     ${group([
      stRow(t('auto_device'), t('auto_device_d'),
        `<select id="auto-select">${autoOptions}</select>`, { stack: true }),
      toggle('switch_microphone', t('mic_follow'), t('mic_follow_d')),
      state.settings.dongle_name
        ? toggle('watch_dongle', t('dongle'), t('dongle_d').replace('%s', state.settings.dongle_name))
        : '',
      // Offered only for a dongle nothing is known about: for a recognised one
      // the switch above already does the job, and teaching it again could only
      // replace a verified rule with a guess.
      //
      // It used to live under Diagnostics, at the bottom of the page. Automatic
      // switching and teaching the dongle are two halves of one wish — the sound
      // following the headset — and the half that makes it work when the headset
      // is switched OFF sat under a heading that reads as logs and bug reports.
      // People set the device above, found nothing else, and concluded the
      // feature was broken.
      state.settings.dongle_usb && !state.settings.dongle_name
        ? stRow(t('teach'), t('teach_d').replace('%s', state.settings.dongle_usb),
          `<button class="seg drop" data-act="teach">${t('teach_btn')}</button>`, { stack: true })
        : '',
    ])}
     <h2 class="sec micro">${secIcon('ui-wave')}${t('player')}</h2>
     ${group([
      stRow(t('player_row'), t('player_d'),
        `<select id="player-select">${playerOptions}</select>`, { stack: true }),
      stRow(t('player_key'), t('player_key_d'), `<div class="segs">${hkPlay.ctl}</div>`),
      hkPlay.warn,
    ])}
     <h2 class="sec micro">${secIcon('sec-control')}${t('control')}</h2>
     ${group([
      stRow(t('hk_row'), t('hk_switch_d'), `<div class="segs">${hkCtl}</div>`),
      hkWarn,
      stRow(t('btn_row'), btn === 'left' ? t('buttons_d_left') : t('buttons_d_right'),
        `<div class="segs">${btnSeg('left', t('btn_left'))}${btnSeg('right', t('btn_right'))}</div>`),
      // Only while a dock is showing us: without one, the tray icon is the only
      // way in and must not be switchable off.
      state.settings.dock_showing
        ? toggle('tray_with_dock', t('tray_dock'), t('tray_dock_d'))
        : '',
    ])}
     <h2 class="sec micro">${secIcon('sec-switching')}${t('switching')}</h2>
     ${group([
      toggle('switch_communications', t('comms'), t('comms_d')),
      toggle('notify_on_switch', t('notify'), t('notify_d')),
      toggle('sound_on_switch', t('beep'), t('beep_d')),
    ])}
     <h2 class="sec micro">${secIcon('sec-appearance')}${t('appearance')}</h2>
     ${group([
      stRow(t('theme_row'), '',
        `<div class="segs wide">${seg('system', t('theme_system'))}${seg('dark', t('theme_dark'))}${seg('light', t('theme_light'))}</div>`,
        { stack: true }),
      // A language is a short word, so the list fits in the right column. That
      // does not work for the priority device: the names there run half a line.
      stRow(t('language'), '', `<select id="lang-select" class="narrow">${langOptions}</select>`),
    ])}
     <h2 class="sec micro">${secIcon('sec-diag')}${t('diag')}</h2>
     ${group([
      stRow(t('learn_open'), t('learn_open_d'),
        `<button class="seg drop" data-act="folder">${t('open_btn')}</button>`),
    ])}`;
}

// ------------------------------------------------------------------ updating
// A copy from the Microsoft Store is updated by the Store: quietly, in the
// background, better than we could. A copy from the releases page has nobody to
// do that for it, so it gets the button. One program, one build — which of the
// two it is, Windows is asked at startup.
let upClearing = null;

function updateBlock() {
  if (state.settings.from_store) {
    return `<div class="micro store">${t('up_store')}</div>`;
  }
  const up = state.settings.update || { state: 'idle' };
  const busy = ['checking', 'downloading', 'checking_file', 'installing'].includes(up.state);
  const label = {
    idle: t('updates'),
    checking: t('up_checking'),
    current: t('up_current'),
    available: t('up_available').replace('%s', up.detail || ''),
    downloading: `${t('up_downloading')} ${up.percent || 0}%`,
    checking_file: t('up_verifying'),
    installing: t('up_installing'),
    failed: t('up_retry'),
  }[up.state] || t('updates');

  // The answer to a check is not a state to sit in: three seconds and the
  // button is a button again, so nobody is left looking at a stale report.
  if (up.state === 'current' && !upClearing) {
    upClearing = setTimeout(() => {
      upClearing = null;
      call('update_action', { action: 'forget' }).catch(() => {});
    }, 3000);
  }

  const bar = up.state === 'downloading'
    ? `<div class="upbar"><i style="width:${up.percent || 0}%"></i></div>` : '';
  // Named reasons get a sentence of their own; anything else — an HTTP code,
  // say — is shown as it came, because it is the thing worth searching for.
  const named = { network: t('up_why_network'), signature: t('up_why_signature'),
    release: t('up_why_release') }[up.detail];
  const why = up.state === 'failed'
    ? `<div class="micro fail">${t('up_failed').replace('%s', named || esc(up.detail || ''))}</div>` : '';
  const kind = up.state === 'available' ? 'btn' : 'btn ghost';
  return `<button class="${kind}" data-act="update" ${busy ? 'disabled' : ''}>
      ${secIcon('ui-refresh')}${label}</button>${bar}${why}`;
}

function renderAbout() {
  $('panel-about').innerHTML = `<div class="about">
      <img class="logo" src="icons/app/icon_512.png" alt="">
      <h2>Master Audio Switcher</h2>
      <div class="micro" style="margin-top:6px">${t('version')} ${state.settings.version}</div>
      <p>${t('about_text')}</p>
      <button class="btn" data-url="https://www.patreon.com/ElectronicMARS">${secIcon('ui-heart')}${t('donate')}</button>
      <button class="btn ghost" data-url="https://github.com/electronic-mars/mas">${secIcon('ui-github')}${t('github')}</button>
      ${updateBlock()}
      <button class="btn ghost quit" data-act="quit" style="margin-top:16px">${secIcon('ui-exit')}${t('quit')}</button>
    </div>`;
}

// -------------------------------------------------------------- icon palette
// Escape closes whatever is open over the page. Clicking the backdrop already
// did, but a backdrop is a thing you have to know about, and Escape is the thing
// everyone tries first — including everyone who is not using a mouse at all.
function closeOnEscape(close) {
  const onKey = (e) => {
    if (e.key !== 'Escape') return;
    e.preventDefault();
    document.removeEventListener('keydown', onKey, true);
    close();
  };
  document.addEventListener('keydown', onKey, true);
  return () => document.removeEventListener('keydown', onKey, true);
}

function openIconSheet(deviceId, currentGlyph) {
  $('overlays').innerHTML = `<div class="sheet" id="sheet"><div class="box">
      <div class="micro">${t('icon_title')}</div>
      <div class="grid">${GLYPHS.map((g) =>
    `<button class="gi" data-glyph="${g}" aria-selected="${g === currentGlyph}">
           <img src="${g === currentGlyph ? iconLight(g, 32) :
    (document.documentElement.dataset.theme === 'light' ? iconLight(g, 32) : iconDark(g, 32))}"
                srcset="${glyphSrcset(g, g === currentGlyph)}" alt="${g}"></button>`).join('')}</div>
    </div></div>`;
  const drop = closeOnEscape(() => { $('overlays').innerHTML = ''; });
  $('sheet').addEventListener('click', async (e) => {
    const btn = e.target.closest('.gi');
    if (btn) {
      state = await call('set_icon', { device_id: deviceId, glyph: btn.dataset.glyph });
      renderAll();
    }
    if (btn || e.target.id === 'sheet') { drop(); $('overlays').innerHTML = ''; }
  });
  // The first glyph takes focus, so the palette can be walked with Tab and
  // chosen with Enter without ever reaching for the mouse.
  $('sheet').querySelector('.gi')?.focus();
}

// ------------------------------------------------------------------- welcome
function gestureCard(inner, title, desc) {
  return `<div class="gest"><div class="n"><svg viewBox="0 0 24 24">${inner}</svg></div>
    <div><div class="t">${title}</div><div class="d">${desc}</div></div></div>`;
}

function showWelcome() {
  // The two buttons used to be drawn with a hairline stroke on one side, and at
  // seventeen pixels the three cards read as the same picture repeated three
  // times. The pressed button is filled instead: the mouse body is a rounded
  // rectangle whose top corners have radius 6, so each button is exactly one
  // quadrant of that corner and can be drawn as an arc, not approximated.
  const mouse = (side) => `<rect x="6" y="2.5" width="12" height="19" rx="6"/>
    <path d="${side === 'left' ? 'M6 8.5A6 6 0 0 1 12 2.5L12 8.5Z'
                               : 'M12 2.5A6 6 0 0 1 18 8.5L12 8.5Z'}"
      style="fill:var(--acc);stroke:none"/>`;
  // Two cards, not three. The middle button opens the mixer, which is also the
  // second tab of this window — teaching it here cost a third of the screen to
  // say something nobody needs in their first minute, and made the two clicks
  // that matter look like one item in a list of three.
  $('overlays').innerHTML = `<div class="welcome" id="welcome">
      <div class="big"><svg viewBox="0 0 24 24"><path d="M4 9v6h4l5 4V5L8 9H4zm12.5 3a4.5 4.5 0 00-2.5-4v8a4.5 4.5 0 002.5-4z"/></svg></div>
      <h2>${t('w_title')}</h2>
      <div style="margin-top:12px">
        ${gestureCard(mouse('left'), t('g_left'), t('g_left_d2'))}
        ${gestureCard(mouse('right'), t('g_right'), t('g_right_d'))}
        ${gestureCard('<path d="M7 14l5-5 5 5" fill="none"/>', t('w_hidden'), t('welcome_note'))}
      </div>
      <button class="btn" id="welcome-ok" style="margin-top:12px">${t('welcome_ok')}</button>
    </div>`;
  $('welcome-ok').addEventListener('click', async () => {
    await call('complete_onboarding').catch(() => {});
    $('overlays').innerHTML = '';
  });
}

// -------------------------------------------------------- teaching a dongle
// Four steps and not two, for the reason set out in core/dongle.py: one "on"
// and one "off" would also be told apart by a battery reading, and a wrong byte
// means headphones that seize the sound at random.
const WIZ_STEPS = ['on1', 'off1', 'on2', 'off2'];
// How long a step waits before letting you move on regardless. A dongle that
// says nothing is a real outcome — it just has to be reached, not sat in.
const WIZ_PATIENCE = 25000;

function showDongleWizard() {
  let idx = 0, heard = 0, ready = false, result = null, timer = null, since = 0;

  const finished = () => idx === WIZ_STEPS.length - 1;

  function draw() {
    if (result) {
      $('overlays').innerHTML = `<div class="welcome wiz" id="wiz">
          <h2>${result.ok ? t('wiz_ok') : t('wiz_no')}</h2>
          <div class="note">${result.ok
    ? t('wiz_ok_d').replace('%s', esc(result.name))
    : t('wiz_no_d')}</div>
          <div class="log">${esc(result.report)}</div>
          <button class="btn" data-url="${encodeURI(result.url)}">${t('wiz_send')}</button>
          <button class="btn ghost" data-wiz="close">${t('wiz_close')}</button>
        </div>`;
      $('wiz').addEventListener('click', onClick);
      return;
    }
    $('overlays').innerHTML = `<div class="welcome wiz" id="wiz">
        <div class="step">${t('wiz_step').replace('%1', idx + 1).replace('%2', WIZ_STEPS.length)}</div>
        <h2>${t('wiz_title')}</h2>
        <div class="act">${t('wiz_' + WIZ_STEPS[idx])}</div>
        <div class="heard"></div>
        <button class="btn" data-wiz="next" style="margin-top:14px">
          ${finished() ? t('wiz_finish') : t('wiz_next')}</button>
        <button class="btn ghost" data-wiz="close">${t('wiz_cancel')}</button>
      </div>`;
    $('wiz').addEventListener('click', onClick);
    paint();
  }

  // Only the counter and the button change while a step runs. Redrawing the
  // whole panel for that would blink the instruction the person is reading.
  function paint() {
    const line = document.querySelector('.wiz .heard');
    const next = document.querySelector('.wiz [data-wiz="next"]');
    if (line) {
      line.innerHTML = heard
        ? t('wiz_heard').replace('%s', `<b>${heard}</b>`)
        : t('wiz_waiting');
    }
    if (next) next.disabled = !ready;
  }

  async function tick() {
    const st = await call('dongle_wizard', { action: 'poll' }).catch(() => null);
    if (!st || !st.running) return;
    heard = st.heard || 0;
    // "Settled" means the dongle has stopped talking: a headset takes seconds to
    // power up and then sends several reports in a row, and moving on in the
    // middle of that would file the rest of them under the next step.
    ready = st.settled || Date.now() - since > WIZ_PATIENCE;
    paint();
  }

  async function enter(i) {
    idx = i;
    heard = 0;
    ready = false;
    since = Date.now();
    draw();
    await call('dongle_wizard', { action: 'step', step: WIZ_STEPS[i] }).catch(() => {});
  }

  // The handler goes on the panel, which draw() replaces every step: on the
  // overlay container it would pile up one dead listener per opening, each with
  // its own idea of which step we are on.
  async function onClick(e) {
    const btn = e.target.closest('[data-wiz]');
    if (!btn) return;
    if (btn.dataset.wiz === 'close') {
      dropEscape();
      clearInterval(timer);
      $('overlays').innerHTML = '';
      if (!result) call('dongle_wizard', { action: 'cancel' }).catch(() => {});
      return;
    }
    if (!ready) return;
    btn.disabled = true;
    ready = false;
    if (!finished()) return void enter(idx + 1);
    clearInterval(timer);
    result = await call('dongle_wizard', { action: 'finish' }).catch(() => null);
    if (!result) return void ($('overlays').innerHTML = '');
    state = await call('get_state');
    renderAll();          // the switch above appears the moment the rule is saved
    draw();
  }

  // Escape leaves the wizard the way Cancel does — the dongle has to be let go,
  // or the listener stays open with nobody able to reach it.
  const dropEscape = closeOnEscape(() => {
    clearInterval(timer);
    $('overlays').innerHTML = '';
    if (!result) call('dongle_wizard', { action: 'cancel' }).catch(() => {});
  });

  call('dongle_wizard', { action: 'start' }).then((st) => {
    if (!st || !st.running) throw new Error('the dongle did not open');
    timer = setInterval(tick, 400);
    return enter(0);
  }).catch(() => { dropEscape(); $('overlays').innerHTML = ''; });
}

// -------------------------------------------------------------------- shared
function applyTheme() {
  const mode = state?.settings?.theme ?? 'system';
  const dark = mode === 'dark' ? true
    : mode === 'light' ? false
      : window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
}

function renderAll() {
  setLang(state.settings.language);
  applyTheme();
  document.documentElement.lang = state.settings.language;
  document.querySelectorAll('[data-t]').forEach((el) => { el.textContent = t(el.dataset.t); });
  renderDevices();
  renderMixer();
  renderSettings();
  renderAbout();
  updateFade();
}

async function refresh() {
  state = await call('get_state');
  // The language file is fetched before drawing, not during: t() is called from
  // every render function and cannot wait for a file.
  await ensureLang(state.settings.language);
  renderAll();
}

// -------------------------------------------------------------------- events
document.addEventListener('click', async (e) => {
  const tab = e.target.closest('.tab');
  if (tab) return openTab(tab.dataset.tab);

  // A key pressed with the mouse keeps focus, and a ring hangs around it even
  // though the person has already moved their hand away. Drop the focus at
  // once: the ring is only needed by someone walking the interface from the
  // keyboard, and they do not lose focus.
  const pressed = e.target.closest('.tbtn, .iconbtn');
  if (pressed) pressed.blur();

  const media = e.target.closest('[data-media]');
  if (media) return void call('media', { action: media.dataset.media }).catch(() => {});

  if (e.target.closest('#btn-mini')) return void toggleMini(!mini);
  if (e.target.closest('#btn-close')) return void call('hide_window').catch(() => {});

  const fold = e.target.closest('#fold-mics');
  if (fold) {
    state = await call('set_setting', { key: 'mics_expanded', value: !state.settings.mics_expanded });
    return renderAll();
  }

  const row = e.target.closest('.row');
  if (row) {
    if (rowDragged) return;   // the row was dragged, not selected
    const act = e.target.closest('[data-act]')?.dataset.act;
    const dev = [...state.outputs, ...state.inputs].find((d) => d.id === row.dataset.id);
    if (!dev) return;
    if (act === 'cycle') {
      state = await call('toggle_cycle', { device_id: dev.id, enabled: !dev.in_cycle });
      return renderAll();
    }
    if (act === 'icon') return openIconSheet(dev.id, dev.icon);
    if (!dev.is_default) {
      state = await call('switch_to', { device_id: dev.id });
      return renderAll();
    }
    return;
  }

  // Mute is on the application icon. Hovering shows a crossed-out speaker; when
  // muted the icon is desaturated and the row dims.
  const muteBtn = e.target.closest('.mx [data-act="mute"]');
  if (muteBtn) {
    const mx = muteBtn.closest('.mx');
    const pressed = muteBtn.getAttribute('aria-pressed') === 'true';
    if (mx.dataset.kind === 'master') await call('set_master_mute', { muted: !pressed });
    else await call('set_app_mute', { key: mx.dataset.key, muted: !pressed });
    return refreshMixer();
  }

  const sw = e.target.closest('.sw');
  if (sw) {
    const key = sw.dataset.set;
    state = await call('set_setting', { key, value: !state.settings[key] });
    return renderAll();
  }

  const grab = e.target.closest('[data-capture]');
  if (grab) {
    if (!capturing) startCapture(grab, grab.dataset.capture);
    return;
  }
  const drop = e.target.closest('[data-uncapture]');
  if (drop) {
    state = await call('set_setting', { key: drop.dataset.uncapture, value: '' });
    return renderAll();
  }

  const buttonSeg = e.target.closest('[data-set-button]');
  if (buttonSeg) {
    state = await call('set_setting', { key: 'switch_button', value: buttonSeg.dataset.setButton });
    return renderAll();
  }

  const themeBtn = e.target.closest('[data-set-theme]');
  if (themeBtn) {
    state = await call('set_setting', { key: 'theme', value: themeBtn.dataset.setTheme });
    return renderAll();
  }

  const urlBtn = e.target.closest('[data-url]');
  if (urlBtn) return void call('open_url', { url: urlBtn.dataset.url }).catch(() => {});

  const upBtn = e.target.closest('[data-act="update"]');
  if (upBtn) {
    // "Available" is the only state where the button installs. Everywhere else
    // — including after a failure — it goes back to asking.
    const now = state.settings.update?.state;
    state = await call('update_action',
      { action: now === 'available' ? 'install' : 'check' }).catch(() => state);
    return renderAll();
  }

  if (e.target.closest('[data-act="startup"]')) return void call('open_startup_settings').catch(() => {});
  if (e.target.closest('[data-act="teach"]')) return void showDongleWizard();
  if (e.target.closest('[data-act="folder"]')) return void call('open_data_folder').catch(() => {});
  if (e.target.closest('[data-act="quit"]')) return void call('quit').catch(() => {});
});

document.addEventListener('change', async (e) => {
  if (e.target.id === 'lang-select') {
    state = await call('set_setting', { key: 'language', value: e.target.value });
    // The file has to be here before anything is drawn in it. Without this the
    // dropdown moved and every other word stayed in the old language, until
    // something unrelated happened to force a full refresh — which made it look
    // as if picking a language worked at random.
    await ensureLang(state.settings.language);
    renderAll();
  }
  if (e.target.id === 'auto-select') {
    state = await call('set_setting', { key: 'auto_device', value: e.target.value });
    renderAll();
  }
  if (e.target.id === 'player-select') {
    state = await call('set_setting', { key: 'priority_player', value: e.target.value });
    renderAll();
  }
});

// mixer sliders
document.addEventListener('pointerdown', (e) => {
  const slider = e.target.closest('.slider');
  if (!slider) return;
  const mx = slider.closest('.mx');
  const apply = (ev) => {
    const r = slider.getBoundingClientRect();
    const v = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
    slider.querySelector('.fill').style.width = `${v * 100}%`;
    slider.querySelector('.knb').style.left = `${v * 100}%`;
    mx.querySelector('.pc').textContent = `${Math.round(v * 100)}%`;
    // Moving the slider switches the sound back on (see set_volume in Python),
    // so the row stops looking muted right away rather than at the next refresh.
    mx.classList.remove('muted');
    if (mx.dataset.kind === 'master') mx.querySelector('.ap').innerHTML = SPEAKER_SVG;
    mx.querySelector('.ap').setAttribute('aria-pressed', 'false');
    const master = mx.dataset.kind === 'master';
    // Mixer sliders are dragged just as often, so they go through the same lane.
    if (master) push('master', 'set_master', { value: v });
    else push(`app:${mx.dataset.key}`, 'set_app_volume', { key: mx.dataset.key, value: v });
    if (master) { knobValue = v * 100; paintKnob(knobValue); }
  };
  apply(e);
  const move = (ev) => apply(ev);
  const up = () => {
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
  };
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', up);
});

// Reordering the cycle is done with pointer events rather than built-in HTML
// drag and drop: the page forbids text selection, and in WebView2 that ban also
// kills native drag and drop — the row simply does not move.
let rowDragged = false;

document.addEventListener('pointerdown', (e) => {
  const row = e.target.closest('.row[data-order]');
  if (!row || e.target.closest('button')) return;
  const rows = [...row.parentElement.querySelectorAll('.row[data-order]')];
  if (rows.length < 2) return;

  const from = rows.indexOf(row);
  const step = rows[1].getBoundingClientRect().top - rows[0].getBoundingClientRect().top;
  const startY = e.clientY;
  let to = from, started = false;

  const move = (ev) => {
    const dy = ev.clientY - startY;
    if (!started) {
      if (Math.abs(dy) < 4) return;   // threshold so a plain click is not counted as a drag
      started = rowDragged = true;
      row.classList.add('dragging');
      row.setPointerCapture(ev.pointerId);
    }
    row.style.transform = `translateY(${dy}px)`;
    to = Math.max(0, Math.min(rows.length - 1, from + Math.round(dy / step)));
    // The neighbours step aside to make room: you can see where the row will land.
    rows.forEach((r, i) => {
      if (r === row) return;
      const shift = (i > from && i <= to) ? -step : (i < from && i >= to) ? step : 0;
      r.style.transform = shift ? `translateY(${shift}px)` : '';
    });
  };

  const up = async () => {
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
    document.removeEventListener('pointercancel', up);
    rows.forEach((r) => { r.style.transform = ''; });
    row.classList.remove('dragging');
    if (!started) return;
    setTimeout(() => { rowDragged = false; }, 0);  // swallow the click that follows
    if (to === from) return;
    const ids = rows.map((r) => r.dataset.id);
    ids.splice(to, 0, ids.splice(from, 1)[0]);
    state = await call('reorder', { device_ids: ids });
    renderAll();
  };

  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', up);
  document.addEventListener('pointercancel', up);
});

$('scroller').addEventListener('scroll', updateFade);
window.addEventListener('resize', updateFade);
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
  if (state) renderAll();
});

// ------------------------------------------------------------------- startup
buildTicks();
buildLcd();
wireKnob();
setPainting(true);
await call('selfcheck', { from: 'ui' }).catch(() => {});
await loadLanguages();
await refresh();
openTab('devices');
if (!state.settings.onboarded) showWelcome();

// The only channel: the interface asks by itself, Python never calls
// JavaScript — such a call from a background thread hung the window.
//
// The rhythm depends on whether anyone is looking. Visible, the level meter and
// the knob need every tick. Hidden, the page used to keep asking five times a
// second for a picture nobody was drawing: measured, that traffic and the work
// behind it were most of what the program burned while idle. Hidden it asks
// once a second, and only to notice that it has been shown again.
const TICK_SEEN = 200, TICK_UNSEEN = 1000;
let polling = false;
let wasHidden = true;        // the window starts out of sight
let lastRev = -1;
let tick = TICK_SEEN;
let timer = null;

function pace(ms) {
  if (ms === tick && timer !== null) return;
  tick = ms;
  clearInterval(timer);
  timer = setInterval(poll, ms);
}

// Waking up must not wait for the slow tick, or the panel would stand frozen
// for up to a second after the window appears. Showing the window raises these
// events, and any of them is enough to ask right now. Which ones actually fire
// depends on the engine, so we listen to all of them rather than pick.
for (const ev of ['focus', 'resize', 'visibilitychange', 'pointerover'])
  window.addEventListener(ev, () => { if (tick !== TICK_SEEN) poll(); });

// A window that has just appeared puts the focus on the first thing it can, and
// the engine treats that as a step by keyboard: the mini-view button came up
// ringed and with its tooltip hanging over the desktop, as though it had been
// tabbed to. Nobody tabbed anywhere — the person clicked the tray icon — so the
// focus is handed back to the page. Anything the person could be typing into,
// such as the box that captures a shortcut, keeps it.
//
// Only on the way out of hiding. The window's focus event also fires every time
// the person comes back to it from another program, and then the focus is one
// they placed themselves — on a glyph of the icon palette, on the knob they are
// turning with the arrows — and taking it away would leave the keyboard dead.
function dropStrayFocus() {
  const el = document.activeElement;
  if (!el || el === document.body) return;
  if (el.closest('input, select, textarea, [data-capture]')) return;
  el.blur();
}

window.addEventListener('focus', () => { if (wasHidden) dropStrayFocus(); });

async function poll() {
  if (polling) return;
  polling = true;
  try {
    const m = await call('get_meter');
    // The window is hidden, so there is nothing to draw. The rest is handled as
    // usual: Python hands out the tab signal once, and it must not be missed.
    if (m.hidden) wasHidden = true;
    setPainting(!m.hidden);
    pace(m.hidden ? TICK_UNSEEN : TICK_SEEN);
    if (!m.hidden) {
      if (wasHidden) { wasHidden = false; dropStrayFocus(); }
      if (!knobBusy) knobValue = m.volume * 100;
      paintKnob(knobValue);
      lvlTarget = m.muted ? 0 : toLevel(m.peak);
      $('lcd-vol').classList.toggle('muted', !!m.muted);
    }

    // While music is playing, the middle key shows the track instead of what
    // the key does — the same thing the tray icon shows. Music stops, the
    // description comes back.
    if (m.now) {
      const track = [m.now.artist, m.now.title].filter(Boolean).join(' — ');
      if (!playBtn.dataset.tip) playBtn.dataset.tip = playBtn.title;
      playBtn.title = m.now.playing && track ? track : playBtn.dataset.tip;
    }

    if (m.tab) openTab(m.tab === 'welcome' ? 'devices' : m.tab);
    // Python itself can turn the mini view off — for example when the tray asks
    // for the mixer, which the mini view does not have. The truth about the
    // mode lives there, and the page checks itself against it.
    if (m.mini !== undefined && m.mini !== mini && !miniBusy) applyMini(m.mini);
    // While a shortcut is being captured the settings must not be redrawn — the
    // button would lose its armed state. The update is picked up on the next
    // tick.
    if (m.rev !== lastRev && !capturing) {
      if (lastRev !== -1) await refresh();
      lastRev = m.rev;
    }
  } catch (e) { /* program is shutting down */ } finally { polling = false; }
}

pace(TICK_SEEN);
