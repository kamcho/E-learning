/**
 * Party-style paper confetti burst (no dependencies).
 * Respects prefers-reduced-motion.
 */
(function (global) {
  var COLORS = [
    '#7c3aed',
    '#3dd6c6',
    '#f4a261',
    '#f472b6',
    '#fbbf24',
    '#34d399',
    '#60a5fa',
    '#ffffff',
  ];

  function prefersReducedMotion() {
    return (
      global.matchMedia &&
      global.matchMedia('(prefers-reduced-motion: reduce)').matches
    );
  }

  function ConfettiBurst(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.particles = [];
    this.running = false;
    this.raf = 0;
  }

  ConfettiBurst.prototype.resize = function () {
    var dpr = Math.min(global.devicePixelRatio || 1, 2);
    this.canvas.width = Math.floor(global.innerWidth * dpr);
    this.canvas.height = Math.floor(global.innerHeight * dpr);
    this.canvas.style.width = global.innerWidth + 'px';
    this.canvas.style.height = global.innerHeight + 'px';
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.width = global.innerWidth;
    this.height = global.innerHeight;
  };

  ConfettiBurst.prototype.spawn = function (originX, originY, count) {
    var spread = Math.PI * 0.9;
    var baseAngle = -Math.PI / 2;

    for (var i = 0; i < count; i += 1) {
      var angle = baseAngle + (Math.random() - 0.5) * spread;
      var speed = 6 + Math.random() * 9;
      var w = 6 + Math.random() * 7;
      var h = 3 + Math.random() * 5;
      this.particles.push({
        x: originX + (Math.random() - 0.5) * 48,
        y: originY + (Math.random() - 0.5) * 24,
        vx: Math.cos(angle) * speed,
        vy: Math.sin(angle) * speed - Math.random() * 3,
        w: w,
        h: h,
        rot: Math.random() * Math.PI,
        spin: (Math.random() - 0.5) * 0.35,
        color: COLORS[Math.floor(Math.random() * COLORS.length)],
        drift: (Math.random() - 0.5) * 0.15,
        life: 1,
        decay: 0.012 + Math.random() * 0.01,
      });
    }
  };

  ConfettiBurst.prototype.tick = function () {
    var ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);
    var alive = 0;

    for (var i = 0; i < this.particles.length; i += 1) {
      var p = this.particles[i];
      if (p.life <= 0) continue;
      alive += 1;
      p.vy += 0.28;
      p.vx += p.drift;
      p.x += p.vx;
      p.y += p.vy;
      p.rot += p.spin;
      p.life -= p.decay;

      ctx.save();
      ctx.globalAlpha = Math.max(0, p.life);
      ctx.translate(p.x, p.y);
      ctx.rotate(p.rot);
      ctx.fillStyle = p.color;
      ctx.fillRect(-p.w / 2, -p.h / 2, p.w, p.h);
      ctx.restore();
    }

    return alive > 0;
  };

  ConfettiBurst.prototype.run = function () {
    var self = this;
    if (self.running) return;
    self.running = true;
    self.resize();

    function frame() {
      if (self.tick()) {
        self.raf = global.requestAnimationFrame(frame);
      } else {
        self.stop();
      }
    }
    self.raf = global.requestAnimationFrame(frame);

    self._boundResize = self._onResize.bind(self);
    global.addEventListener('resize', self._boundResize);
  };

  ConfettiBurst.prototype.stop = function () {
    this.running = false;
    if (this.raf) {
      global.cancelAnimationFrame(this.raf);
      this.raf = 0;
    }
    this.ctx.clearRect(0, 0, this.width, this.height);
    if (this._boundResize) {
      global.removeEventListener('resize', this._boundResize);
      this._boundResize = null;
    }
    if (this.canvas.parentNode) {
      this.canvas.parentNode.removeChild(this.canvas);
    }
  };

  ConfettiBurst.prototype._onResize = function () {
    if (this.running) this.resize();
  };

  var activeLayer = null;

  function celebrate(options) {
    options = options || {};
    if (prefersReducedMotion()) {
      return;
    }

    if (activeLayer) {
      activeLayer.stop();
      activeLayer = null;
    }

    var canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    canvas.className = 'soma-confetti-canvas';
    canvas.style.cssText =
      'position:fixed;inset:0;z-index:9999;pointer-events:none;';
    document.body.appendChild(canvas);

    var burst = new ConfettiBurst(canvas);
    activeLayer = burst;

    var anchor = options.anchor;
    var originX = options.x;
    var originY = options.y;
    if (originX == null || originY == null) {
      if (anchor && anchor.getBoundingClientRect) {
        var rect = anchor.getBoundingClientRect();
        originX = rect.left + rect.width / 2;
        originY = rect.top + rect.height * 0.35;
      } else {
        originX = global.innerWidth / 2;
        originY = global.innerHeight * 0.32;
      }
    }

    var count = options.particles || 140;
    burst.spawn(originX, originY, count);
    burst.spawn(global.innerWidth * 0.18, global.innerHeight * 0.22, Math.floor(count * 0.35));
    burst.spawn(global.innerWidth * 0.82, global.innerHeight * 0.22, Math.floor(count * 0.35));

    setTimeout(function () {
      burst.spawn(originX, originY + 12, Math.floor(count * 0.45));
    }, 180);

    burst.run();
    setTimeout(function () {
      if (activeLayer === burst) {
        burst.stop();
        activeLayer = null;
      }
    }, options.duration || 3200);
  }

  global.SomaConfetti = { celebrate: celebrate };
})(window);