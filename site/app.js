/* WW Análisis Deportivo: lee los JSON de data/ y pinta las secciones. Sin dependencias. */
(() => {
  "use strict";

  const DATA = "data/";
  const FILES = ["meta", "fixtures", "standings", "teams", "predictions", "history", "performance"];
  const TZ = "Europe/Madrid";
  const VIEWS = ["jornada", "clasificacion", "equipos", "rendimiento"];
  const S = {};                       // estado: datos cargados
  const view = document.getElementById("view");

  /* ---------- Utilidades ---------- */
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const pct = (x) => `${Math.round(x * 100)}%`;
  const num = (x, d = 2) => Number(x).toLocaleString("es-ES", { minimumFractionDigits: d, maximumFractionDigits: d });

  // Redondea varios porcentajes para que sumen exactamente 100
  function to100(values) {
    const raw = values.map((v) => v * 100);
    const floors = raw.map(Math.floor);
    let rest = 100 - floors.reduce((a, b) => a + b, 0);
    raw.map((v, i) => [v - floors[i], i]).sort((a, b) => b[0] - a[0])
      .forEach(([, i]) => { if (rest > 0) { floors[i]++; rest--; } });
    return floors;
  }

  const fmt = (opts) => new Intl.DateTimeFormat("es-ES", { timeZone: TZ, ...opts });
  const fDay = fmt({ weekday: "long", day: "numeric", month: "long" });
  const fDayShort = fmt({ weekday: "short", day: "numeric", month: "short" });
  const fTime = fmt({ hour: "2-digit", minute: "2-digit" });
  const fFull = fmt({ day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });

  // football-data pone 00:00 UTC cuando la hora aún no está fijada
  const timeTbd = (iso) => /T00:00:00/.test(iso);
  const when = (iso, short = false) => {
    const d = new Date(iso);
    const day = (short ? fDayShort : fDay).format(d);
    return { day: day.charAt(0).toUpperCase() + day.slice(1), time: timeTbd(iso) ? "Hora por confirmar" : fTime.format(d) };
  };

  function crest(team, cls = "") {
    if (team.logo) {
      return `<img class="crest ${cls}" src="${esc(team.logo)}" alt="" width="28" height="28" loading="lazy"
        onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'crest crest--fallback ${cls}',textContent:'${esc(team.tla || "")}'}))">`;
    }
    return `<span class="crest crest--fallback ${cls}" aria-hidden="true">${esc(team.tla || "")}</span>`;
  }

  function split(p, { names } = {}) {
    const [h, d, a] = to100([p.home_win, p.draw, p.away_win]);
    const seg = (cls, val, who) =>
      `<span class="${cls}${val < 9 ? " tight" : ""}" style="flex:${Math.max(val, 1)}" title="${who}: ${val}%">${val}%</span>`;
    const label = names
      ? `Probabilidades: victoria de ${names[0]} ${h}%, empate ${d}%, victoria de ${names[1]} ${a}%`
      : `Local ${h}%, empate ${d}%, visitante ${a}%`;
    return `<div class="split" role="img" aria-label="${esc(label)}">${seg("h", h, "Local")}${seg("d", d, "Empate")}${seg("a", a, "Visitante")}</div>`;
  }

  const FORM_LABEL = { W: "V", D: "E", L: "D" };
  const FORM_TITLE = { W: "Victoria", D: "Empate", L: "Derrota" };
  const form = (list) => `<span class="form" aria-label="Últimos resultados: ${list.map((r) => FORM_TITLE[r]).join(", ")}">${
    list.map((r) => `<i class="${r}" title="${FORM_TITLE[r]}">${FORM_LABEL[r]}</i>`).join("")}</span>`;

  const teamStats = (id) => S.teams.find((t) => t.team.id === id);
  const standing = (id) => S.standings.find((r) => r.team.id === id);
  const fact = (label, value, note = "") => `<div class="fact"><dt>${label}</dt><dd>${value}${note ? ` <small>${note}</small>` : ""}</dd></div>`;

  // scale: factor para el ancho de la barra (por defecto el valor es la proporción del 100%)
  function bars(rows, scale = 1) {
    return `<ul class="bars">${rows.map(([label, v, isRef]) => `
      <li><span>${label}</span><span class="track"><span class="fill${isRef ? " ref" : ""}" style="width:${Math.min(v * scale * 100, 100)}%"></span></span>
      <span class="val">${pct(v)}</span></li>`).join("")}</ul>`;
  }

  /* ---------- Jornada ---------- */
  function renderJornada() {
    const preds = S.predictions.matches;
    const live = S.fixtures.filter((f) => f.status === "LIVE" || f.status === "HT");
    let html = "";

    if (live.length) {
      html += `<section><div class="section-head"><h2>En juego</h2><p>Marcador con posible retraso de unos minutos</p></div>
        <div class="live-strip">${live.map((f) => `
          <div class="panel live-card">
            <span class="badge">${f.status === "HT" ? "Descanso" : "En juego"}</span>
            <span class="team-line t-home">${esc(f.home.name)} ${crest(f.home)}</span>
            <span class="score">${f.goals.home ?? 0} - ${f.goals.away ?? 0}</span>
            <span class="team-line t-away">${crest(f.away)} ${esc(f.away.name)}</span>
          </div>`).join("")}</div></section>`;
    }

    if (!preds.length) {
      html += `<div class="panel empty"><strong>No hay partidos pendientes</strong>Las predicciones de la próxima jornada aparecerán en cuanto se publique el calendario.</div>`;
    } else {
      const [first, ...rest] = preds;
      html += featured(first);
      const rounds = [...new Set(rest.map((m) => m.round))];
      for (const round of rounds) {
        const list = rest.filter((m) => m.round === round);
        html += `<section><div class="section-head"><h2>${esc(round)}</h2>
          <p>Pulsa un partido para ver goles, ambos marcan y marcadores probables</p></div>
          <ul class="panel fixtures">${list.map(fixtureRow).join("")}</ul></section>`;
      }
    }

    html += recentResults();
    view.innerHTML = html;

    view.querySelectorAll(".fixture__row").forEach((btn) => btn.addEventListener("click", () => {
      const open = btn.getAttribute("aria-expanded") === "true";
      btn.setAttribute("aria-expanded", String(!open));
      document.getElementById(btn.getAttribute("aria-controls")).hidden = open;
    }));
  }

  function featured(m) {
    const p = m.prediction, w = when(m.date);
    return `<section class="panel feature" aria-labelledby="feat-title">
      <p class="feature__when" id="feat-title">Próximo partido: ${esc(m.round)}, ${w.day}, ${w.time}</p>
      <div class="feature__teams">
        <div class="feature__team">${crest(m.home, "crest--lg")}<h3>${esc(m.home.name)}</h3></div>
        <span class="feature__vs">contra</span>
        <div class="feature__team feature__team--away">${crest(m.away, "crest--lg")}<h3>${esc(m.away.name)}</h3></div>
      </div>
      ${split(p.probabilities, { names: [m.home.name, m.away.name] })}
      <div class="feature__legend"><span>Gana ${esc(m.home.name)}</span><span>Empate</span><span>Gana ${esc(m.away.name)}</span></div>
      <dl class="feature__facts">
        ${fact("Goles esperados", `${num(p.expected_goals.home)} - ${num(p.expected_goals.away)}`)}
        ${fact("Más de 2,5 goles", pct(p.over_under.over_2_5))}
        ${fact("Marcan ambos", pct(p.btts.yes))}
        ${fact("Marcador más probable", esc(p.top_scores[0].score), pct(p.top_scores[0].probability))}
      </dl>
      <div class="fixture__detail" style="padding:22px 0 0">${detail(m, { featured: true })}</div>
    </section>`;
  }

  function fixtureRow(m) {
    const w = when(m.date, true), id = `fx-${m.fixture_id}`;
    return `<li class="fixture">
      <button class="fixture__row" aria-expanded="false" aria-controls="${id}">
        <span class="fixture__time"><strong>${timeTbd(m.date) ? "—" : w.time}</strong>${w.day}</span>
        <span class="fixture__teams">
          <span class="team-line">${crest(m.home)}<span>${esc(m.home.name)}</span></span>
          <span class="team-line">${crest(m.away)}<span>${esc(m.away.name)}</span></span>
        </span>
        ${split(m.prediction.probabilities, { names: [m.home.name, m.away.name] })}
        <span class="fixture__chev" aria-hidden="true"></span>
      </button>
      <div class="fixture__detail" id="${id}" hidden>${detail(m)}</div>
    </li>`;
  }

  function detail(m, { featured = false } = {}) {
    const p = m.prediction;
    const h = teamStats(m.home.id), a = teamStats(m.away.id);
    const side = (t, s, where) => !t ? "" : `
      <div><h4>${esc(t.team.name)} ${where === "home" ? "en casa" : "fuera"}</h4>
        <p>${s.played} partidos: ${s.wins} V, ${s.draws} E, ${s.losses} D. Goles ${s.goals_for} a favor y ${s.goals_against} en contra.</p>
        <p style="margin-top:6px">${form(t.form)}</p></div>`;
    return `<div class="detail-grid">
      ${featured ? "" : `<div><h4>Goles en el partido</h4>${bars([
        ["Más de 1,5", p.over_under.over_1_5], ["Más de 2,5", p.over_under.over_2_5],
        ["Más de 3,5", p.over_under.over_3_5], ["Marcan ambos", p.btts.yes]])}</div>`}
      <div><h4>Marcadores más probables</h4>${bars(p.top_scores.map((s) => [s.score, s.probability]), 1 / p.top_scores[0].probability)}</div>
      ${side(h, h?.home, "home")}${side(a, a?.away, "away")}
    </div>`;
  }

  function recentResults() {
    const done = S.fixtures.filter((f) => f.status === "FT");
    if (!done.length) return "";
    const lastRound = done[done.length - 1].round;
    const list = done.filter((f) => f.round === lastRound);
    return `<section><div class="section-head"><h2>Resultados: ${esc(lastRound)}</h2></div>
      <ul class="panel results">${list.map((f) => {
        const h = S.history[String(f.id)];
        let verdict = "";
        if (h && h.evaluation) {
          const ev = h.evaluation, probs = h.prediction.probabilities;
          const label = { home_win: `${h.home.name}`, draw: "empate", away_win: `${h.away.name}` }[ev.predicted];
          verdict = `Favorito: ${esc(label)} (${pct(probs[ev.predicted])}) <span class="${ev.hit ? "hit" : "miss"}">${ev.hit ? "acierto" : "fallo"}</span>`;
        }
        return `<li class="result">
          <span class="team-line home">${crest(f.home)}<span>${esc(f.home.name)}</span></span>
          <span class="score">${f.goals.home} - ${f.goals.away}</span>
          <span class="team-line">${crest(f.away)}<span>${esc(f.away.name)}</span></span>
          <span class="verdict">${verdict}</span></li>`;
      }).join("")}</ul></section>`;
  }

  /* ---------- Clasificación ---------- */
  function renderClasificacion() {
    const rows = S.standings;
    if (!rows.length) { view.innerHTML = `<div class="panel empty"><strong>Clasificación no disponible</strong>Se mostrará tras la próxima actualización de datos.</div>`; return; }
    view.innerHTML = `<section><div class="section-head"><h2>Clasificación</h2><p>Pulsa un equipo para ver sus estadísticas</p></div>
      <div class="panel table-wrap"><table>
        <caption class="sr-only">Clasificación de la liga</caption>
        <thead><tr><th scope="col" class="t-pos">#</th><th scope="col" class="t-team">Equipo</th>
          <th scope="col" title="Partidos jugados">PJ</th><th scope="col" class="hide-sm" title="Victorias">V</th>
          <th scope="col" class="hide-sm" title="Empates">E</th><th scope="col" class="hide-sm" title="Derrotas">D</th>
          <th scope="col" class="hide-sm" title="Goles a favor y en contra">Goles</th><th scope="col" title="Diferencia de goles">DG</th>
          <th scope="col">Pts</th><th scope="col" class="hide-sm">Últimos 5</th></tr></thead>
        <tbody>${rows.map((r) => {
          const t = teamStats(r.team.id);
          return `<tr><td class="t-pos">${r.rank}</td>
            <td class="t-team"><a href="#equipos/${r.team.id}">${crest(r.team)}<span>${esc(r.team.name)}</span></a></td>
            <td>${r.played}</td><td class="hide-sm">${r.win}</td><td class="hide-sm">${r.draw}</td><td class="hide-sm">${r.lose}</td>
            <td class="hide-sm">${r.goals_for}:${r.goals_against}</td><td>${r.goal_diff > 0 ? "+" : ""}${r.goal_diff}</td>
            <td class="t-pts">${r.points}</td><td class="hide-sm">${t ? form(t.form) : ""}</td></tr>`;
        }).join("")}</tbody></table></div></section>`;
  }

  /* ---------- Equipos ---------- */
  function leagueAvg(key) {
    return S.teams.reduce((s, t) => s + t[key], 0) / (S.teams.length || 1);
  }

  function renderEquipos(teamId) {
    const sorted = [...S.teams].sort((a, b) => a.team.name.localeCompare(b.team.name, "es"));
    if (!sorted.length) { view.innerHTML = `<div class="panel empty"><strong>Sin estadísticas todavía</strong>Aparecerán cuando se juegue la primera jornada.</div>`; return; }
    const id = Number(teamId) || S.standings[0]?.team.id || sorted[0].team.id;
    const t = teamStats(id) || sorted[0];
    const st = standing(t.team.id);
    const next = S.predictions.matches.find((m) => m.home.id === t.team.id || m.away.id === t.team.id);

    const rates = [
      ["Portería a cero", "clean_sheets_rate"], ["Se queda sin marcar", "failed_to_score_rate"],
      ["Marcan ambos", "btts_rate"], ["Más de 2,5 goles", "over_2_5_rate"],
    ];
    const splitRow = (label, s) => `<tr><th scope="row">${label}</th><td>${s.played}</td><td>${s.wins}</td><td>${s.draws}</td><td>${s.losses}</td>
      <td>${s.goals_for}:${s.goals_against}</td><td>${s.played ? num((s.wins * 3 + s.draws) / s.played) : "—"}</td></tr>`;

    let nextHtml = `<p class="lede">No tiene partidos en las próximas jornadas.</p>`;
    if (next) {
      const w = when(next.date);
      nextHtml = `<p class="lede" style="margin-bottom:12px">${esc(next.home.name)} contra ${esc(next.away.name)}. ${w.day}, ${w.time}.</p>
        ${split(next.prediction.probabilities, { names: [next.home.name, next.away.name] })}
        <div class="feature__legend"><span>${esc(next.home.name)}</span><span>Empate</span><span>${esc(next.away.name)}</span></div>`;
    }

    view.innerHTML = `
      <div class="team-picker"><label for="team-select">Equipo</label>
        <select id="team-select">${sorted.map((x) => `<option value="${x.team.id}"${x.team.id === t.team.id ? " selected" : ""}>${esc(x.team.name)}</option>`).join("")}</select></div>
      <section class="panel team-hero">${crest(t.team, "crest--lg")}
        <div><h2>${esc(t.team.full_name || t.team.name)}</h2>
        <p>${st ? `${st.rank}º con ${st.points} puntos tras ${st.played} partidos.` : ""} Últimos resultados: ${form(t.form)}</p></div></section>
      <div class="team-grid">
        <section class="panel"><h3>Goles por partido</h3>
          <dl class="facts-row">
            ${fact("A favor", num(t.avg_goals_for), `media liga ${num(leagueAvg("avg_goals_for"))}`)}
            ${fact("En contra", num(t.avg_goals_against), `media liga ${num(leagueAvg("avg_goals_against"))}`)}
          </dl></section>
        <section class="panel"><h3>Con qué frecuencia…</h3>
          ${bars(rates.map(([l, k]) => [l, t[k]]))}
          <p class="metric__note">Media de la liga: ${rates.map(([l, k]) => `${l.toLowerCase()} ${pct(leagueAvg(k))}`).join(", ")}.</p></section>
        <section class="panel"><h3>En casa y fuera</h3>
          <table class="splits"><thead><tr><th scope="col"></th><th scope="col">PJ</th><th scope="col">V</th><th scope="col">E</th><th scope="col">D</th><th scope="col">Goles</th><th scope="col" title="Puntos por partido">Pts/PJ</th></tr></thead>
          <tbody>${splitRow("Casa", t.home)}${splitRow("Fuera", t.away)}</tbody></table></section>
        <section class="panel"><h3>Próximo partido</h3>${nextHtml}</section>
      </div>`;

    document.getElementById("team-select").addEventListener("change", (e) => {
      history.replaceState(null, "", `#equipos/${e.target.value}`);
      renderEquipos(e.target.value);
    });
  }

  /* ---------- Rendimiento ---------- */
  function renderRendimiento() {
    const bt = S.performance.backtest || {}, live = S.performance.live || {};
    const evaluated = Object.values(S.history).filter((h) => h.evaluation).reverse();

    const metricBlock = (title, m, note) => !m.matches ? "" : `
      <section><div class="section-head"><h2>${title}</h2><p>${m.matches} partidos</p></div>
        <p class="lede" style="margin-bottom:16px">${note}</p>
        <div class="metrics">
          <div class="panel metric"><div class="metric__value">${pct(m.accuracy_1x2)}</div>
            <div class="metric__name">Acierto del resultado (1X2)</div>
            ${bars([["Modelo", m.accuracy_1x2], ["Al azar", 1 / 3, true]])}
            <p class="metric__note">Partidos en los que el resultado más probable según el modelo fue el que ocurrió.</p></div>
          ${m.accuracy_over_2_5 != null ? `<div class="panel metric"><div class="metric__value">${pct(m.accuracy_over_2_5)}</div>
            <div class="metric__name">Acierto en más/menos de 2,5 goles</div>
            ${bars([["Modelo", m.accuracy_over_2_5], ["Al azar", 0.5, true]])}
            <p class="metric__note">Si el modelo daba más del 50% a "más de 2,5 goles", ¿hubo 3 goles o más?</p></div>` : ""}
          <div class="panel metric"><div class="metric__value">${num(m.avg_brier, 3)}</div>
            <div class="metric__name">Calibración (Brier, más bajo es mejor)</div>
            <p class="metric__note">Mide si los porcentajes son fiables, no solo si acierta el favorito. Repartir 33% a cada resultado daría 0,667. ${
              m.avg_brier < 0.667 ? `El modelo mejora esa referencia en ${num((0.667 - m.avg_brier) / 0.667 * 100, 0)}%.` : ""}</p></div>
        </div></section>`;

    const liveHtml = live.matches
      ? metricBlock("Predicciones publicadas", live,
        "Predicciones guardadas antes de empezar cada partido y comparadas con el resultado final. Es la medida más honesta.")
      : `<section><div class="section-head"><h2>Predicciones publicadas</h2></div>
          <div class="panel empty"><strong>Aún no hay predicciones evaluadas</strong>Las predicciones se guardan antes de cada partido y se comparan con el resultado al terminar. Las primeras aparecerán aquí al acabar la próxima jornada.</div></section>`;
    const simHtml = metricBlock("Simulación con la temporada actual", bt,
      "Cada partido ya jugado se predice usando solo los partidos anteriores a él, como si el modelo hubiera estado funcionando desde el principio.");
    // Con predicciones reales evaluadas, van primero; si no, primero la simulación
    let html = live.matches ? liveHtml + simHtml : simHtml + liveHtml;

    if (evaluated.length) {
      html += `<section><div class="section-head"><h2>Últimas predicciones evaluadas</h2></div>
        <ul class="panel results">${evaluated.slice(0, 20).map((h) => {
          const ev = h.evaluation, probs = h.prediction.probabilities;
          const label = { home_win: h.home.name, draw: "empate", away_win: h.away.name }[ev.predicted];
          return `<li class="result">
            <span class="team-line home">${crest(h.home)}<span>${esc(h.home.name)}</span></span>
            <span class="score">${h.result.home} - ${h.result.away}</span>
            <span class="team-line">${crest(h.away)}<span>${esc(h.away.name)}</span></span>
            <span class="verdict">Favorito: ${esc(label)} (${pct(probs[ev.predicted])}) <span class="${ev.hit ? "hit" : "miss"}">${ev.hit ? "acierto" : "fallo"}</span></span></li>`;
        }).join("")}</ul></section>`;
    }

    const model = S.predictions.model || {};
    html += `<section class="prose"><div class="section-head"><h2>Cómo se calculan las probabilidades</h2></div>
      <p>Cada equipo recibe una <strong>fuerza de ataque</strong> y una <strong>fuerza defensiva</strong> según los goles que marca y encaja, comparados con la media de la liga${
        model.league_home_goals_avg ? ` (ahora ${num(model.league_home_goals_avg)} goles por partido del local y ${num(model.league_away_goals_avg)} del visitante)` : ""}.</p>
      <p>Con esas fuerzas se estiman los <strong>goles esperados</strong> de cada equipo en el partido, y una distribución de Poisson convierte esos goles esperados en la probabilidad de cada marcador. Sumando marcadores salen la victoria local, el empate, la victoria visitante, los goles totales y si marcan ambos.</p>
      <p>Dos ajustes evitan conclusiones precipitadas: los partidos recientes pesan más que los antiguos, y con pocos partidos jugados las fuerzas se acercan a la media de la liga.</p>
      <p>El modelo se recalcula solo después de cada partido${model.matches_used ? ` y ahora usa ${model.matches_used} resultados` : ""}.</p></section>`;

    view.innerHTML = html;
  }

  /* ---------- Navegación ---------- */
  function route() {
    const [name, param] = (location.hash.replace("#", "") || "jornada").split("/");
    const current = VIEWS.includes(name) ? name : "jornada";
    document.querySelectorAll(".tabs a").forEach((a) => {
      if (a.dataset.view === current) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    });
    ({ jornada: renderJornada, clasificacion: renderClasificacion, equipos: () => renderEquipos(param), rendimiento: renderRendimiento })[current]();
    const titles = { jornada: "Jornada", clasificacion: "Clasificación", equipos: "Equipos", rendimiento: "Rendimiento del modelo" };
    document.title = `${titles[current]}: WW Análisis Deportivo`;
  }

  async function load() {
    try {
      const results = await Promise.all(FILES.map((f) =>
        fetch(`${DATA}${f}.json`, { cache: "no-cache" }).then((r) => {
          if (!r.ok) throw new Error(`${f}.json (${r.status})`);
          return r.json();
        })));
      FILES.forEach((f, i) => { S[f] = results[i]; });
    } catch (err) {
      view.innerHTML = `<div class="panel error"><strong>No se han podido cargar los datos.</strong>
        <p>Comprueba la conexión y recarga la página. Detalle: ${esc(err.message)}</p></div>`;
      document.getElementById("updated").textContent = "";
      return;
    }
    const last = S.meta.last_update ? fFull.format(new Date(S.meta.last_update)) : "";
    document.getElementById("updated").textContent = last ? `LaLiga ${S.meta.season}-${String(S.meta.season + 1).slice(2)}. Actualizado el ${last}` : "";
    route();
  }

  window.addEventListener("hashchange", () => { route(); if (!location.hash.startsWith("#equipos/")) window.scrollTo(0, 0); });
  load();
})();
