import '@fontsource-variable/manrope';
import '@fontsource/noto-sans-georgian/300.css';
import '@fontsource/noto-sans-georgian/400.css';
import '@fontsource/noto-sans-georgian/500.css';
import './styles.css';
import { App } from './app/App';
import { UI } from './ui/ui';
import { BASE } from './base';

async function boot() {
  const canvas = document.getElementById('scene') as HTMLCanvasElement;
  const params = new URLSearchParams(location.search);
  const shot = params.has('shot');
  const ui = new UI(document.getElementById('ui')!);
  const app = new App(canvas, { preserve: shot });
  app.ui = ui;
  (window as any).__app = app;
  // rendered stills (Cycles) for the gallery, if present
  fetch(`${BASE}assets/stills/index.json`)
    .then((r) => (r.ok ? r.json() : []))
    .then((list: string[]) => {
      (window as any).__STILLS__ = list;
      const loaderEl = document.querySelector('.loader') as HTMLElement | null;
      if (loaderEl && list.length) {
        loaderEl.style.backgroundImage = `linear-gradient(rgba(8,10,12,0.72), rgba(8,10,12,0.86)), url(${list[0]})`;
        loaderEl.style.backgroundSize = 'cover';
        loaderEl.style.backgroundPosition = 'center';
      }
    })
    .catch(() => {});

  let entered = false;
  const loader = ui.loader(() => {
    entered = true;
    ui.build(app);
    if (!shot) app.introFlight();
  });
  if (!shot) app.start();
  await app.load((_, f) => loader.progress(f));
  loader.ready();
  if (shot) {
    // headless mode: no animation loop; the test harness drives frames explicitly
    document.querySelector<HTMLButtonElement>('.loader .enter')?.click();
    document.querySelector('.loader')?.remove();
    const { VIEWS, view } = await import('./app/flight');
    (window as any).__VIEWS = VIEWS;
    (window as any).__view = view;
    (window as any).__FX = (await import('./app/fx')).FX;
    (window as any).__shotReady = true;
    return;
  }
  if (params.has('auto')) {
    // headless screenshots / kiosk: skip the click
    document.querySelector<HTMLButtonElement>('.loader .enter')?.click();
  }
  void entered;
}

boot();
