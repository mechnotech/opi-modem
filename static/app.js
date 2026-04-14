// OPI Monitor — app.js

function doLogout() {
  fetch('/api/logout', {method: 'POST'}).then(function() {
    window.location.href = '/login';
  });
}

// Redirect to login on 401
function authFetch(url, opts) {
  return fetch(url, opts).then(function(r) {
    if (r.status === 401) { window.location.href = '/login'; throw new Error('unauth'); }
    return r;
  });
}

function toast(msg, type) {
  var el = document.getElementById('toast');
  el.textContent = msg;
  el.style.borderColor = (type === 'err') ? 'var(--danger)' : 'var(--accent)';
  el.style.color        = (type === 'err') ? 'var(--danger)' : 'var(--accent)';
  el.classList.add('show');
  setTimeout(function() { el.classList.remove('show'); }, 3000);
}

function post(url) {
  return authFetch(url, {method: 'POST'}).then(function(r) { return r.json(); });
}

function phoneReboot() {
  if (!confirm('Перезагрузить телефон? Интернет восстановится автоматически (~2 мин)')) return;
  post('/api/phone/reboot').then(function() { toast('Телефон перезагружается, ждите...'); });
}
function opiReboot() {
  if (!confirm('Перезагрузить Orange Pi?')) return;
  post('/api/opi/reboot').then(function() { toast('OPI перезагружается...'); });
}
function opiPoweroff() {
  if (!confirm('Выключить Orange Pi?')) return;
  post('/api/opi/poweroff').then(function() { toast('OPI выключается...'); });
}

function rsrpToBars(rsrp) {
  if (!rsrp) return 0;
  if (rsrp >= -80)  return 5;
  if (rsrp >= -90)  return 4;
  if (rsrp >= -100) return 3;
  if (rsrp >= -110) return 2;
  return 1;
}

function updateSignalBars(rsrp) {
  var bars   = document.querySelectorAll('.sig-bar');
  var active = rsrpToBars(rsrp);
  for (var i = 0; i < bars.length; i++) {
    if (i < active) bars[i].classList.add('active');
    else            bars[i].classList.remove('active');
  }
}

function setText(id, val) {
  document.getElementById(id).textContent = val;
}
function setClass(id, cls) {
  document.getElementById(id).className = 'stat-value ' + cls;
}

function loadStats() {
  authFetch('/api/stats')
    .then(function(r) { return r.json(); })
    .then(function(d) {
      var bat = d.battery;
      var pct = bat.capacity !== null ? bat.capacity : 0;

      // Battery
      setText('bat-pct',     pct + '%');
      setText('bat-temp',    bat.temp     !== null ? bat.temp     + ' C' : '--');
      setText('bat-current', bat.current_ma !== null ? bat.current_ma + ' mA' : '--');
      setText('bat-voltage', bat.voltage_v  !== null ? bat.voltage_v  + ' V'  : '--');
      setText('bat-status',  bat.status);

      var chEl = document.getElementById('bat-charging');
      chEl.textContent = bat.charging ? 'ON' : 'OFF';
      chEl.className   = 'stat-value ' + (bat.charging ? 'accent' : 'warn');

      var bar = document.getElementById('bat-bar');
      bar.style.width = pct + '%';
      bar.className   = 'bat-bar' + (pct < 20 ? ' danger' : pct < 40 ? ' warn' : '');

      setClass('bat-pct', pct < 20 ? 'danger' : pct < 40 ? 'warn' : 'accent');
      if (bat.temp !== null)
        setClass('bat-temp', bat.temp > 40 ? 'danger' : bat.temp > 35 ? 'warn' : '');

      // Signal
      var sig = d.signal;
      setText('sig-operator', sig.operator || '--');
      setText('sig-band',     sig.band     || ('EARFCN ' + (sig.earfcn || '--')));
      setText('sig-rsrp',     sig.rsrp !== null ? sig.rsrp + ' dBm' : '--');
      setText('sig-rsrq',     sig.rsrq !== null ? sig.rsrq + ' dB'  : '--');
      setText('sig-rssi',     sig.rssi !== null ? sig.rssi + ' dBm' : '--');
      updateSignalBars(sig.rsrp);

      // Traffic
      setText('rx-mb', d.traffic.rx_mb);
      setText('tx-mb', d.traffic.tx_mb);
      if (d.traffic.wan_iface) setText('wan-iface', d.traffic.wan_iface);

      // OPI
      setText('opi-uptime', d.opi.uptime || '--');
      setText('opi-load',   d.opi.load   || '--');
      setText('opi-temp',   d.opi.cpu_temp !== null ? d.opi.cpu_temp + ' C' : '--');
      if (d.opi.cpu_temp)
        setClass('opi-temp', d.opi.cpu_temp > 70 ? 'danger' : d.opi.cpu_temp > 55 ? 'warn' : '');

      setText('last-update', 'last update: ' + d.time);
      document.getElementById('status-dot').style.background = 'var(--accent)';
    })
    .catch(function() {
      document.getElementById('status-dot').style.background = 'var(--danger)';
    });
}

