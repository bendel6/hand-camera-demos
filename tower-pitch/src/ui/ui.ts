import gsap from 'gsap';
import en from '../content/en.json';
import ka from '../content/ka.json';
import type { App, Mode, ScreenLabel } from '../app/App';
import { HOTSPOTS } from '../app/App';
import { CATEGORY_COLOURS, POIS, POI_META, Category } from '../app/location';
import { fmtTime } from '../app/environment';
import parkingLayout from '../content/parking-layout.json';
import { Ambient } from './audio';
import { Recorder } from './recorder';
import { BASE, MODEL_SUFFIX } from '../base';

type Lang = 'en' | 'ka';
const STRINGS: Record<Lang, any> = { en, ka };

const GALLERY = [
  { src: `${BASE}assets/pdf/render-p05.webp`, group: 'renders' },
  { src: `${BASE}assets/pdf/render-p07.webp`, group: 'renders' },
  { src: `${BASE}assets/pdf/render-p08.webp`, group: 'renders' },
  { src: `${BASE}assets/pdf/render-p06.webp`, group: 'renders' },
  { src: `${BASE}assets/pdf/montage-p09.webp`, group: 'renders' },
  { src: `${BASE}assets/pdf/montage-p10.webp`, group: 'renders' },
  { src: `${BASE}assets/pdf/render-p01.webp`, group: 'renders' },
  { src: `${BASE}assets/pdf/siteplan.webp`, group: 'renders' },
];

function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = '', html = ''): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html) e.innerHTML = html;
  return e;
}

const ICONS: Record<string, string> = {
  overview: '<svg viewBox="0 0 24 24"><path d="M4 20V9l5-3v14M11 20V4l9 4v12M2 20h20"/></svg>',
  location: '<svg viewBox="0 0 24 24"><path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/></svg>',
  structure: '<svg viewBox="0 0 24 24"><path d="M4 20h16M6 20V6M18 20V6M6 6h12M6 11h12M6 16h12M12 6v14"/></svg>',
  parking: '<svg viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="3"/><path d="M10 16V8h3a2.5 2.5 0 0 1 0 5h-3"/></svg>',
  buildup: '<svg viewBox="0 0 24 24"><path d="M4 20h16M7 20V10M17 20V6M7 10l10-4M17 6l3 2M9 3h9"/></svg>',
  greenery: '<svg viewBox="0 0 24 24"><path d="M12 21v-7M12 14c-4 0-7-3-7-7 4 0 7 3 7 7zM12 12c0-4 3-7 7-7 0 4-3 7-7 7z"/></svg>',
  gallery: '<svg viewBox="0 0 24 24"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/><circle cx="16" cy="9" r="1.5"/></svg>',
  lighting: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>',
  compare: '<svg viewBox="0 0 24 24"><path d="M12 3v18M5 7h4v10H5zM15 5h4v14h-4z"/></svg>',
};

export class UI {
  root: HTMLElement;
  lang: Lang = 'en';
  t: any = en;
  app!: App;
  private labels = new Map<string, HTMLElement>();
  private labelLayer: HTMLElement;
  private card: HTMLElement;
  private nav: HTMLElement;
  private sub: HTMLElement;
  private numbers: HTMLElement;
  private locPanel: HTMLElement;
  private phase: HTMLElement;
  private compare: HTMLElement;
  private timeLabel!: HTMLElement;
  private timeSlider!: HTMLInputElement;
  private audio = new Ambient();
  private recorder: Recorder | null = null;
  private activeMode: string = 'overview';
  private counted = false;

  constructor(root: HTMLElement) {
    this.root = root;
    this.labelLayer = el('div', 'labels');
    this.card = el('aside', 'card glass hidden');
    this.nav = el('nav', 'nav glass');
    this.sub = el('div', 'subnav glass hidden');
    this.numbers = el('div', 'numbers');
    this.locPanel = el('aside', 'locpanel glass hidden');
    this.phase = el('div', 'phase hidden');
    this.compare = el('div', 'compare hidden');
    root.append(this.labelLayer, this.numbers, this.locPanel, this.card, this.phase, this.compare, this.sub, this.nav);
  }

