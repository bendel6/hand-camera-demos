import type { App } from '../app/App';
import { VIEWS, view } from '../app/flight';

/** Records a ~30 s scripted flythrough of the canvas to MP4 (where supported) or WebM and downloads it. */
export class Recorder {
  active = false;
  constructor(private canvas: HTMLCanvasElement) {}

  private mime(): { type: string; ext: string } {
    const prefs = [
      { type: 'video/mp4;codecs=avc1.640033', ext: 'mp4' },
      { type: 'video/mp4', ext: 'mp4' },
      { type: 'video/webm;codecs=vp9', ext: 'webm' },
      { type: 'video/webm', ext: 'webm' },
    ];
    return prefs.find((p) => (window as any).MediaRecorder?.isTypeSupported(p.type)) ?? prefs[3];
  }

  async recordTour(app: App) {
    this.active = true;
    const { type, ext } = this.mime();
    const stream = this.canvas.captureStream(60);
    const rec = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 24_000_000 });
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const done = new Promise<void>((res) => (rec.onstop = () => res()));
    document.body.classList.add('presenting');
    rec.start(250);
    const f = app.flight;
    await f.to(VIEWS.overview, 3.5, { arc: 0 });
    await f.orbit(app.controls.target.clone(), 190, 60, -2.1, 0.9, 8);
    await f.to(VIEWS.entrance, 4, { arc: 10 });
    await f.to(VIEWS.facade, 4, { arc: 20 });
    await f.to(view(-160, -260, 260, 40, 30, 60), 5, { arc: 30 });
    await new Promise((r) => setTimeout(r, 600));
    rec.stop();
    await done;
    document.body.classList.remove('presenting');
    const blob = new Blob(chunks, { type: type.split(';')[0] });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `kazbegi23-tour.${ext}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    this.active = false;
  }
}
