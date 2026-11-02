/* The locally vendored OpenSpline viewer owns both sound and video. */
class RealFaceAvatar {
  constructor() {
    this.active = false;
    this.connection = null;
    this.generation = 0;
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
    this.button.textContent = 'Cancel connection';
    this.setStatus('Connecting to your tutor… First startup can take a few minutes.');
    try {
      await this.options.connect();
      // The user may cancel while the WebSocket is connecting.
      if (this.button.dataset.connecting === 'true') this.options.send({type: 'avatar_start'});
    } catch {
      this.fail('Unable to connect. Check that the server is running.');
    }
  }

  handleMessage({type, content}) {
    if (!type.startsWith('avatar_')) return false;
    if (type === 'avatar_session') void this.attach(content);
    else if (type === 'avatar_status') this.setStatus(content);
    else if (type === 'avatar_error') this.fail(content);
    else if (type === 'avatar_turn_end') this.options.onTurnEnd?.();
    return true;
  }

  async attach(session) {
    const generation = ++this.generation;
    try {
      const {AvatarConnection} = await import('/static/vendor/openspline/index.js');
      if (generation !== this.generation) return;
      const connection = new AvatarConnection(session, this.video);
      this.connection = connection;
      connection.addEventListener('statechange', event => {
        if (this.connection !== connection) return;
        if (event.detail === 'ready') {
          if (!this.active) {
            this.options.onReady?.();
            this.active = true;
            this.options.send({type: 'avatar_ready'});
          }
          this.setStatus('Live face connected · Ready to listen');
          this.button.textContent = 'Disconnect face';
          this.button.dataset.connecting = 'false';
        } else if (event.detail === 'speaking') {
          this.video.muted = false;
          this.setStatus('Your tutor is speaking');
          this.options.onSpeaking?.();
        } else if (event.detail === 'disconnected' || event.detail === 'error') {
          this.fail('Live face disconnected. Reconnect to restore video.');
        }
      });
      connection.addEventListener('autoplayblocked', () => { this.playButton.hidden = false; });
      connection.addEventListener('turnend', () => {
        if (this.connection !== connection) return;
        this.setStatus('Listening · Take your time');
        this.options.onTurnEnd?.();
      });
      connection.addEventListener('error', () => this.fail('The avatar stream failed. Voice-only mode is available.'));
      this.video.hidden = false;
      await connection.connect();
    } catch {
      if (generation === this.generation) this.fail('Could not play the live face. Check the renderer URL and network access.');
    }
  }

  interrupt() {
    if (!this.connection) return;
    this.video.muted = true;
    this.options.send({type: 'avatar_interrupt'});
    this.setStatus('Listening · Take your time');
  }

  disconnect(notify = true) {
    ++this.generation;
    this.active = false;
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