  // ---------------------------------------------------------------------------------------- loader
  loader(onEnter: () => void) {
    const L = el('div', 'loader');
    L.innerHTML = `
      <div class="loader-inner">
        <div class="logo">${logoSvg()}</div>
        <h1>${this.t.projectName}</h1>
        <p class="tag">${this.t.tagline}</p>
        <div class="bar"><span></span></div>
        <p class="status">${this.t.loading}</p>
        <button class="enter hidden">${this.t.enter}</button>
      </div>
      <p class="note">${this.t.conceptNote}</p>`;
    this.root.append(L);
    const bar = L.querySelector('.bar span') as HTMLElement;
    const btn = L.querySelector('.enter') as HTMLButtonElement;
    btn.onclick = () => {
      gsap.to(L, { opacity: 0, duration: 0.9, onComplete: () => L.remove() });
      onEnter();
    };
    return {
      progress: (f: number) => (bar.style.width = `${Math.round(f * 100)}%`),
      ready: () => {
        (L.querySelector('.status') as HTMLElement).classList.add('hidden');
        (L.querySelector('.bar') as HTMLElement).classList.add('hidden');
        btn.classList.remove('hidden');
        gsap.from(btn, { opacity: 0, y: 8, duration: 0.6 });
      },
    };
  }

  // ---------------------------------------------------------------------------------------- shell
  build(app: App) {
    this.app = app;
    const top = el('header', 'topbar');
    top.innerHTML = `
      <div class="brand"><span class="mark">${logoSvg()}</span><div><b class="pname"></b><small class="ptag"></small></div></div>
      <div class="tools">
        <button class="tool lang" title="EN / KA">KA</button>
        <button class="tool music" title="Music"><svg viewBox="0 0 24 24"><path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/></svg></button>
        <button class="tool rec"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="6"/></svg><span class="rec-l"></span></button>
        <button class="tool present"><svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg><span class="pres-l"></span></button>
      </div>`;
    this.root.append(top);
    top.querySelector('.lang')!.addEventListener('click', () => this.setLang(this.lang === 'en' ? 'ka' : 'en'));
    top.querySelector('.music')!.addEventListener('click', (e) => {
      const on = this.audio.toggle();
      (e.currentTarget as HTMLElement).classList.toggle('on', on);
    });
    top.querySelector('.present')!.addEventListener('click', () => this.togglePresent());
    top.querySelector('.rec')!.addEventListener('click', () => this.record());
    // the claude.ai preview frame cannot save files, so recording is only offered on the real site
    if (MODEL_SUFFIX) (top.querySelector('.rec') as HTMLElement).style.display = 'none';
    document.addEventListener('fullscreenchange', () => {
      if (!document.fullscreenElement && this.app.present) this.togglePresent(false);
    });
    window.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        this.closeCard();
        this.closeGallery();
      }
    });

    const help = el('div', 'help');
    const attr = el('div', 'attr');
    this.root.append(help, attr);
    this.buildNav();
    this.buildNumbers();
    this.buildLocation();
    this.buildCompare();
    this.setLang('en');
  }

  private buildNav() {
    const modes = ['overview', 'location', 'structure', 'parking', 'buildup', 'greenery', 'gallery', 'lighting', 'compare'];
    this.nav.innerHTML = modes.map((m) => `<button data-mode="${m}">${ICONS[m]}<span></span></button>`).join('');
    this.nav.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => this.onNav(b.dataset.mode!)));
  }

  private async onNav(mode: string) {
    this.closeCard();
    if (mode === 'gallery') return this.openGallery();
    if (mode === 'lighting') return this.toggleSub('lighting');
    this.activeMode = mode;
    this.nav.querySelectorAll('button').forEach((b) => b.classList.toggle('active', b.dataset.mode === mode));
    this.locPanel.classList.toggle('hidden', mode !== 'location');
    this.compare.classList.toggle('hidden', mode !== 'compare');
    if (mode === 'structure') this.toggleSub('structure', true);
    else this.toggleSub(null);
    if (mode === 'parking') setTimeout(() => this.openParkingCard(), 2600);
    if (mode === 'greenery') setTimeout(() => this.openHotspot('green', false), 2400);
    await this.app.setMode(mode as Mode);
  }

  private toggleSub(which: 'lighting' | 'structure' | null, force = false) {
    const cur = this.sub.dataset.which;
    if (!which || (cur === which && !force)) {
      this.sub.classList.add('hidden');
      this.sub.dataset.which = '';
      return;
    }
    this.sub.dataset.which = which;
    this.sub.classList.remove('hidden');
    const t = this.t;
    if (which === 'lighting') {
      this.sub.innerHTML = `
        <div class="seg"><button data-p="day">${t.lighting.day}</button><button data-p="golden">${t.lighting.golden}</button><button data-p="night">${t.lighting.night}</button></div>
        <label class="time"><span>${t.lighting.time}</span><input type="range" min="300" max="1410" step="1"><b></b></label>`;
      this.sub.querySelectorAll('[data-p]').forEach((b) =>
        b.addEventListener('click', () => this.app.setPreset((b as HTMLElement).dataset.p as any)),
      );
      this.timeSlider = this.sub.querySelector('input')!;
      this.timeLabel = this.sub.querySelector('.time b')!;
      this.timeSlider.value = String(Math.round(this.app.env.minutes));
      this.timeSlider.addEventListener('input', () => this.app.env.setTime(+this.timeSlider.value));
    } else {
      this.sub.innerHTML = `
        <div class="seg">
          <button class="ex">${this.app.effects.exploded ? t.structure.assemble : t.structure.explode}</button>
          <button class="xr">${this.app.effects.xray ? t.structure.solid : t.structure.xray}</button>
        </div>`;
      this.sub.querySelector('.ex')!.addEventListener('click', async (e) => {
        const b = e.currentTarget as HTMLElement;
        const on = !this.app.effects.exploded;
        b.textContent = on ? t.structure.assemble : t.structure.explode;
        (this.sub.querySelector('.xr') as HTMLElement).textContent = t.structure.xray;
        await this.app.explode(on);
      });
      this.sub.querySelector('.xr')!.addEventListener('click', (e) => {
        const b = e.currentTarget as HTMLElement;
        const on = !this.app.effects.xray;
        b.textContent = on ? t.structure.solid : t.structure.xray;
        (this.sub.querySelector('.ex') as HTMLElement).textContent = t.structure.explode;
        this.app.xray(on);
      });
    }
  }

  private buildNumbers() {
    this.numbers.innerHTML = ['height', 'floors', 'area', 'parking', 'green', 'plot']
      .map((k) => `<div class="num" data-k="${k}"><b>0</b><span></span></div>`)
      .join('');
  }

  private countNumbers() {
    const vals: Record<string, [number, string]> = {
      height: [115, ' m'],
      floors: [46, ''],
      area: [37400, ' m²'],
      parking: [350, ''],
      green: [18, '%'],
      plot: [5317, ' m²'],
    };
    this.numbers.querySelectorAll('.num').forEach((n, i) => {
      const k = (n as HTMLElement).dataset.k!;
      const b = n.querySelector('b')!;
      const [v, unit] = vals[k];
      const s = { v: 0 };
      gsap.to(s, {
        v,
        duration: 2.2,
        delay: 0.15 * i,
        ease: 'power2.out',
        onUpdate: () => {
          const x = Math.round(s.v);
          b.textContent = k === 'floors' ? `${Math.round((x / 46) * 30)} + ${Math.round((x / 46) * 16)}` : `${k === 'area' ? '≈' : ''}${x.toLocaleString('en-US')}${unit}`;
        },
      });
    });
    gsap.from(this.numbers, { opacity: 0, y: -10, duration: 0.8 });
  }

  private buildLocation() {
    const cats = Object.keys(CATEGORY_COLOURS) as Category[];
    this.locPanel.innerHTML = `
      <h3 class="lt"></h3>
      <p class="sum"></p>
      <div class="chips">${cats.map((c) => `<button class="chip on" data-c="${c}" style="--c:${CATEGORY_COLOURS[c]}"><i></i><span></span></button>`).join('')}</div>
      <button class="tourbtn"></button>
      <ul class="poilist"></ul>
      <p class="fine"></p>`;
    this.locPanel.querySelectorAll('.chip').forEach((c) =>
      c.addEventListener('click', () => {
        const on = !c.classList.contains('on');
        c.classList.toggle('on', on);
        this.app.location.setCategory((c as HTMLElement).dataset.c as Category, on);
        this.renderPoiList();
      }),
    );
    this.locPanel.querySelector('.tourbtn')!.addEventListener('click', () => {
      if (this.app.touring) {
        this.app.stopTour();
        this.updateLocationTexts();
      } else {
        this.app.autoTour((id) => (id ? this.openPoi(id, false) : this.closeCard()));
        (this.locPanel.querySelector('.tourbtn') as HTMLElement).textContent = this.t.location.stopTour;
      }
    });
  }

  private renderPoiList() {
    const ul = this.locPanel.querySelector('.poilist')!;
    const enabled = this.app?.location.enabled;
    ul.innerHTML = POIS.filter((p) => !enabled || enabled.has(p.category))
      .slice(0, 14)
      .map((p) => `<li data-id="${p.id}" style="--c:${CATEGORY_COLOURS[p.category]}"><i></i><span>${this.poiName(p)}</span><b>${this.poiDistance(p)}</b></li>`)
      .join('');
    ul.querySelectorAll('li').forEach((li) => li.addEventListener('click', () => this.openPoi((li as HTMLElement).dataset.id!, true)));
  }

  private poiName(p: any) {
    return this.lang === 'ka' && p.name_ka ? p.name_ka : p.name_en;
  }

  private poiDistance(p: any) {
    const u = this.t.units;
    const m = p.walk_m && p.walk_m < 1500 ? p.walk_m : p.drive_m ?? p.straight_m;
    return m < 1000 ? `${Math.round(m / 10) * 10} ${u.m}` : `${(m / 1000).toFixed(1)} ${u.km}`;
  }

  private updateLocationTexts() {
    const t = this.t.location;
    const s = POI_META.summary;
    (this.locPanel.querySelector('.lt') as HTMLElement).textContent = t.title;
    (this.locPanel.querySelector('.sum') as HTMLElement).textContent = t.summary
      .replace('{centre}', s.city_centre_drive_min)
      .replace('{airport}', `≈${s.airport_drive_min}`)
      .replace('{metro}', s.nearest_metro_walk_m);
    this.locPanel.querySelectorAll('.chip').forEach((c) => (c.querySelector('span')!.textContent = t.categories[(c as HTMLElement).dataset.c!]));
    (this.locPanel.querySelector('.tourbtn') as HTMLElement).textContent = this.app?.touring ? t.stopTour : t.tour;
    (this.locPanel.querySelector('.fine') as HTMLElement).textContent = t.estimates;
    this.renderPoiList();
  }

  private buildCompare() {
    this.compare.innerHTML = `<div class="line"></div><div class="knob"><svg viewBox="0 0 24 24"><path d="M9 6l-6 6 6 6M15 6l6 6-6 6"/></svg></div><span class="lb l"></span><span class="lb r"></span>`;
    const knob = this.compare.querySelector('.knob') as HTMLElement;
    let drag = false;
    const move = (x: number) => {
      const f = Math.min(0.95, Math.max(0.05, x / window.innerWidth));
      this.app.compareX = f;
      this.compare.style.setProperty('--x', `${f * 100}%`);
    };
    knob.addEventListener('pointerdown', (e) => {
      drag = true;
      knob.setPointerCapture(e.pointerId);
    });
    knob.addEventListener('pointermove', (e) => drag && move(e.clientX));
    knob.addEventListener('pointerup', () => (drag = false));
    this.compare.style.setProperty('--x', '50%');
  }

  // ---------------------------------------------------------------------------------------- language
  setLang(lang: Lang) {
    this.lang = lang;
    this.t = STRINGS[lang];
    document.documentElement.lang = lang;
    document.body.classList.toggle('ka', lang === 'ka');
    const t = this.t;
    (this.root.querySelector('.lang') as HTMLElement).textContent = lang === 'en' ? 'ქა' : 'EN';
    (this.root.querySelector('.pname') as HTMLElement).textContent = t.projectName;
    (this.root.querySelector('.ptag') as HTMLElement).textContent = t.tagline;
    (this.root.querySelector('.rec-l') as HTMLElement).textContent = t.ui.record;
    (this.root.querySelector('.pres-l') as HTMLElement).textContent = t.ui.present;
    (this.root.querySelector('.help') as HTMLElement).textContent = t.ui.help;
    (this.root.querySelector('.attr') as HTMLElement).textContent = t.ui.attribution;
    this.nav.querySelectorAll('button').forEach((b) => (b.querySelector('span')!.textContent = t.nav[b.dataset.mode!]));
    this.numbers.querySelectorAll('.num').forEach((n) => (n.querySelector('span')!.textContent = t.numbers[(n as HTMLElement).dataset.k!]));
    (this.compare.querySelector('.lb.l') as HTMLElement).textContent = t.compare.before;
    (this.compare.querySelector('.lb.r') as HTMLElement).textContent = t.compare.after;
    this.updateLocationTexts();
    for (const [k, e] of this.labels) this.fillLabel(k, e);
    if (this.sub.dataset.which) this.toggleSub(this.sub.dataset.which as any, true);
  }

  // ---------------------------------------------------------------------------------------- cards
  openCard(html: string) {
    this.card.innerHTML = `<button class="x" aria-label="close">×</button>${html}`;
    this.card.querySelector('.x')!.addEventListener('click', () => this.closeCard());
    this.card.classList.remove('hidden');
    gsap.fromTo(this.card, { opacity: 0, x: 30 }, { opacity: 1, x: 0, duration: 0.5, ease: 'power2.out' });
    this.card.querySelectorAll('img').forEach((img) => img.addEventListener('click', () => this.openGallery(img.getAttribute('src')!.replace('_thumb', ''))));
  }

  closeCard() {
    if (this.card.classList.contains('hidden')) return;
    gsap.to(this.card, { opacity: 0, x: 30, duration: 0.3, onComplete: () => this.card.classList.add('hidden') });
  }

  openHotspot(id: string, fly = true) {
    const h = HOTSPOTS.find((x) => x.id === id);
    const t = this.t.hotspots[id];
    if (!h || !t) return;
    if (fly) this.app.focusHotspot(id);
    const img = h.image ? `<img src="${h.image.replace('.webp', '_thumb.webp')}" alt="">` : '';
    this.openCard(`<h2>${t.title}</h2><p>${t.text}</p>${img}`);
  }

  openLayer(id: string) {
    const t = this.t.layers[id];
    this.openCard(`<h2>${t.title}</h2><p>${t.text}</p>`);
    const nodes = this.app.effects.meshesOfLayer(id);
    this.app.post.outline.selection.set(nodes.flatMap((n) => {
      const out: any[] = [];
      n.traverse((o: any) => o.isMesh && out.push(o));
      return out;
    }));
  }

  openParkingCard() {
    const t = this.t.parking;
    const meta = (parkingLayout as any).meta;
    const rows = meta.levels
      .map((l: any) => `<div class="lvl" style="--c:${l.colour}"><b>${l.name}</b><span>${t.levels[l.name]}</span><em>${l.bays} ${t.bays}</em><small>${l.ev} ${t.ev} · ${l.accessible} ${t.accessible}</small><button data-l="${l.name}">${t.enter}</button></div>`)
      .join('');
    this.openCard(`<h2><span class="count">0</span> · ${t.title.replace('350 ', '')}</h2><p>${t.text}</p><div class="levels">${rows}</div>`);
    const c = this.card.querySelector('.count') as HTMLElement;
    const s = { v: 0 };
    gsap.to(s, { v: 350, duration: 2.6, ease: 'power2.out', onUpdate: () => (c.textContent = String(Math.round(s.v))) });
    this.card.querySelectorAll('.lvl button').forEach((b) => b.addEventListener('click', () => this.flyLevel((b as HTMLElement).dataset.l!)));
  }

  private flyLevel(level: string) {
    const z = { B1: -3.6, B2: -7.2, B3: -10.8 }[level]!;
    this.app.effects.showLevel(level);
    this.onParkingLevel(level);
    import('../app/flight').then(({ view }) => this.app.flight.to(view(10, 10, z + 9, 44, 40, z + 0.5), 2.4, { arc: 6 }));
  }

  onParkingLevel(level: string) {
    this.card.querySelectorAll('.lvl').forEach((e) => e.classList.toggle('on', (e.querySelector('b') as HTMLElement).textContent === level));
    for (const [k, e] of this.labels) if (k.startsWith('level:')) e.classList.toggle('cur', k === `level:${level}`);
  }

  openPoi(id: string, fly = true) {
    const p = POIS.find((x) => x.id === id);
    if (!p) return;
    if (fly) this.app.focusPoi(id);
    const t = this.t.location;
    const u = this.t.units;
    const fmt = (m: number | null) => (m == null ? '—' : m < 1000 ? `${Math.round(m / 10) * 10} ${u.m}` : `${(m / 1000).toFixed(1)} ${u.km}`);
    const rows = [
      p.walk_m != null && p.walk_m < 6000 ? `<div><b>${p.walk_min} ${u.min}</b><span>${t.walk} · ${fmt(p.walk_m)}</span></div>` : '',
      p.drive_m != null ? `<div><b>${p.approximate ? '≈' : ''}${p.drive_min} ${u.min}</b><span>${t.drive} · ${fmt(p.drive_m)}</span></div>` : '',
      `<div><b>${fmt(p.straight_m)}</b><span>${t.straight}</span></div>`,
    ].join('');
    this.openCard(`<p class="cat" style="--c:${CATEGORY_COLOURS[p.category]}">${t.categories[p.category]}</p><h2>${this.poiName(p)}</h2><div class="stats">${rows}</div><p class="fine">${t.estimates}</p>`);
  }

  showPhase(i: number) {
    if (i < 0) {
      gsap.to(this.phase, { opacity: 0, duration: 0.6, onComplete: () => this.phase.classList.add('hidden') });
      return;
    }
    this.phase.classList.remove('hidden');
    this.phase.innerHTML = `<small>${i + 1} / 5</small><span>${this.t.buildup.phases[i]}</span>`;
    gsap.fromTo(this.phase, { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.6 });
  }

  // ---------------------------------------------------------------------------------------- gallery
  openGallery(start?: string) {
    const stills = (window as any).__STILLS__ as string[] | undefined;
    const items = [...(stills ?? []).map((s) => ({ src: s, group: 'stills' })), ...GALLERY];
    let i = Math.max(0, items.findIndex((x) => x.src === start));
    const G = el('div', 'gallery');
    G.innerHTML = `<button class="x">×</button><button class="nv prev">‹</button><img alt=""><button class="nv next">›</button><div class="cap"></div>`;
    const img = G.querySelector('img')!;
    const cap = G.querySelector('.cap') as HTMLElement;
    const show = () => {
      img.src = items[i].src;
      cap.textContent = `${this.t.gallery[items[i].group]} · ${i + 1} / ${items.length}`;
      gsap.fromTo(img, { opacity: 0 }, { opacity: 1, duration: 0.4 });
    };
    G.querySelector('.prev')!.addEventListener('click', () => { i = (i + items.length - 1) % items.length; show(); });
    G.querySelector('.next')!.addEventListener('click', () => { i = (i + 1) % items.length; show(); });
    G.querySelector('.x')!.addEventListener('click', () => this.closeGallery());
    G.addEventListener('keydown', () => {});
    this.root.append(G);
    show();
    gsap.from(G, { opacity: 0, duration: 0.4 });
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'ArrowRight') { i = (i + 1) % items.length; show(); }
      if (e.key === 'ArrowLeft') { i = (i + items.length - 1) % items.length; show(); }
    };
    window.addEventListener('keydown', onKey);
    (G as any).__off = () => window.removeEventListener('keydown', onKey);
  }

  closeGallery() {
    const G = this.root.querySelector('.gallery') as any;
    if (!G) return;
    G.__off?.();
    gsap.to(G, { opacity: 0, duration: 0.3, onComplete: () => G.remove() });
  }

  // ---------------------------------------------------------------------------------------- present / record
  togglePresent(force?: boolean) {
    const on = force ?? !this.app.present;
    this.app.present = on;
    document.body.classList.toggle('presenting', on);
    if (on) {
      document.documentElement.requestFullscreen?.().catch(() => {});
      this.toast(this.t.ui.presentHint);
    } else if (document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  }

  async record() {
    if (this.recorder?.active) return;
    this.recorder = new Recorder(this.app.renderer.domElement);
    const btn = this.root.querySelector('.rec') as HTMLElement;
    btn.classList.add('on');
    (btn.querySelector('.rec-l') as HTMLElement).textContent = this.t.ui.recording;
    document.body.classList.add('recording');
    await this.recorder.recordTour(this.app);
    btn.classList.remove('on');
    (btn.querySelector('.rec-l') as HTMLElement).textContent = this.t.ui.record;
    document.body.classList.remove('recording');
  }

  toast(msg: string) {
    const T = el('div', 'toast glass', msg);
    this.root.append(T);
    gsap.fromTo(T, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.4 });
    gsap.to(T, { opacity: 0, delay: 3.2, duration: 0.6, onComplete: () => T.remove() });
  }

  // ---------------------------------------------------------------------------------------- labels
  private fillLabel(key: string, e: HTMLElement) {
    const [kind, id] = key.split(':');
    const t = this.t;
    if (kind === 'hot') e.innerHTML = `<i class="pulse"></i><span>${t.hotspots[id]?.title ?? id}</span>`;
    if (kind === 'layer') e.innerHTML = `<span>${t.layers[id]?.title ?? id}</span>`;
    if (kind === 'level') {
      const l = (parkingLayout as any).meta.levels.find((x: any) => x.name === id);
      e.innerHTML = `<b style="--c:${l.colour}">${id}</b><span>${l.bays} ${t.parking.bays}</span>`;
    }
    if (kind === 'poi') {
      const p = POIS.find((x) => x.id === id)!;
      e.style.setProperty('--c', CATEGORY_COLOURS[p.category]);
      e.innerHTML = `<span>${this.poiName(p)}</span><small>${this.poiDistance(p)}${p.walk_min != null && p.walk_m! < 1500 ? ` · ${p.walk_min} ${t.units.min} ${t.location.walk}` : p.drive_min != null ? ` · ${p.approximate ? '≈' : ''}${p.drive_min} ${t.units.min} ${t.location.drive}` : ''}</small>`;
    }
    if (kind === 'ring') {
      const [label, k] = id.split('|');
      e.innerHTML = `<b>${label}</b><span>${t.location.rings[k]}</span>`;
    }
    if (kind === 'site') e.innerHTML = `<span>${t.projectName}</span>`;
  }

  positionLabels(list: ScreenLabel[]) {
    const seen = new Set<string>();
    // greedy de-overlap for POI labels: nearer first
    const placed: Array<[number, number, number, number]> = [];
    const sorted = [...list].sort((a, b) => (a.key.startsWith('poi') ? 1 : 0) - (b.key.startsWith('poi') ? 1 : 0) || a.depth - b.depth);
    for (const L of sorted) {
      seen.add(L.key);
      let e = this.labels.get(L.key);
      if (!e) {
        const kind = L.key.split(':')[0];
        e = el('div', `lbl lbl-${kind}`);
        this.fillLabel(L.key, e);
        const [k, id] = L.key.split(':');
        if (k === 'hot') e.addEventListener('click', () => this.openHotspot(id));
        if (k === 'layer') e.addEventListener('click', () => this.openLayer(id));
        if (k === 'poi') e.addEventListener('click', () => this.openPoi(id));
        if (k === 'level') e.addEventListener('click', () => this.flyLevel(id));
        this.labelLayer.append(e);
        this.labels.set(L.key, e);
      }
      let vis = L.visible;
      if (vis && L.key.startsWith('poi')) {
        const w = 150, h = 34;
        const box: [number, number, number, number] = [L.x - w / 2, L.y - h, L.x + w / 2, L.y];
        if (placed.some((b) => !(box[2] < b[0] || box[0] > b[2] || box[3] < b[1] || box[1] > b[3]))) vis = false;
        else placed.push(box);
      }
      e.style.transform = `translate3d(${L.x.toFixed(1)}px, ${L.y.toFixed(1)}px, 0)`;
      e.classList.toggle('off', !vis);
    }
    for (const [k, e] of this.labels) if (!seen.has(k)) e.classList.add('off');
  }

  tick(app: App) {
    if (this.timeLabel) {
      this.timeLabel.textContent = fmtTime(app.env.minutes);
      if (document.activeElement !== this.timeSlider) this.timeSlider.value = String(Math.round(app.env.minutes));
    }
    if (!this.counted) {
      this.counted = true;
      this.countNumbers();
    }
  }
}

function logoSvg() {
  return `<svg viewBox="0 0 32 32"><path d="M9 27V9l6-3v21M17 27V13l6-2v16M5 27h22" fill="none" stroke="currentColor" stroke-width="2"/></svg>`;
}
