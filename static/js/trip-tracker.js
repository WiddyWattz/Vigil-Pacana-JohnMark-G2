/*
 * Vigil trip tracker (runs on the "tracking" page).
 *
 * 1. Gets the rider's position and speed from the browser's Geolocation API
 *    (or from a simulated demo ride when the trip source is SIMULATED).
 * 2. Warns the rider immediately with a beep + vibration when the speed is over the limit.
 * 3. Every few seconds, sends the collected readings to Django as JSON.
 *    Django validates and saves them and decides which ones count as SpeedAlerts.
 */
(() => {
  const root = document.getElementById("tracker");
  if (!root) return;

  const LIMIT = Number(root.dataset.limit);
  const SOURCE = root.dataset.source;
  const URL = root.dataset.readingsUrl;
  const CSRF = root.dataset.csrf;
  const FLUSH_EVERY_MS = 3000;
  const GAUGE_MAX = Math.max(120, LIMIT * 2); // km/h at the end of the gauge arc

  const $ = (id) => document.getElementById(id);
  const queue = [];          // readings waiting to be sent
  let last = null;           // previous position (to compute speed when the GPS gives none)
  let running = false;
  let watchId = null;
  let simTimer = null;
  let lastBeep = 0;
  let audio = null;

  // ---- UI helpers -------------------------------------------------------
  const status = (text) => { $("gps-status").textContent = text; };
  const showError = (text) => { $("tracker-error").textContent = text || ""; };

  function setGauge(speed) {
    $("speed-now").textContent = Math.round(speed);
    $("gauge-bar").setAttribute("stroke-dasharray", `${Math.min(speed / GAUGE_MAX, 1) * 100} 100`);
    const over = speed > LIMIT;
    $("gauge-card").classList.toggle("over", over);
    $("over-banner").hidden = !over;
    if (over) warn();
  }

  function placeLimitTick() {
    // Rotate the small tick on the gauge to where the speed limit is.
    const angle = Math.PI * (1 - Math.min(LIMIT / GAUGE_MAX, 1));
    const cx = 110, cy = 115, r1 = 80, r2 = 100;
    const line = $("gauge-limit");
    line.setAttribute("x1", cx + r1 * Math.cos(angle)); line.setAttribute("y1", cy - r1 * Math.sin(angle));
    line.setAttribute("x2", cx + r2 * Math.cos(angle)); line.setAttribute("y2", cy - r2 * Math.sin(angle));
  }

  // Sound + vibration, at most once every 3 seconds.
  function warn() {
    const now = Date.now();
    if (now - lastBeep < 3000) return;
    lastBeep = now;
    if (navigator.vibrate) navigator.vibrate([250, 120, 250]);
    if (!audio) return;
    const osc = audio.createOscillator(), gain = audio.createGain();
    osc.type = "square"; osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.15, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.6);
    osc.connect(gain).connect(audio.destination);
    osc.start(); osc.stop(audio.currentTime + 0.6);
  }

  // ---- Collecting readings ---------------------------------------------
  function distanceKm(a, b) {
    const R = 6371, rad = (d) => (d * Math.PI) / 180;
    const dLat = rad(b.lat - a.lat), dLon = rad(b.lon - a.lon);
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2;
    return 2 * R * Math.asin(Math.sqrt(h));
  }

  function addReading(lat, lon, speedKmh, accuracy, time) {
    const point = { lat, lon, time };
    if (speedKmh == null && last) {
      // GPS gave no speed: compute it from the distance since the previous point.
      const hours = (time - last.time) / 3600000;
      speedKmh = hours > 0 ? distanceKm(last, point) / hours : 0;
    }
    speedKmh = Math.max(0, Math.min(speedKmh || 0, 300));
    last = point;
    setGauge(speedKmh);
    queue.push({
      recorded_at: new Date(time).toISOString(),
      latitude: lat.toFixed(6),
      longitude: lon.toFixed(6),
      speed_kmh: speedKmh.toFixed(1),
      accuracy_m: accuracy == null ? "" : accuracy.toFixed(1),
    });
  }

  function onPosition(pos) {
    const c = pos.coords;
    const speed = c.speed == null || Number.isNaN(c.speed) ? null : c.speed * 3.6; // m/s -> km/h
    status(`GPS active (±${Math.round(c.accuracy)} m)`);
    addReading(c.latitude, c.longitude, speed, c.accuracy, pos.timestamp);
  }

  function onGpsError(err) {
    const reasons = { 1: "Location permission was denied. Allow location access for this site.", 2: "Position unavailable. Move to an open area.", 3: "GPS timed out. Still trying…" };
    showError(reasons[err.code] || err.message);
    status(err.code === 3 ? "Searching…" : "GPS error");
  }

  // Demo ride: a loop near Cebu IT Park with a speed profile that goes over 60 km/h.
  function startSimulation() {
    const profile = [0, 8, 18, 28, 36, 42, 45, 46, 48, 50, 54, 58, 62, 66, 70, 72, 71, 68, 63, 57, 50, 45, 44, 47, 52, 58, 64, 69, 66, 59, 50, 40, 30, 20, 10, 4];
    let i = 0, lat = 10.3299, lon = 123.9056, heading = 45;
    status("Demo ride (simulated GPS)");
    simTimer = setInterval(() => {
      const speed = profile[i % profile.length] + (Math.random() * 2 - 1);
      const metres = Math.max(speed, 0) / 3.6;                // distance in 1 second
      heading += (Math.random() * 16 - 8);
      lat += (metres * Math.cos((heading * Math.PI) / 180)) / 111320;
      lon += (metres * Math.sin((heading * Math.PI) / 180)) / (111320 * Math.cos((lat * Math.PI) / 180));
      addReading(lat, lon, Math.max(speed, 0), 5, Date.now());
      i++;
    }, 1000);
  }

  // ---- Sending readings to Django --------------------------------------
  async function flush() {
    if (!queue.length) return true;
    const batch = queue.splice(0, 60);
    try {
      const res = await fetch(URL, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": CSRF },
        body: JSON.stringify({ readings: batch }),
        credentials: "same-origin",
      });
      const data = await res.json();
      if (!res.ok) {
        if (res.status === 400) { showError(data.error || "Some readings were rejected."); return true; } // drop bad data
        throw new Error(data.error || `Server error ${res.status}`);
      }
      showError("");
      updateStats(data.stats);
      data.new_alerts.forEach(logAlert);
      return true;
    } catch (e) {
      queue.unshift(...batch); // keep them and retry on the next flush
      showError(`Couldn't save readings (${e.message}). Retrying…`);
      return false;
    }
  }

  function updateStats(s) {
    $("stat-distance").textContent = s.distance_km.toFixed(2);
    $("stat-max").textContent = s.max_speed_kmh;
    $("stat-alerts").textContent = s.alerts;
    $("stat-readings").textContent = s.readings;
  }

  function logAlert(a) {
    const list = $("alert-log");
    list.querySelector(".none")?.remove();
    const li = document.createElement("li");
    const time = new Date(a.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" });
    li.innerHTML = `<b>${a.speed_kmh} km/h</b> <span>${time}</span>`;
    list.prepend(li);
  }

  // ---- Start / pause / end ---------------------------------------------
  function start() {
    // Creating the AudioContext inside the click lets the browser play alert sounds later.
    audio = audio || new (window.AudioContext || window.webkitAudioContext)();
    running = true;
    $("btn-track").querySelector("span").textContent = "Pause tracking";
    if (SOURCE === "SIMULATED") {
      startSimulation();
    } else if (!("geolocation" in navigator)) {
      showError("This browser has no GPS support.");
    } else {
      status("Waiting for GPS…");
      watchId = navigator.geolocation.watchPosition(onPosition, onGpsError, { enableHighAccuracy: true, maximumAge: 0, timeout: 15000 });
    }
  }

  function pause() {
    running = false;
    if (watchId !== null) navigator.geolocation.clearWatch(watchId);
    clearInterval(simTimer);
    watchId = simTimer = null; last = null;
    status("Paused");
    $("btn-track").querySelector("span").textContent = "Resume tracking";
    flush();
  }

  $("btn-track").addEventListener("click", () => (running ? pause() : start()));

  // Save any unsent readings before ending the trip.
  $("end-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (running) pause();
    await flush();
    e.target.submit();
  });

  placeLimitTick();
  setInterval(() => running && flush(), FLUSH_EVERY_MS);
})();
