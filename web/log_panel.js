/**
 * Map Generator Pro v7.0 — Log Panel
 * Panneau de log flottant style terminal, disponible sur toutes les pages.
 * Usage : inclure ce script en fin de <body>. Il s'auto-initialise.
 */

(function() {
  'use strict';

  // ── CSS ──────────────────────────────────────────────────────────────────────
  var css = `
#mgp-log-btn {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 1000;
  width: 38px;
  height: 38px;
  background: #0a1e12;
  border: 1px solid #2e6647;
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all .2s;
  font-size: 16px;
}
#mgp-log-btn:hover {
  background: #1a3d2a;
  border-color: #5dba7d;
}
#mgp-log-badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #2e8b57;
  color: #050e09;
  font-family: 'Courier New', monospace;
  font-size: 8px;
  font-weight: 700;
  min-width: 14px;
  height: 14px;
  border-radius: 7px;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 0 3px;
}

#mgp-log-panel {
  position: fixed;
  bottom: 68px;
  right: 20px;
  z-index: 999;
  width: 520px;
  max-height: 340px;
  background: #050e09;
  border: 1px solid #2e6647;
  border-radius: 8px;
  display: none;
  flex-direction: column;
  font-family: 'Courier New', monospace;
  box-shadow: 0 4px 24px rgba(0,0,0,0.6);
}
#mgp-log-panel.open {
  display: flex;
}

#mgp-log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid #1e3d2a;
  flex-shrink: 0;
}
#mgp-log-title {
  font-size: 10px;
  color: #5dba7d;
  letter-spacing: 2px;
  text-transform: uppercase;
}
#mgp-log-actions {
  display: flex;
  gap: 6px;
}
.mgp-log-action-btn {
  background: transparent;
  border: 1px solid #1e3d2a;
  border-radius: 3px;
  color: #4a7a5a;
  font-family: 'Courier New', monospace;
  font-size: 9px;
  letter-spacing: 1px;
  padding: 2px 7px;
  cursor: pointer;
  transition: all .15s;
}
.mgp-log-action-btn:hover {
  border-color: #2e6647;
  color: #7ab890;
}

#mgp-log-body {
  flex: 1;
  overflow-y: auto;
  padding: 8px 12px;
  scrollbar-width: thin;
  scrollbar-color: #2e6647 #0a1e12;
}

.mgp-log-line {
  font-size: 10px;
  line-height: 1.7;
  color: #4a7a5a;
  white-space: pre-wrap;
  word-break: break-all;
}
.mgp-log-line.new {
  color: #7ab890;
}
.mgp-log-line.warn {
  color: #c8a060;
}
.mgp-log-line.err {
  color: #e87a7a;
}
.mgp-log-line.action {
  color: #5dba7d;
}
.mgp-log-empty {
  font-size: 10px;
  color: #2e5c3e;
  letter-spacing: 1px;
  padding: 8px 0;
}

#mgp-log-footer {
  padding: 5px 12px;
  border-top: 1px solid #1e3d2a;
  font-size: 9px;
  color: #2e5c3e;
  letter-spacing: 1px;
  flex-shrink: 0;
  display: flex;
  justify-content: space-between;
}
`;

  // ── HTML ─────────────────────────────────────────────────────────────────────
  function injectHTML() {
    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);

    var btn = document.createElement('div');
    btn.id = 'mgp-log-btn';
    btn.title = 'Journal de session';
    btn.innerHTML = '<span>&#128196;</span><div id="mgp-log-badge"></div>';
    btn.onclick = togglePanel;
    document.body.appendChild(btn);

    var panel = document.createElement('div');
    panel.id = 'mgp-log-panel';
    panel.innerHTML = `
      <div id="mgp-log-header">
        <div id="mgp-log-title">&#9654; Journal de session</div>
        <div id="mgp-log-actions">
          <button class="mgp-log-action-btn" onclick="window._mgpLog.refresh()">&#8635; Rafraichir</button>
          <button class="mgp-log-action-btn" onclick="window._mgpLog.clear()">&#128465; Vider</button>
          <button class="mgp-log-action-btn" onclick="window._mgpLog.close()">&#10005;</button>
        </div>
      </div>
      <div id="mgp-log-body">
        <div class="mgp-log-empty">Aucune action enregistree.</div>
      </div>
      <div id="mgp-log-footer">
        <span id="mgp-log-count">0 ligne(s)</span>
        <span id="mgp-log-time">--:--:--</span>
      </div>
    `;
    document.body.appendChild(panel);
  }

  // ── State ─────────────────────────────────────────────────────────────────────
  var _lines = [];
  var _open = false;
  var _pollInterval = null;
  var _lastCount = 0;

  // ── Couleur selon le contenu ──────────────────────────────────────────────────
  function lineClass(text) {
    if (!text) return 'mgp-log-line';
    var t = text.toUpperCase();
    if (t.includes('ERREUR') || t.includes('ERROR') || t.includes('FAIL')) return 'mgp-log-line err';
    if (t.includes('WARN') || t.includes('ATTENTION')) return 'mgp-log-line warn';
    if (t.includes('[ACTION]') || t.includes('[PROJET]') || t.includes('[TERRAIN]') ||
        t.includes('[GENERATION]') || t.includes('[SATMAP]') || t.includes('[INSPECTION]') ||
        t.includes('[CORRECTIONS]')) return 'mgp-log-line action';
    return 'mgp-log-line';
  }

  // ── Rendu ─────────────────────────────────────────────────────────────────────
  function renderLines(lines, newCount) {
    var body = document.getElementById('mgp-log-body');
    if (!body) return;
    if (!lines || lines.length === 0) {
      body.innerHTML = '<div class="mgp-log-empty">Aucune action enregistree.</div>';
      return;
    }
    body.innerHTML = lines.map(function(line, i) {
      var isNew = i >= lines.length - newCount;
      var cls = lineClass(line) + (isNew ? ' new' : '');
      return '<div class="' + cls + '">' + escapeHTML(line) + '</div>';
    }).join('');
    // Scroll to bottom
    body.scrollTop = body.scrollHeight;
    // Footer
    var count = document.getElementById('mgp-log-count');
    if (count) count.textContent = lines.length + ' ligne(s)';
    var time = document.getElementById('mgp-log-time');
    if (time) time.textContent = new Date().toLocaleTimeString();
    // Badge
    var badge = document.getElementById('mgp-log-badge');
    if (badge && newCount > 0) {
      badge.style.display = 'flex';
      badge.textContent = newCount > 9 ? '9+' : newCount;
    }
  }

  function escapeHTML(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  // ── Fetch log depuis main.py ──────────────────────────────────────────────────
  function fetchLog() {
    if (!window.pywebview || !window.pywebview.api) return;
    window.pywebview.api.get_log().then(function(lines) {
      if (!lines) return;
      var newCount = Math.max(0, lines.length - _lastCount);
      _lines = lines;
      renderLines(lines, _open ? 0 : newCount);
      if (!_open && newCount > 0) {
        var badge = document.getElementById('mgp-log-badge');
        if (badge) { badge.style.display = 'flex'; badge.textContent = newCount > 9 ? '9+' : newCount; }
      }
      _lastCount = lines.length;
    }).catch(function() {});
  }

  // ── Toggle ────────────────────────────────────────────────────────────────────
  function togglePanel() {
    _open = !_open;
    var panel = document.getElementById('mgp-log-panel');
    if (panel) panel.classList.toggle('open', _open);
    if (_open) {
      // Clear badge
      var badge = document.getElementById('mgp-log-badge');
      if (badge) badge.style.display = 'none';
      fetchLog();
    }
  }

  // ── API publique ──────────────────────────────────────────────────────────────
  window._mgpLog = {
    refresh: function() { fetchLog(); },
    clear: function() {
      if (window.pywebview && window.pywebview.api) {
        window.pywebview.api.clear_log().then(function() {
          _lines = []; _lastCount = 0;
          renderLines([], 0);
        });
      }
    },
    close: function() {
      _open = false;
      var panel = document.getElementById('mgp-log-panel');
      if (panel) panel.classList.remove('open');
    }
  };

  // ── Init ──────────────────────────────────────────────────────────────────────
  function init() {
    injectHTML();
    // Poll toutes les 3 secondes
    _pollInterval = setInterval(fetchLog, 3000);
    // Premier fetch après pywebviewready
    window.addEventListener('pywebviewready', function() {
      setTimeout(fetchLog, 500);
    });
    if (window.pywebview && window.pywebview.api) {
      setTimeout(fetchLog, 500);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