function loadSms() {
  var list = document.getElementById('sms-list');
  list.innerHTML = '<div style="color:var(--dim);font-family:var(--mono);font-size:.8rem">Loading...</div>';
  authFetch('/api/sms')
    .then(function(r) { return r.json(); })
    .then(function(msgs) {
      if (!msgs.length) {
        list.innerHTML = '<div style="color:var(--dim);font-family:var(--mono);font-size:.8rem">No messages</div>';
        return;
      }
      var html = '';
      for (var i = 0; i < msgs.length; i++) {
        var m = msgs[i];
        html += '<div class="sms-item ' + (m.read ? '' : 'sms-unread') + '">'
              + '<span class="sms-from">' + m.from + '</span>'
              + '<span class="sms-date">' + m.date + '</span>'
              + '<div class="sms-body">'  + m.body + '</div>'
              + '</div>';
      }
      list.innerHTML = html;
    })
    .catch(function() {
      list.innerHTML = '<div style="color:var(--danger);font-family:var(--mono);font-size:.8rem">Error loading SMS</div>';
    });
}

function clearSms() {
  if (!confirm('Удалить все SMS из inbox?')) return;
  authFetch('/api/sms/clear', {method: 'POST'})
    .then(function(r) { return r.json(); })
    .then(function() {
      toast('SMS удалены');
      loadSms();
    })
    .catch(function() { toast('Ошибка', 'err'); });
}

function sendSms() {
  var to   = document.getElementById('sms-to').value.trim();
  var body = document.getElementById('sms-body').value.trim();
  if (!to || !body) { toast('Fill number and text', 'err'); return; }
  authFetch('/api/sms/send', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({to: to, body: body})
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    if (d.success) {
      toast('SMS sent');
      document.getElementById('sms-body').value = '';
    } else {
      toast('Send failed', 'err');
    }
  })
  .catch(function() { toast('Error', 'err'); });
}

function sendUssd(code) {
  if (!code) return;
  var el = document.getElementById('ussd-response');
  el.style.color = 'var(--dim)';
  el.textContent = 'Sending ' + code + ' ... (~5 sec)';
  authFetch('/api/ussd', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({code: code})
  })
  .then(function(r) { return r.json(); })
  .then(function(d) {
    el.style.color = 'var(--accent)';
    el.textContent = d.response.length ? d.response.join('\n') : 'No response captured';
  })
  .catch(function() {
    el.style.color = 'var(--danger)';
    el.textContent = 'Error';
  });
}

function updateClock() {
  var now = new Date();
  setText('clock', now.toTimeString().slice(0, 8));
}

// Init
updateClock();
setInterval(updateClock, 1000);
loadStats();
loadSms();
setInterval(loadStats, 10000);
