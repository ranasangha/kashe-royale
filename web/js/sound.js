/* ============================================================
   PokerStack sound — generated with the Web Audio API.
   No audio files, no external assets.
   ============================================================ */

const MUTE_KEY = "pokerstack.muted";
const MUSIC_KEY = "pokerstack.music";

/* ---------------------------------------------------------------- music bed
   A slow "private casino lounge" loop, synthesised on the fly: a I-vi-ii-V
   pad progression, a soft root bass and a sparse vibraphone-style sparkle.
   Nothing is downloaded, so the game still works fully offline.
   -------------------------------------------------------------------------- */
const MUSIC_BPM = 84;                       // one chord per bar (4 beats)
const BEAT = 60 / MUSIC_BPM;
const BAR = BEAT * 4;
const MUSIC_LEVEL = 1.0;                    // gain of the music bus (master sits at 0.18)
const SCHEDULE_AHEAD = 0.6;                 // seconds of audio pre-scheduled
const TICK_MS = 60;                         // scheduler wakeup interval

const midiToFreq = (midi) => 440 * Math.pow(2, (midi - 69) / 12);

// Each bar: bass root + four pad tones (MIDI note numbers).
const CHORDS = [
  { bass: 48, tones: [60, 64, 67, 71] }, // Cmaj7  (I)
  { bass: 45, tones: [60, 64, 67, 69] }, // Am7    (vi)
  { bass: 50, tones: [62, 65, 69, 72] }, // Dm7    (ii)
  { bass: 43, tones: [59, 62, 65, 67] }, // G7     (V)
];

export class PokerSound {
  constructor() {
    this.ctx = null;
    this.master = null;
    this.muted = false;
    this.musicOn = false;
    this.musicTimer = null;
    this.musicGraph = null;
    this.musicBarIndex = 0;
    this.nextBarTime = null;
    try {
      this.muted = localStorage.getItem(MUTE_KEY) === "1";
      this.musicOn = localStorage.getItem(MUSIC_KEY) === "1";
    } catch (error) {
      this.muted = false;
      this.musicOn = false;
    }
  }

  ensure() {
    if (this.muted) return false;
    if (!this.ctx) {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      if (!AudioContext) return false;
      this.ctx = new AudioContext();
      this.master = this.ctx.createGain();
      this.master.gain.value = 0.18;
      this.master.connect(this.ctx.destination);
    }
    if (this.ctx.state === "suspended") this.ctx.resume().catch(() => {});
    return true;
  }

  setMuted(value) {
    this.muted = Boolean(value);
    try {
      localStorage.setItem(MUTE_KEY, this.muted ? "1" : "0");
    } catch (error) {
      /* ignore */
    }
    if (this.muted && this.ctx) {
      this.master.gain.setTargetAtTime(0, this.ctx.currentTime, 0.02);
    } else if (this.ctx) {
      this.master.gain.setTargetAtTime(0.18, this.ctx.currentTime, 0.02);
      if (this.musicOn) this._musicStart();
    }
  }

  toggle() {
    this.setMuted(!this.muted);
    if (!this.muted) this.click();
    return this.muted;
  }

