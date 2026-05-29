// guided-brew-mode.js — guidedBrewMode Alpine component (Phase 11 / Plan 04, extended Phase 20 / Plan 05).
//
// CSP-build compliant (docs/decisions/0001): registered via Alpine.data,
// string x-data reference, config via data-* attributes. No eval.
//
// Responsibilities:
//   1. Read recipe steps from data-steps attribute (JSON.parse — no eval).
//   2. Timer: wall-clock-truth (Date.now() - _startTimestamp), not an incrementing counter.
//      _resync() on visibilitychange so the timer self-corrects on wake from screen sleep.
//   3. Audio: AudioContext synthesized chime (unlocked in Start button handler).
//   4. Vibration: navigator.vibrate — fails silently on iOS.
//   5. Wake lock: navigator.wakeLock.request('screen') + NoSleep.js fallback.
//   6. Cue prefs: read/write localStorage 'snobbery:gbm:cues'.
//   7. Coaching getters: coachingLine, stepTypeBadge, stepNote, stepWaterTemp, preCueCountdown, isPreCue.
//   8. Tap-to-mark: markFirstDrip / clearFirstDrip; bloom auto-derives on Bloom step completion.
//   9. finishBrewing(): carries first_drip + bloom_time + brew_time into /brew/new.

document.addEventListener('alpine:init', () => {
  Alpine.data('guidedBrewMode', () => ({
    // --- state ---
    steps: [],
    currentStepIndex: 0,
    isRunning: false,
    isPaused: false,
    isDone: false,
    remainingSeconds: 0,
    elapsedTotalSeconds: 0,
    cuePrefs: { chime: true, vibrate: true },
    wakeLockState: 'none', // 'held' | 'fallback' | 'none'

    // Wall-clock timer state (Phase 20 D-15)
    _startTimestamp: null,   // Date.now() at brew start — wall-clock truth
    _pausedOffset: 0,        // accumulated pause duration in seconds
    _pausedAt: null,         // Date.now() at last pause

    // Capture state (Phase 20 D-12..D-14)
    firstDripSeconds: null,  // tap-to-mark; null = not yet marked
    bloomTimeSeconds: null,  // auto-set when Bloom step transitions

    // private
    recipeId: '',
    coffeeId: '',
    _timer: null,
    audioCtx: null,
    wakeLockSentinel: null,
    noSleep: null,
    _onVisibility: null,

    init() {
      const ds = this.$root.dataset;
      try {
        this.steps = JSON.parse(ds.steps || '[]');
      } catch (_err) {
        this.steps = [];
      }
      this.recipeId = ds.recipeId || '';
      this.coffeeId = ds.coffeeId || '';

      if (this.steps.length > 0) {
        this.remainingSeconds = this._stepDuration(0);
      }

      this._loadCuePrefs();
      this._setupVisibilityReacquire();
    },

    destroy() {
      this._stopTimer();
      this._releaseWakeLock();
      if (this._onVisibility) {
        document.removeEventListener('visibilitychange', this._onVisibility);
        this._onVisibility = null;
      }
      try {
        localStorage.removeItem('snobbery:gbm:start');
      } catch (_) {}
    },

    // --- computed helpers ---
    get hasSteps() {
      return this.steps.length > 0;
    },

    get currentStep() {
      return this.steps[this.currentStepIndex] || null;
    },

    get nextStep() {
      return this.steps[this.currentStepIndex + 1] || null;
    },

    get stepCount() {
      return this.steps.length;
    },

    get progressPct() {
      if (this.stepCount === 0) return 0;
      return Math.round((this.currentStepIndex / this.stepCount) * 100);
    },

    get formattedRemaining() {
      return this._formatTime(this.remainingSeconds);
    },

    get formattedElapsed() {
      return this._formatTime(this.elapsedTotalSeconds);
    },

    // --- coaching getters (Phase 20 D-08..D-11) ---

    get coachingLine() {
      const step = this.currentStep;
      if (!step) return '';
      const type = step.type || 'Pour';
      const w = step.water_grams;
      // Pour sequence number: count Pour steps up to and including current
      const pourNum = this.steps
        .slice(0, this.currentStepIndex + 1)
        .filter(s => (s.type || 'Pour') === 'Pour').length;
      switch (type) {
        case 'Bloom':  return w ? 'Bloom — ' + w + 'g' : 'Bloom';
        case 'Pour':   return 'Pour ' + pourNum + ' — to ' + (w ? w + 'g' : '?');
        case 'Wait':   return 'Wait — ' + this._formatTime(step.time_seconds || 0);
        case 'Action': return step.label || 'Action';
        default:       return step.label || 'Step ' + (this.currentStepIndex + 1);
      }
    },

    get stepTypeBadge() {
      const step = this.currentStep;
      return step ? (step.type || 'Pour').toUpperCase() : '';
    },

    get stepNote() {
      const step = this.currentStep;
      return (step && step.note) ? step.note : '';
    },

    get stepWaterTemp() {
      const step = this.currentStep;
      return (step && step.water_temp_c) ? 'at ' + step.water_temp_c + '°C' : '';
    },

    // Pre-cue countdown: returns 1–3 when within 3s of a transition (D-10)
    get preCueCountdown() {
      if (this.remainingSeconds > 3 || this.remainingSeconds <= 0) return 0;
      return this.remainingSeconds;
    },

    get isPreCue() {
      return this.preCueCountdown > 0;
    },

    _formatTime(secs) {
      const m = Math.floor(secs / 60);
      const s = secs % 60;
      return String(m).padStart(2, '0') + ':' + String(s).padStart(2, '0');
    },

    _stepDuration(index) {
      // Steps carry cumulative time offsets; duration of step N is
      // offset[N] - offset[N-1] (or offset[0] for the first step).
      const step = this.steps[index];
      if (!step) return 0;
      const offset = step.time_seconds || step.time || 0;
      if (index === 0) return offset;
      const prev = this.steps[index - 1];
      const prevOffset = prev ? (prev.time_seconds || prev.time || 0) : 0;
      return Math.max(0, offset - prevOffset);
    },

    // --- start / pause / resume ---
    async start() {
      if (!this.hasSteps || this.isRunning) return;
      // Switch to running screen immediately so iOS PWA doesn't show a frozen UI
      // if unlockAudio or requestWakeLock take time / reject.
      this.isRunning = true;
      this.isPaused = false;
      this._startTimer();
      // Audio unlock MUST run synchronously inside the user gesture (before any await).
      try { this.unlockAudio(); } catch (_e) { /* non-fatal */ }
      // Wake lock is best-effort; failure must not abort the brew.
      try { await this.requestWakeLock(); } catch (_e) { /* non-fatal */ }
    },

    pause() {
      if (!this.isRunning || this.isPaused) return;
      this.isPaused = true;
      this._pausedAt = Date.now();
      this._stopTimer();
    },

    resume() {
      if (!this.isRunning || !this.isPaused) return;
      this.isPaused = false;
      if (this._pausedAt) {
        this._pausedOffset += Math.floor((Date.now() - this._pausedAt) / 1000);
        this._pausedAt = null;
      }
      this._startTimer();
    },

    togglePause() {
      if (this.isPaused) {
        this.resume();
      } else {
        this.pause();
      }
    },

    // --- timer internals ---
    _startTimer() {
      this._stopTimer();
      if (!this._startTimestamp) {
        this._startTimestamp = Date.now() - (this.elapsedTotalSeconds * 1000);
        try { localStorage.setItem('snobbery:gbm:start', String(this._startTimestamp)); } catch (_) {}
      }
      this._timer = setInterval(() => this._tick(), 1000);
    },

    _stopTimer() {
      if (this._timer !== null) {
        clearInterval(this._timer);
        this._timer = null;
      }
    },

    // Wall-clock-truth tick: compute elapsed from Date.now() - _startTimestamp (Pitfall 1).
    _tick() {
      const elapsed = Math.floor((Date.now() - this._startTimestamp) / 1000) - this._pausedOffset;
      this.elapsedTotalSeconds = elapsed;
      this._syncStateFromElapsed(elapsed);
    },

    // Self-correct on wake from screen sleep (D-15, Pitfall 7).
    _resync() {
      if (!this._startTimestamp || !this.isRunning || this.isPaused) return;
      const elapsed = Math.floor((Date.now() - this._startTimestamp) / 1000) - this._pausedOffset;
      this.elapsedTotalSeconds = elapsed;
      this._syncStateFromElapsed(elapsed);
    },

    // Walk steps using cumulative time_seconds offsets (Pitfall 5).
    // Fires chime/vibrate for newly crossed step boundaries only.
    _syncStateFromElapsed(elapsed) {
      let stepIdx = 0;
      for (let i = 0; i < this.steps.length; i++) {
        if (elapsed >= (this.steps[i].time_seconds || 0)) {
          stepIdx = i + 1;
        } else {
          break;
        }
      }

      if (stepIdx >= this.steps.length) {
        if (!this.isDone) {
          this._stopTimer();
          this.isRunning = false;
          this.isDone = true;
          this._releaseWakeLock();
        }
        return;
      }

      const prevIndex = this.currentStepIndex;
      this.currentStepIndex = stepIdx;
      const stepEnd = this.steps[stepIdx].time_seconds || 0;
      this.remainingSeconds = Math.max(0, stepEnd - elapsed);

      // Newly crossed step boundary — fire cues and auto-derive bloom time.
      if (stepIdx > prevIndex) {
        const completedStep = this.steps[prevIndex];
        if ((completedStep.type || 'Pour') === 'Bloom') {
          // D-13: bloom time auto-derives when the Bloom step transitions out.
          this.bloomTimeSeconds = this.elapsedTotalSeconds;
        }
        // Chime fires at the transition, NOT during pre-cue display (Pitfall 2).
        if (this.cuePrefs.chime) this.playChime();
        if (this.cuePrefs.vibrate) this.triggerVibration();
      }
    },

    // Manual skip to next step.
    nextStep_action() {
      if (!this.isRunning || this.isDone) return;
      if (this.currentStepIndex >= this.steps.length - 1) {
        this._stopTimer();
        this.isRunning = false;
        this.isDone = true;
        this._releaseWakeLock();
        return;
      }
      const prevIndex = this.currentStepIndex;
      this.currentStepIndex++;
      this.remainingSeconds = this._stepDuration(this.currentStepIndex);
      const completedStep = this.steps[prevIndex];
      if ((completedStep.type || 'Pour') === 'Bloom') {
        this.bloomTimeSeconds = this.elapsedTotalSeconds;
      }
      if (this.cuePrefs.chime) this.playChime();
      if (this.cuePrefs.vibrate) this.triggerVibration();
    },

    // --- tap-to-mark (Phase 20 D-12 / D-14) ---
    markFirstDrip() {
      if (this.firstDripSeconds === null) {
        this.firstDripSeconds = this.elapsedTotalSeconds;
      }
    },

    clearFirstDrip() {
      this.firstDripSeconds = null;
    },

    // --- audio ---
    unlockAudio() {
      // Called from "Start guided brew" button tap — must be user gesture.
      if (!this.audioCtx) {
        this.audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }
    },

    playChime() {
      // Re-resume AudioContext on each step advance (Pitfall 4 — iOS 18.5
      // re-suspends after ~5s of inactivity).
      if (this.audioCtx && this.audioCtx.state === 'suspended') {
        this.audioCtx.resume();
      }
      if (!this.audioCtx || this.audioCtx.state !== 'running') return;
      const osc = this.audioCtx.createOscillator();
      const gain = this.audioCtx.createGain();
      osc.type = 'sine';
      osc.frequency.setValueAtTime(880, this.audioCtx.currentTime); // A5
      gain.gain.setValueAtTime(0.3, this.audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.audioCtx.currentTime + 0.5);
      osc.connect(gain);
      gain.connect(this.audioCtx.destination);
      osc.start();
      osc.stop(this.audioCtx.currentTime + 0.5);
    },

    // --- vibration ---
    triggerVibration() {
      if (this.cuePrefs.vibrate && navigator.vibrate) {
        navigator.vibrate([100, 50, 100]);
      }
      // navigator.vibrate is undefined on iOS Safari — silent skip, no error.
    },

    // --- wake lock ---
    async requestWakeLock() {
      if ('wakeLock' in navigator) {
        try {
          this.wakeLockSentinel = await navigator.wakeLock.request('screen');
          this.wakeLockState = 'held';
          this.wakeLockSentinel.addEventListener('release', () => {
            this.wakeLockState = 'none';
          });
          return;
        } catch (_e) {
          // Falls through to NoSleep.js fallback.
        }
      }
      // NoSleep.js fallback for iOS pre-18.4 installed PWAs.
      // NoSleep.min.js must be loaded (nonce-tagged) before this runs.
      if (window.NoSleep) {
        this.noSleep = new window.NoSleep();
        try {
          await this.noSleep.enable(); // MUST be in user gesture handler
          this.wakeLockState = 'fallback';
        } catch (_e) {
          this.wakeLockState = 'none';
        }
      }
    },

    async _releaseWakeLock() {
      if (this.wakeLockSentinel) {
        try {
          await this.wakeLockSentinel.release();
        } catch (_e) {
          // Ignore release errors.
        }
        this.wakeLockSentinel = null;
      }
      if (this.noSleep) {
        this.noSleep.disable();
        this.noSleep = null;
      }
      this.wakeLockState = 'none';
    },

    _setupVisibilityReacquire() {
      this._onVisibility = async () => {
        if (document.visibilityState === 'visible' && this.isRunning && !this.isPaused) {
          // Resync first so missed transitions auto-advance silently (D-15).
          this._resync();
          await this.requestWakeLock();
        }
      };
      document.addEventListener('visibilitychange', this._onVisibility);
    },

    // --- cue prefs ---
    _loadCuePrefs() {
      try {
        const raw = localStorage.getItem('snobbery:gbm:cues');
        const prefs = raw ? JSON.parse(raw) : null;
        this.cuePrefs = prefs || { chime: true, vibrate: true };
      } catch (_err) {
        this.cuePrefs = { chime: true, vibrate: true };
      }
    },

    _saveCuePrefs() {
      try {
        localStorage.setItem('snobbery:gbm:cues', JSON.stringify(this.cuePrefs));
      } catch (_err) {
        /* quota / private mode */
      }
    },

    toggleChime() {
      this.cuePrefs = { ...this.cuePrefs, chime: !this.cuePrefs.chime };
      this._saveCuePrefs();
    },

    // Idempotent On/Off helpers — CSP-safe alternatives to short-circuit
    // expressions like `cuePrefs.chime || toggleChime()` in x-on handlers.
    chimeOn() {
      if (!this.cuePrefs.chime) this.toggleChime();
    },

    chimeOff() {
      if (this.cuePrefs.chime) this.toggleChime();
    },

    vibrateOn() {
      if (!this.cuePrefs.vibrate) this.toggleVibrate();
    },

    vibrateOff() {
      if (this.cuePrefs.vibrate) this.toggleVibrate();
    },

    // Computed aria-pressed strings for the "Off" buttons — avoids
    // `(!cuePrefs.x).toString()` expressions in templates (CSP-unsafe).
    get chimeOffPressed() {
      return String(!this.cuePrefs.chime);
    },

    get vibrateOffPressed() {
      return String(!this.cuePrefs.vibrate);
    },

    toggleVibrate() {
      this.cuePrefs = { ...this.cuePrefs, vibrate: !this.cuePrefs.vibrate };
      this._saveCuePrefs();
    },

    // --- cancel / finish ---
    cancelWithoutLogging() {
      if (window.confirm('Cancel brew? This cannot be undone.')) {
        this._stopTimer();
        this._releaseWakeLock();
        window.location.assign('/brew');
      }
    },

    // Navigate to /brew/new prefilled with recipe, coffee, and all timing params (Phase 20 D-15).
    finishBrewing() {
      let url = '/brew/new?gbm=1&recipe_id=' + encodeURIComponent(this.recipeId);
      if (this.coffeeId) {
        url += '&coffee_id=' + encodeURIComponent(this.coffeeId);
      }
      url += '&brew_time=' + encodeURIComponent(this.elapsedTotalSeconds);
      if (this.firstDripSeconds !== null) {
        url += '&first_drip=' + encodeURIComponent(this.firstDripSeconds);
      }
      if (this.bloomTimeSeconds !== null) {
        url += '&bloom_time=' + encodeURIComponent(this.bloomTimeSeconds);
      }
      window.location.assign(url);
    },

    doneWithoutLogging() {
      this._stopTimer();
      this._releaseWakeLock();
      window.location.assign('/');
    },
  }));
});
