/* The locally vendored OpenSpline viewer owns both sound and video. */
class RealFaceAvatar {
  constructor() {
    this.active = false;
    this.connection = null;
    this.generation = 0;
    this.speaking = false;
    this.interrupted = false;
    this.resumeTimer = null;
    this.connectTimer = null;
    this.connectTimeoutMs = 45000;
    this.options = {};
    this.video = document.getElementById('avatarVideo');
    this.status = document.getElementById('avatarStatus');
    this.button = document.getElementById('avatarConnectBtn');
    this.playButton = document.getElementById('avatarPlayBtn');
    this.button.onclick = () => this.toggle();
    this.playButton.onclick = () => {
      this.connection?.play().then(() => { this.playButton.hidden = true; })
        .catch(() => this.setStatus('Tap again to enable sound and video.'));
    };
  }

  configure(options) { this.options = options; }
  setStatus(text) { this.status.textContent = text; }

  async toggle() {
    if (this.connection || this.button.dataset.connecting === 'true') {
      this.disconnect();
      return;
    }
    this.button.dataset.connecting = 'true';
    const generation = ++this.generation;
    this.button.textContent = 'Cancel connection';
    this.setStatus('Connecting to your tutor…');
    this.connectTimer = setTimeout(() => {
      if (generation === this.generation && !this.active) {
        this.fail('Connection took too long. Try connecting again.');
      }
    }, this.connectTimeoutMs);
    try {
      await this.options.connect();
      // The user may cancel while the WebSocket is connecting.
      if (generation === this.generation && this.button.dataset.connecting === 'true') {
        this.options.send({type: 'avatar_start'});
      }
    } catch {
      if (generation === this.generation) this.fail('Unable to connect. Check that the server is running.');
    }
  }

  handleMessage({type, content}) {
    if (!type.startsWith('avatar_')) return false;
    if (type === 'avatar_session') {
      if (this.button.dataset.connecting === 'true') void this.attach(content);
    }
    else if (type === 'avatar_status' && this.button.dataset.connecting === 'true') this.setStatus(content);
    else if (type === 'avatar_error') this.fail(content);
    else if (type === 'avatar_turn_start') {
      this.interrupted = false;
    } else if (type === 'avatar_interrupted') {
      // Stop immediately on the click; only resume idle video after the server
      // has cleared old media and the small RTP tail has had time to drain.
      clearTimeout(this.resumeTimer);
      this.resumeTimer = setTimeout(() => this.connection?.play().catch(() => {}), 180);
    } else if (type === 'avatar_turn_end' && !this.interrupted) {
      this.speaking = false;
      this.setStatus('Listening · Take your time');
      this.options.onTurnEnd?.();
    }
    return true;
  }

  async attach(session) {
    const generation = this.generation;
    try {
      const {AvatarConnection} = await import('/static/vendor/openspline/index.js');
      if (generation !== this.generation) return;
      const connection = new AvatarConnection(session, this.video);
      this.connection = connection;
      connection.addEventListener('statechange', event => {
        if (this.connection !== connection) return;
        if (event.detail === 'ready') {
          clearTimeout(this.connectTimer);
          if (!this.active) {
            this.options.onReady?.();
            this.active = true;
            this.options.send({type: 'avatar_ready'});
          }
          this.setStatus('Live face connected · Ready to listen');
          this.button.textContent = 'Disconnect face';
          this.button.dataset.connecting = 'false';
        } else if (event.detail === 'speaking') {
          if (this.interrupted || this.speaking) return;
          this.speaking = true;
          this.video.play().catch(() => {});
          this.video.muted = false;
          this.setStatus('Your tutor is speaking');
          this.options.onSpeaking?.();
        } else if (event.detail === 'disconnected' || event.detail === 'error') {
          this.fail('Live face disconnected. Reconnect to restore video.');
        }
      });
      connection.addEventListener('autoplayblocked', () => {
        if (this.connection === connection) this.playButton.hidden = false;
      });
      // The player's turnend means generation ended, not that audio finished
      // playing. Only avatar_turn_end from the publisher's drain unlocks input.
      connection.addEventListener('error', () => {
        if (this.connection === connection) this.fail('The avatar stream failed. Voice-only mode is available.');
      });
      this.video.hidden = false;
      await connection.connect();
    } catch {
      if (generation === this.generation) this.fail('Could not play the live face. Check the renderer URL and network access.');
    }
  }

  interrupt(notify = true) {
    if (!this.connection) return;
    clearTimeout(this.resumeTimer);
    this.interrupted = true;
    this.speaking = false;
    this.video.muted = true;
    this.video.pause();
    if (notify) this.options.send({type: 'avatar_interrupt'});
    this.setStatus('Listening · Take your time');
  }

  disconnect(notify = true) {
    clearTimeout(this.resumeTimer);
    clearTimeout(this.connectTimer);
    ++this.generation;
    this.active = false;
    this.speaking = false;
    this.interrupted = false;
    const previous = this.connection;
    this.connection = null;
    previous?.close();
    this.video.hidden = true;
    this.video.muted = false;
    this.playButton.hidden = true;
    this.button.dataset.connecting = 'false';
    this.button.textContent = 'Connect live face';
    if (notify) this.options.send?.({type: 'avatar_stop'});
    this.setStatus('Portrait preview · Connect to see your tutor move');
  }

  fail(message) {
    this.disconnect(false);
    this.options.send?.({type: 'avatar_failed'});
    this.options.onFailure?.();
    this.setStatus(message);
  }
}

window.realFace = new RealFaceAvatar();
