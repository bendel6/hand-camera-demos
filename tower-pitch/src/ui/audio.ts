/** Soft generative ambient pad (Web Audio, no files). Off by default. */
export class Ambient {
  private ctx: AudioContext | null = null;
  private master: GainNode | null = null;
  private timer: number | null = null;
  on = false;

  toggle(): boolean {
    this.on ? this.stop() : this.start();
    return this.on;
  }

  private start() {
    this.on = true;
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0;
      const verb = this.ctx.createConvolver();
      verb.buffer = this.impulse(3.5);
      const wet = this.ctx.createGain();
      wet.gain.value = 0.55;
      this.master.connect(this.ctx.destination);
      this.master.connect(verb).connect(wet).connect(this.ctx.destination);
    }
    this.ctx.resume();
    this.master!.gain.linearRampToValueAtTime(0.16, this.ctx.currentTime + 2.5);
    const chords = [
      [57, 60, 64, 67, 71],
      [53, 57, 60, 64, 67],
      [55, 59, 62, 66, 69],
      [52, 55, 59, 62, 66],
    ];
    let i = 0;
    const play = () => {
      if (!this.on || !this.ctx) return;
      for (const n of chords[i % chords.length]) this.voice(n, 9);
      i++;
    };
    play();
    this.timer = window.setInterval(play, 8000);
  }

  private stop() {
    this.on = false;
    if (this.timer) clearInterval(this.timer);
    if (this.ctx && this.master) this.master.gain.linearRampToValueAtTime(0, this.ctx.currentTime + 1.5);
  }

  private voice(midi: number, dur: number) {
    const ctx = this.ctx!;
    const f = 440 * Math.pow(2, (midi - 69) / 12);
    const t = ctx.currentTime;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(0.05, t + 2.8);
    g.gain.linearRampToValueAtTime(0, t + dur);
    const lp = ctx.createBiquadFilter();
    lp.type = 'lowpass';
    lp.frequency.value = 1400;
    for (const det of [-6, 5]) {
      const o = ctx.createOscillator();
      o.type = 'triangle';
      o.frequency.value = f;
      o.detune.value = det;
      o.connect(lp);
      o.start(t);
      o.stop(t + dur + 0.1);
    }
    lp.connect(g).connect(this.master!);
  }

  private impulse(sec: number) {
    const ctx = this.ctx!;
    const len = ctx.sampleRate * sec;
    const b = ctx.createBuffer(2, len, ctx.sampleRate);
    for (let c = 0; c < 2; c++) {
      const d = b.getChannelData(c);
      for (let i = 0; i < len; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / len, 2.6);
    }
    return b;
  }
}