  tone(frequency, duration, type = "sine", gain = 0.2, delay = 0, slide = 0) {
    if (!this.ensure()) return;
    const now = this.ctx.currentTime + delay;
    const osc = this.ctx.createOscillator();
    const env = this.ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, now);
    if (slide) osc.frequency.exponentialRampToValueAtTime(Math.max(40, frequency + slide), now + duration);
    env.gain.setValueAtTime(0.0001, now);
    env.gain.exponentialRampToValueAtTime(gain, now + 0.012);
    env.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    osc.connect(env);
    env.connect(this.master);
    osc.start(now);
    osc.stop(now + duration + 0.02);
  }

  noise(duration, gain = 0.08, delay = 0, highpass = 900) {
    if (!this.ensure()) return;
    const length = Math.max(1, Math.floor(this.ctx.sampleRate * duration));
    const buffer = this.ctx.createBuffer(1, length, this.ctx.sampleRate);
    const data = buffer.getChannelData(0);
    for (let i = 0; i < length; i += 1) {
      data[i] = (Math.random() * 2 - 1) * (1 - i / length);
    }
    const source = this.ctx.createBufferSource();
    source.buffer = buffer;
    const filter = this.ctx.createBiquadFilter();
    filter.type = "highpass";
    filter.frequency.value = highpass;
    const env = this.ctx.createGain();
    env.gain.value = gain;
    source.connect(filter);
    filter.connect(env);
    env.connect(this.master);
    const now = this.ctx.currentTime + delay;
    source.start(now);
    source.stop(now + duration);
  }

  click() {
    this.tone(620, 0.045, "triangle", 0.08, 0, -160);
  }

  deal() {
    this.noise(0.09, 0.075, 0, 1500);
    this.tone(320, 0.05, "triangle", 0.06, 0, -80);
  }

  chip() {
    this.tone(1180, 0.045, "square", 0.035, 0, -240);
    this.tone(760, 0.06, "triangle", 0.06, 0.02, -120);
  }

  flip() {
    this.noise(0.12, 0.06, 0, 800);
    this.tone(440, 0.08, "sine", 0.04, 0, 120);
  }

  check() {
    this.tone(420, 0.06, "sine", 0.09);
    this.tone(560, 0.08, "sine", 0.06, 0.05);
  }

  fold() {
    this.tone(180, 0.09, "sine", 0.07, 0, -40);
  }

  raise() {
    this.tone(520, 0.06, "triangle", 0.08);
    this.tone(780, 0.09, "triangle", 0.06, 0.05);
  }

  win() {
    if (!this.ensure()) return;
    [523.25, 659.25, 783.99, 1046.5].forEach((note, index) => {
      this.tone(note, 0.42, "triangle", 0.1, index * 0.09);
    });
    this.tone(261.63, 0.7, "sine", 0.06, 0.02);
  }

  error() {
    this.tone(150, 0.14, "sawtooth", 0.045, 0, -30);
  }

  turn() {
    this.tone(880, 0.06, "sine", 0.045);
    this.tone(1108, 0.08, "sine", 0.035, 0.06);
  }

  /* ------------------------------------------------------------ music --- */

  /** Called on the first user gesture: unlocks audio and starts the bed if enabled. */
  unlock() {
    const ok = this.ensure();
    if (ok && this.musicOn && !this.muted) this._musicStart();
    return ok;
  }

  /** Turn the background music on or off. Returns the new state. */
  toggleMusic() {
    this.enableMusic(!this.musicOn);
    return this.musicOn;
  }

  enableMusic(value) {
    this.musicOn = Boolean(value);
    try {
      localStorage.setItem(MUSIC_KEY, this.musicOn ? "1" : "0");
    } catch (error) {
      /* ignore */
    }
    if (!this.musicOn) {
      this._musicStop();
      return false;
    }
    // Browsers only allow audio after a gesture, and a muted master is silent:
    // remember the choice and start as soon as either blocker clears.
    if (this.muted || !this.ensure()) return true;
    this._musicStart();
    return true;
  }

  _musicStart() {
    if (this.musicTimer || !this.musicOn || this.muted) return;
    if (!this.ensure()) return;

    const gain = this.ctx.createGain();
    const filter = this.ctx.createBiquadFilter();
    filter.type = "lowpass";
    filter.frequency.value = 1800;
    filter.Q.value = 0.3;
    filter.connect(gain);
    gain.connect(this.master);
    const now = this.ctx.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(MUSIC_LEVEL, now + 1.4);
    this.musicGraph = { gain, filter };
    this.nextBarTime = null;
    this.musicTimer = window.setInterval(() => this._musicTick(), TICK_MS);
  }

  _musicStop() {
    if (this.musicTimer) {
      window.clearInterval(this.musicTimer);
      this.musicTimer = null;
    }
    const graph = this.musicGraph;
    this.musicGraph = null;
    this.nextBarTime = null;
    if (!graph || !this.ctx) return;
    const now = this.ctx.currentTime;
    graph.gain.gain.cancelScheduledValues(now);
    graph.gain.gain.setValueAtTime(Math.max(graph.gain.gain.value, 0.0001), now);
    graph.gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.5);
    // Notes already scheduled keep ringing into this bus; disconnect after the
    // longest bar has finished so nothing leaks.
    window.setTimeout(() => {
      try {
        graph.gain.disconnect();
        graph.filter.disconnect();
      } catch (error) {
        /* already gone */
      }
    }, Math.ceil(BAR * 1000) + 2000);
  }

  /** Lookahead scheduler: keeps the next bar(s) queued just ahead of the clock. */
  _musicTick() {
    if (!this.musicOn || !this.ctx || !this.musicGraph) return;
    if (this.muted) return;
    if (typeof document !== "undefined" && document.hidden) return; // no work in a background tab
    const now = this.ctx.currentTime;
    if (this.nextBarTime === null) this.nextBarTime = now + 0.2;
    if (this.nextBarTime < now - 1) this.nextBarTime = now + 0.2; // tab slept: resync
    while (this.nextBarTime < now + SCHEDULE_AHEAD) {
      this._scheduleBar(this.nextBarTime);
      this.nextBarTime += BAR;
    }
  }

  /** Schedules one bar (chord pad + bass + sparkle) starting at `when`. */
  _scheduleBar(when) {
    const chord = CHORDS[this.musicBarIndex % CHORDS.length];
    this.musicBarIndex += 1;
    const dest = this.musicGraph.filter;
    // Pad: four voices, slow attack, release that overlaps the next chord.
    chord.tones.forEach((midi, index) => {
      this._pad(midiToFreq(midi), when, BAR * 1.05, dest, 0.036 - index * 0.004);
    });
    // Bass: root note, one and a half beats.
    this._pad(midiToFreq(chord.bass), when, BEAT * 1.8, dest, 0.075);
    // Sparse sparkle so the loop never sounds mechanical.
    if (Math.random() < 0.8) {
      this._sparkle(midiToFreq(chord.tones[1] + 12), when + BEAT * 2, dest);
    }
    if (Math.random() < 0.45) {
      this._sparkle(midiToFreq(chord.tones[3] + 12), when + BEAT * 3.5, dest);
    }
  }

  _pad(frequency, start, duration, dest, peak) {
    const now = start;
    const oscA = this.ctx.createOscillator();
    const oscB = this.ctx.createOscillator();
    oscA.type = "sine";
    oscA.frequency.value = frequency;
    oscB.type = "triangle";
    oscB.frequency.value = frequency;
    oscB.detune.value = 8;
    const env = this.ctx.createGain();
    const attack = Math.min(0.6, duration * 0.35);
    env.gain.setValueAtTime(0.0001, now);
    env.gain.exponentialRampToValueAtTime(peak, now + attack);
    env.gain.setValueAtTime(peak, now + duration * 0.6);
    env.gain.exponentialRampToValueAtTime(0.0001, now + duration);
    oscA.connect(env);
    oscB.connect(env);
    env.connect(dest);
    oscA.start(now);
    oscB.start(now);
    oscA.stop(now + duration + 0.05);
    oscB.stop(now + duration + 0.05);
  }

  _sparkle(frequency, start, dest) {
    const osc = this.ctx.createOscillator();
    osc.type = "sine";
    osc.frequency.value = frequency;
    const env = this.ctx.createGain();
    const duration = 1.4;
    env.gain.setValueAtTime(0.0001, start);
    env.gain.exponentialRampToValueAtTime(0.05, start + 0.015);
    env.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    osc.connect(env);
    env.connect(dest);
    osc.start(start);
    osc.stop(start + duration + 0.05);
  }
}
