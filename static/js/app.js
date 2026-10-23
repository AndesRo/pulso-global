/* Pulso Global · interfaz */
(() => {
    'use strict';

    const $ = (s, el = document) => el.querySelector(s);
    const $$ = (s, el = document) => [...el.querySelectorAll(s)];
    const MINUS = '−';
    const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
    const REFRESH_MS = 60000;
    const FETCH_TIMEOUT_MS = 45000;
    const reduceMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;

    /* ---------- Formato (es-CL) ---------- */
    const nfc = {};
    const nf = d => nfc[d] ||= new Intl.NumberFormat('es-CL', { minimumFractionDigits: d, maximumFractionDigits: d, useGrouping: 'always' });
    const fmt = (v, d = 2) => (v == null || isNaN(v)) ? '—' : nf(d).format(v);
    const sgn = (v, d = 2, suf = '%') => (v == null || isNaN(v)) ? '—' : (v > 0 ? '+' : v < 0 ? MINUS : '') + nf(d).format(Math.abs(v)) + suf;
    const arrow = v => v > 0 ? '▲' : v < 0 ? '▼' : '■';
    const cls = v => v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
    const chgTxt = i => i.chg1u === 'pb' ? sgn(i.chg1, 1, ' pb') : sgn(i.chg1, 2, '%');
    const fdate = iso => { const [y, m, d] = iso.split('-'); return `${d}-${m}-${y}`; };
    const timeFmt = new Intl.DateTimeFormat('es-CL', { hour: '2-digit', minute: '2-digit', hour12: false });

    /* ---------- Estado ---------- */
    const S = {
        data: null, byId: {}, prev: {}, tab: 'resumen', seg: { mercados: 'indices', macro: 'inflacion' },
        sheet: null, range: 90, err: null, conv: { amt: 1000, from: 'USD' }, lastOk: 0, opener: null, loading: false
    };
    const view = $('#view'), sheet = $('#sheet'), app = $('#app'), root = document.documentElement;

    const SHORT = {
        spx: 'SPX', ndx: 'NDX', dji: 'DJI', sx5e: 'SX5E', ftse: 'FTSE', n225: 'N225', hsi: 'HSI', bvsp: 'BVSP', ipsa: 'IPSA',
        vix: 'VIX', tnx: '10Y', dxy: 'DXY', gold: 'XAU', silver: 'XAG', wti: 'WTI', brent: 'BRT', copper: 'Cu', gas: 'NG',
        btc: 'BTC', eth: 'ETH', sol: 'SOL', eurusd: 'EUR', gbpusd: 'GBP', usdjpy: 'JPY', usdcny: 'CNY', usdbrl: 'BRL', usdmxn: 'MXN',
        usdchf: 'CHF', usdclp: 'CLP', uf: 'UF', cobre: 'Cu'
    };
    const SRC = { yahoo: 'Yahoo Finance', frankfurter: 'Frankfurter · BCE', mindicador: 'mindicador.cl', bancomundial: 'Banco Mundial', alternativeme: 'alternative.me' };
    const ESTADO = { ok: 'Operativa', parcial: 'Parcial', error: 'Sin respuesta' };
    const ICON = {
        resumen: '<path d="M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h6v6h-6z"/>',
        mercados: '<path d="M3 17l6-6 4 4 8-9"/><path d="M15 6h6v6"/>',
        divisas: '<path d="M7 7h13l-3-3M17 17H4l3 3"/>',
        cripto: '<circle cx="12" cy="12" r="9"/><path d="M10 7v10M10 8h3.2a2 2 0 010 4H10m0 0h3.6a2 2 0 010 4H10"/>',
        chile: '<path d="M3 19l6-10 4 6 3-4 5 8z"/>',
        macro: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
        alertas: '<path d="M6 16v-5a6 6 0 0112 0v5l2 2H4zM10 20a2 2 0 004 0"/>'
    };
    const TABS = [['resumen', 'Resumen'], ['mercados', 'Mercados'], ['divisas', 'Divisas'], ['cripto', 'Cripto'], ['chile', 'Chile'], ['macro', 'Macro'], ['alertas', 'Alertas']];
    const TAB_IDS = TABS.map(t => t[0]);

    /* ---------- Gráficos SVG ---------- */
    let gid = 0;
    function spark(vals, color, { fill = true, w = 100, h = 32 } = {}) {
        if (!vals || vals.length < 2) return '';
        const id = 'g' + (gid++), mn = Math.min(...vals), mx = Math.max(...vals), sp = (mx - mn) || 1;
        const d = vals.map((v, i) => (i ? 'L' : 'M') + (i / (vals.length - 1) * w).toFixed(1) + ' ' + (h - 3 - (v - mn) / sp * (h - 6)).toFixed(1)).join('');
        return `<svg class="spark" viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" aria-hidden="true"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="${color}" stop-opacity=".38"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
    ${fill ? `<path d="${d}L${w} ${h}L0 ${h}Z" fill="url(#${id})"/>` : ''}
    <path d="${d}" fill="none" stroke="${color}" stroke-width="1.7" vector-effect="non-scaling-stroke" stroke-linejoin="round" stroke-linecap="round"/></svg>`;
    }
    const colOf = v => v > 0 ? '#34d399' : v < 0 ? '#fb7185' : '#94a3b8';
    const smaArr = (v, n) => v.map((_, i) => i < n - 1 ? null : v.slice(i - n + 1, i + 1).reduce((a, b) => a + b, 0) / n);

    const CH = { W: 360, H: 190, pl: 8, pr: 8, pt: 14, pb: 20 };
    function bigChart(it, range, anim) {
        const n = it.series.length; let from = 0;
        if (range < 90) {
            const c = new Date(it.dates[n - 1]); c.setDate(c.getDate() - range);
            from = Math.max(0, it.dates.findIndex(d => new Date(d) >= c));
        }
        const v = it.series.slice(from), d = it.dates.slice(from), s7 = smaArr(it.series, 7).slice(from);
        const { W, H, pl, pr, pt, pb } = CH;
        const mn = Math.min(...v), mx = Math.max(...v), sp = (mx - mn) || 1;
        const X = i => pl + i / (v.length - 1) * (W - pl - pr), Y = x => pt + (1 - (x - mn) / sp) * (H - pt - pb);
        const line = arr => arr.map((x, i) => x == null ? '' : (i === 0 || arr[i - 1] == null ? 'M' : 'L') + X(i).toFixed(1) + ' ' + Y(x).toFixed(1)).join('');
        const col = colOf(v[v.length - 1] - v[0]), id = 'b' + (gid++);
        const grid = [0, .5, 1].map(f => {
            const y = pt + f * (H - pt - pb), val = mx - f * sp;
            return `<line x1="${pl}" x2="${W - pr}" y1="${y}" y2="${y}" stroke="rgba(255,255,255,.07)"/><text x="${pl + 2}" y="${y - 3}" fill="#7a84a1" font-size="9">${fmt(val, it.dec > 2 ? 2 : it.dec)}</text>`;
        }).join('');
        const dd = line(v);
        return `<svg viewBox="0 0 ${W} ${H}" id="bc" data-from="${from}" role="img" aria-label="Gráfico de ${esc(it.name)}, últimos ${range === 30 ? '30 días' : '3 meses'}"><defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="${col}" stop-opacity=".32"/><stop offset="1" stop-color="${col}" stop-opacity="0"/></linearGradient></defs>${grid}
    <path d="${dd}L${X(v.length - 1)} ${H - pb}L${X(0)} ${H - pb}Z" fill="url(#${id})"/>
    <path d="${line(s7)}" fill="none" stroke="#fbbf24" stroke-width="1.1" stroke-dasharray="3 3" opacity=".75"/>
    <path ${anim ? 'class="dr" pathLength="1"' : ''} d="${dd}" fill="none" stroke="${col}" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"/>
    <text x="${pl}" y="${H - 5}" fill="#7a84a1" font-size="9">${fdate(d[0])}</text>
    <text x="${W - pr}" y="${H - 5}" fill="#7a84a1" font-size="9" text-anchor="end">${fdate(d[d.length - 1])}</text>
    <line id="xh" y1="${pt}" y2="${H - pb}" stroke="rgba(255,255,255,.35)" stroke-dasharray="2 3" opacity="0"/>
    <circle id="xd" r="4" fill="${col}" stroke="#fff" stroke-width="1.5" opacity="0"/></svg>`;
    }
    function bindChart(it) {
        const svg = $('#bc'), tip = $('#tip'); if (!svg) return;
        const from = +svg.dataset.from, v = it.series.slice(from), d = it.dates.slice(from);
        const { W, H, pl, pr, pt, pb } = CH;
        const mn = Math.min(...v), mx = Math.max(...v), sp = (mx - mn) || 1;
        const move = e => {
            const r = svg.getBoundingClientRect(), x = (e.clientX - r.left) / r.width * W;
            const i = Math.max(0, Math.min(v.length - 1, Math.round((x - pl) / (W - pl - pr) * (v.length - 1))));
            const cx = pl + i / (v.length - 1) * (W - pl - pr), cy = pt + (1 - (v[i] - mn) / sp) * (H - pt - pb);
            $('#xh').setAttribute('x1', cx); $('#xh').setAttribute('x2', cx); $('#xh').setAttribute('opacity', 1);
            $('#xd').setAttribute('cx', cx); $('#xd').setAttribute('cy', cy); $('#xd').setAttribute('opacity', 1);
            tip.innerHTML = `<b>${fmt(v[i], it.dec)}</b>${fdate(d[i])}`;
            tip.style.opacity = 1;
            const px = cx / W * r.width;
            tip.style.transform = `translate(${Math.max(0, Math.min(r.width - tip.offsetWidth, px - tip.offsetWidth / 2))}px, 0)`;
        };
        const hide = () => { tip.style.opacity = 0;['xh', 'xd'].forEach(k => $('#' + k)?.setAttribute('opacity', 0)); };
        svg.addEventListener('pointermove', move); svg.addEventListener('pointerdown', move); svg.addEventListener('pointerleave', hide);
    }

    function gauge(val) {
        return `<svg class="gauge" viewBox="0 0 200 112" role="img" aria-label="Índice de miedo y codicia: ${val} de 100"><defs><linearGradient id="gg" x1="0" x2="1"><stop offset="0" stop-color="#fb7185"/><stop offset=".38" stop-color="#fb923c"/><stop offset=".62" stop-color="#facc15"/><stop offset="1" stop-color="#34d399"/></linearGradient></defs>
  <path d="M20 100A80 80 0 0 1 180 100" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="14" stroke-linecap="round"/>
  <path d="M20 100A80 80 0 0 1 180 100" fill="none" stroke="url(#gg)" stroke-width="14" stroke-linecap="round" opacity=".92"/>
  <g class="needle" data-ang="${-90 + val * 1.8}"><line x1="100" y1="100" x2="100" y2="36" stroke="#fff" stroke-width="3.2" stroke-linecap="round"/><circle cx="100" cy="100" r="6.5" fill="#fff"/></g></svg>`;
    }
    const fgLabel = v => v < 25 ? 'Miedo extremo' : v < 45 ? 'Miedo' : v <= 55 ? 'Neutral' : v < 75 ? 'Codicia' : 'Codicia extrema';
    const vixLabel = v => v < 15 ? 'calma' : v < 20 ? 'normal' : v < 30 ? 'tensión' : 'pánico';

    /* ---------- Componentes ---------- */
    const item = id => S.byId[id];
    const sparkOf = (i, n = 40) => spark(i.series.slice(-n), colOf(i.chg30 ?? i.chg1), { fill: false });

    function rowHTML(i) {
        return `<div class="card row g-${i.group}" data-open="${i.id}" role="button" tabindex="0" aria-label="${esc(i.name)}: ${fmt(i.value, i.dec)}, ${chgTxt(i)}. Ver detalle">
    <div class="badge" aria-hidden="true">${SHORT[i.id] || esc(i.name.slice(0, 3).toUpperCase())}</div>
    <div><div class="nm">${esc(i.name)}</div><div class="sb">${esc(i.sym || '')}${i.sym ? ' · ' : ''}${esc(i.unit)}</div></div>
    <div class="sp">${sparkOf(i)}</div>
    <div class="px"><b data-fid="${i.id}">${fmt(i.value, i.dec)}</b><span class="pill ${cls(i.chg1)}">${arrow(i.chg1)} ${chgTxt(i)}</span></div></div>`;
    }
    function kpiHTML(i, label) {
        return `<div class="card kpi" data-open="${i.id}" role="button" tabindex="0" aria-label="${esc(label || i.name)}: ${fmt(i.value, i.dec)}, ${chgTxt(i)}. Ver detalle">
    <div class="n"><span>${esc(label || i.name)}</span><span class="${cls(i.chg1)}" aria-hidden="true">${arrow(i.chg1)}</span></div>
    <div class="v" data-fid="${i.id}">${fmt(i.value, i.dec > 2 ? 2 : i.dec)}</div>
    <span class="pill ${cls(i.chg1)}">${chgTxt(i)}</span><div class="s">${sparkOf(i, 30)}</div></div>`;
    }
    function alertText(a) {
        const pb = a.unidad === 'pb';
        if (a.tipo === 'variacion') return `Variación diaria de ${sgn(a.valor, pb ? 1 : 2, pb ? ' pb' : '%')} (umbral ${fmt(a.umbral, pb ? 0 : 1)}${pb ? ' pb' : '%'})`;
        if (a.tipo === 'atipico') return `Movimiento atípico: z-score ${sgn(a.valor, 1, '')}`;
        if (a.tipo === 'maximo') return 'Nuevo máximo de 3 meses';
        return 'Nuevo mínimo de 3 meses';
    }
    const RANK = { alta: 0, media: 1, info: 2 };
    const alertGroups = () => S.data.items.filter(i => i.alerts.length)
        .map(i => ({ i, lvl: i.alerts.map(a => a.nivel).sort((x, y) => RANK[x] - RANK[y])[0] }))
        .sort((x, y) => RANK[x.lvl] - RANK[y.lvl] || Math.abs(y.i.z) - Math.abs(x.i.z));
    const list = rows => `<div class="list">${rows.map(rowHTML).join('')}</div>`;

    /* ---------- Vistas ---------- */
    const V = {};
    V.resumen = () => {
        const d = S.data, spx = item('spx') || d.items.find(i => i.group === 'indices');
        const idx = d.items.filter(i => i.group === 'indices'), up = idx.filter(i => i.chg1 > 0).length;
        const vix = item('vix'), fg = d.feargreed;
        const movers = d.items.filter(i => i.kind === 'serie' && !i.rate && i.group !== 'riesgo').sort((a, b) => Math.abs(b.chg1) - Math.abs(a.chg1)).slice(0, 6);
        const kp = [['usdclp', 'Dólar · CLP'], ['cobre', 'Cobre · USD/lb'], ['gold', 'Oro'], ['wti', 'Petróleo WTI'], ['btc', 'Bitcoin'], ['tnx', 'Bono 10Y EE.UU.'], ['vix', 'VIX'], ['dxy', 'Índice dólar']]
            .map(([id, l]) => item(id) && kpiHTML(item(id), l)).filter(Boolean).join('');
        const hero = spx ? `<div class="card hero" data-open="${spx.id}" role="button" tabindex="0" aria-label="${esc(spx.name)}: ${fmt(spx.value, spx.dec)}. Ver detalle">
    <div class="lbl"><span>${esc(spx.name)}</span><span>${esc(spx.source)}</span></div>
    <div class="big cu" data-v="${spx.value}" data-d="${spx.dec}" data-fid="${spx.id}">${fmt(spx.value, spx.dec)}</div>
    <span class="pill ${cls(spx.chg1)}">${arrow(spx.chg1)} ${chgTxt(spx)}</span> <span class="pill ${cls(spx.chg30)}">30d ${sgn(spx.chg30)}</span>
    <div class="chips">
      ${idx.length ? `<span class="chip">Bolsas al alza <b>${up}/${idx.length}</b></span>` : ''}
      ${vix ? `<span class="chip">VIX <b>${fmt(vix.value, 1)} · ${vixLabel(vix.value)}</b></span>` : ''}
      ${fg ? `<span class="chip">Cripto <b>${fg.value} · ${fgLabel(fg.value)}</b></span>` : ''}
    </div>
    <div class="chart">${spark(spx.series, colOf(spx.chg30), { h: 60 })}</div></div>` : '';
        const gaugeCard = fg ? `<div class="card gwrap"><h2 class="h">Sentimiento cripto</h2>${gauge(fg.value)}
    <div><div class="gv cu" data-v="${fg.value}" data-d="0">${fg.value}</div><div class="gl">${fgLabel(fg.value)}</div>
    <div class="gs">Índice Fear &amp; Greed (0 = miedo extremo, 100 = codicia extrema)</div></div></div>` : '';
        const fuentes = `<div class="card"><h2 class="h flush">Fuentes de datos</h2><div class="srows">${Object.entries(d.fuentes).map(([k, f]) => {
            const msg = f.error || ((f.fallidos || []).length ? 'Sin datos de: ' + f.fallidos.join(', ') : '');
            return `<div class="srow ${f.estado}"><span class="sdot"></span><b>${SRC[k] || k}</b><span class="sst">${ESTADO[f.estado] || f.estado}</span>${msg ? `<small>${esc(msg)}</small>` : ''}</div>`;
        }).join('')}</div></div>`;
        return `
  ${hero || gaugeCard ? `<div class="res-top">${hero}${gaugeCard}</div>` : ''}
  <h2 class="h">Lo más importante</h2><div class="kpis">${kp}</div>
  <div class="res-cols">
    <section><h2 class="h">Mayores movimientos del día</h2>${list(movers)}</section>
    <section><h2 class="h">Estado del servicio</h2>${fuentes}</section>
  </div>`;
    };
    V.mercados = () => {
        const s = S.seg.mercados, segs = [['indices', 'Bolsas'], ['commodities', 'Materias primas'], ['riesgo', 'Riesgo']];
        return `<div class="seg" data-seg="mercados" role="group" aria-label="Tipo de mercado">${segs.map(([k, l]) => `<button data-k="${k}" aria-pressed="${k === s}">${l}</button>`).join('')}</div>
    ${list(S.data.items.filter(i => i.group === s && i.kind === 'serie'))}`;
    };
    V.divisas = () => {
        const fx = S.data.items.filter(i => i.group === 'fx'), cc = Object.keys(S.data.fx_per_usd);
        return `<div class="split"><aside><h2 class="h">Conversor</h2><div class="card"><div class="conv-in"><input id="amt" inputmode="decimal" value="${S.conv.amt}" aria-label="Monto a convertir" autocomplete="off">
    <select id="from" aria-label="Moneda de origen">${cc.map(c => `<option ${c === S.conv.from ? 'selected' : ''}>${c}</option>`).join('')}</select></div>
    <div class="conv-out" id="cout" aria-live="polite">${convHTML()}</div></div></aside>
    <section><h2 class="h">Pares principales</h2>${list(fx)}
    <p class="note">Tipos de cambio de referencia del Banco Central Europeo (Frankfurter). El dólar en Chile viene de mindicador.cl.</p></section></div>`;
    };
    function convHTML() {
        const r = S.data.fx_per_usd, usd = (S.conv.amt || 0) / (r[S.conv.from] || 1);
        return Object.keys(r).filter(c => c !== S.conv.from).slice(0, 8).map(c => {
            const v = usd * r[c]; return `<div class="co"><small>${c}</small><b>${fmt(v, Math.abs(v) >= 1000 ? 0 : 2)}</b></div>`;
        }).join('');
    }
    V.cripto = () => {
        const cs = ['btc', 'eth', 'sol'].map(item).filter(Boolean), fg = S.data.feargreed;
        if (!cs.length && !fg) return '<div class="msg"><div><b>Sin datos de criptomonedas</b>Las fuentes no respondieron. Se reintentará automáticamente.</div></div>';
        return `<div class="cards">${cs.map(i => `<div class="card cc g-cripto" data-open="${i.id}" role="button" tabindex="0" aria-label="${esc(i.name)}: ${fmt(i.value, i.dec)}, ${chgTxt(i)}. Ver detalle"><div class="top2"><div><div class="nm">${esc(i.name)} · ${esc(i.sym)}</div>
    <div class="v" data-fid="${i.id}">${fmt(i.value, i.dec)}</div></div><div class="r"><span class="pill ${cls(i.chg1)}">${arrow(i.chg1)} ${chgTxt(i)}</span>
    <div class="nm">30d <span class="${cls(i.chg30)}">${sgn(i.chg30)}</span></div></div></div>
    <div class="ch">${spark(i.series.slice(-60), colOf(i.chg30), { h: 50 })}</div></div>`).join('')}
    ${fg ? `<div class="card fg-card"><div class="hd"><h2 class="h flush">Fear &amp; Greed · últimos 30 días</h2><span class="gl">${fg.value} · ${fgLabel(fg.value)}</span></div>
    <div class="ch">${spark(fg.history, '#a78bfa', { h: 50 })}</div></div>` : ''}</div>`;
    };
    V.chile = () => {
        const ser = S.data.items.filter(i => i.group === 'chile' && i.kind === 'serie'), st = S.data.items.filter(i => i.group === 'chile' && i.kind === 'stat');
        const f = S.data.fuentes.mindicador || {};
        const aviso = f.estado && f.estado !== 'ok' ? `<div class="card warn-card"><b>${f.estado === 'error' ? 'mindicador.cl no respondió' : 'mindicador.cl respondió parcialmente'}</b>
    <div>${esc(f.error || '')}</div><small>Se reintenta automáticamente y mientras tanto se conservan los últimos datos recibidos.</small></div>` : '';
        return `${aviso}${ser.length ? `<h2 class="h">Mercado</h2>${list(ser)}` : ''}
    ${st.length ? `<h2 class="h">Indicadores macro de Chile</h2><div class="stats">${st.map(i => `<div class="card st"><div class="n">${esc(i.name)}</div>
    <div class="v">${fmt(i.value, i.dec)}${i.unit === '%' ? ' <small>%</small>' : ''}</div><div class="d">${i.unit === '%' ? '' : esc(i.unit) + ' · '}dato ${fdate(i.fecha)}</div></div>`).join('')}</div>` : ''}
    ${!ser.length && !st.length && !aviso ? '<div class="msg"><div><b>Sin datos de Chile</b>Se reintentará automáticamente.</div></div>' : ''}`;
    };
    V.macro = () => {
        const m = S.data.macro; if (!m) return '<div class="msg"><div><b>Sin datos macro</b>El Banco Mundial no respondió. Se reintentará automáticamente.</div></div>';
        const s = S.seg.macro, segs = [['inflacion', 'Inflación'], ['pib', 'PIB'], ['desempleo', 'Desempleo']];
        const titles = { inflacion: 'Inflación anual (%)', pib: 'Crecimiento del PIB (%)', desempleo: 'Desempleo (% fuerza laboral)' };
        const card = k => {
            const rows = m[k] || [];
            const mn = Math.min(0, ...rows.map(r => r.valor)), mx = Math.max(0, ...rows.map(r => r.valor)), sp = (mx - mn) || 1, z = -mn / sp * 100;
            return `<section class="card macro-card ${k === s ? 'on' : ''}"><h2 class="h flush">${titles[k]}</h2>${rows.map(r => {
                const w = Math.abs(r.valor) / sp * 100, l = r.valor >= 0 ? z : z - w;
                return `<div class="bar-row ${r.iso === 'CHL' ? 'me' : ''}"><span class="c">${esc(r.pais)}</span><div class="t"><i class="${r.valor < 0 ? 'neg' : ''}" data-w="${w}" data-l="${l}"></i></div><b>${fmt(r.valor, 1)}</b></div>`;
            }).join('')}
      <p class="note">Último dato anual disponible (${[...new Set(rows.map(r => r.anio))].sort().join(' – ')}).</p></section>`;
        };
        return `<div class="seg macro-seg" data-seg="macro" role="group" aria-label="Indicador macroeconómico">${segs.map(([k, l]) => `<button data-k="${k}" aria-pressed="${k === s}">${l}</button>`).join('')}</div>
  <div class="macro-grid">${segs.map(([k]) => card(k)).join('')}</div><p class="note">Fuente: Banco Mundial. Datos anuales, sujetos a revisión.</p>`;
    };
    V.alertas = () => {
        const al = alertGroups(), c = n => al.filter(x => x.lvl === n).length;
        return `<div class="sum"><div><b class="down">${c('alta')}</b><small>Altas</small></div><div><b class="c-warn">${c('media')}</b><small>Medias</small></div><div><b class="c-info">${c('info')}</b><small>Info</small></div></div>
  ${al.length ? `<div class="list">${al.map(({ i, lvl }) => `<div class="card al" data-open="${i.id}" role="button" tabindex="0"><div class="lv ${lvl}"></div><div><div class="t1">${esc(i.name)} <span class="pill ${cls(i.chg1)}">${chgTxt(i)}</span></div>
    ${i.alerts.map(a => `<div class="t2">${alertText(a)}</div>`).join('')}</div><div class="sp">${sparkOf(i)}</div></div>`).join('')}</div>`
                : '<div class="msg"><div><b>Todo tranquilo</b>No hay alertas activas en este momento.</div></div>'}
  <p class="note">Reglas: variación diaria sobre el umbral de cada clase de activo, z-score ≥ 2 sobre los últimos 30 días y nuevos máximos o mínimos de 3 meses.</p>`;
    };

    /* ---------- Panel de detalle ---------- */
    function sheetHTML(i, anim) {
        const st = [['Var. 30 días', i.chg30u === 'pb' ? sgn(i.chg30, 0, ' pb') : sgn(i.chg30)], ['Mínimo 3M', fmt(i.min, i.dec)], ['Máximo 3M', fmt(i.max, i.dec)],
        ['Media 7d', fmt(i.sma7, i.dec)], ['Media 30d', fmt(i.sma30, i.dec)], ['z-score', sgn(i.z, 1, '')]];
        return `<div class="grab"></div><div class="sh-top"><div><div class="sh-n">${esc(i.name)}</div><div class="sh-s">${esc(i.sym || '')}${i.sym ? ' · ' : ''}${esc(i.unit)}</div></div>
    <button class="x" data-close aria-label="Cerrar detalle">✕</button></div>
    <div class="sh-px"><span class="big">${fmt(i.value, i.dec)}</span><span class="pill ${cls(i.chg1)}">${arrow(i.chg1)} ${chgTxt(i)}</span></div>
    <div class="rng" role="group" aria-label="Rango del gráfico">${[[30, '1M'], [90, '3M']].map(([r, l]) => `<button data-range="${r}" aria-pressed="${r === S.range}">${l}</button>`).join('')}</div>
    <div class="chartbox">${bigChart(i, S.range, anim)}<div class="tip" id="tip"></div></div>
    <div class="mstats">${st.map(([l, v]) => `<div class="ms"><small>${l}</small><b>${v}</b></div>`).join('')}</div>
    ${i.alerts.length ? `<div class="sal">${i.alerts.map(a => `<div class="${a.nivel}">${alertText(a)}</div>`).join('')}</div>` : ''}
    <div class="fuente">Fuente: ${esc(i.source)} · último dato ${fdate(i.dates[i.dates.length - 1])} · línea punteada = media móvil de 7 días</div>`;
    }
    function paintSheet(anim) {
        const i = item(S.sheet); if (!i) return closeSheet();
        const y = sheet.scrollTop, hadFocus = sheet.contains(document.activeElement);
        sheet.innerHTML = sheetHTML(i, anim && !reduceMotion);
        sheet.scrollTop = y;
        bindChart(i);
        if (hadFocus) $('.x', sheet)?.focus({ preventScroll: true });
    }
    function openSheet(id) {
        const i = item(id); if (!i || i.kind !== 'serie') return;
        S.opener = document.activeElement; S.sheet = id;
        paintSheet(true); sheet.scrollTop = 0;
        root.classList.add('sheet-open', 'lock'); app.inert = true;
        $('.x', sheet)?.focus({ preventScroll: true });
    }
    function closeSheet() {
        if (!S.sheet && !root.classList.contains('sheet-open')) return;
        S.sheet = null; root.classList.remove('sheet-open', 'lock'); app.inert = false;
        const o = S.opener; S.opener = null;
        if (o && document.contains(o) && o.focus) o.focus({ preventScroll: true });
    }

    /* ---------- Render ---------- */
    function paintNav() {
        const n = S.data ? alertGroups().filter(x => x.lvl !== 'info').length : 0;
        $('#nav').innerHTML = TABS.map(([k, l]) => `<a href="#/${k}" data-tab="${k}"${k === S.tab ? ' aria-current="page"' : ''}><svg viewBox="0 0 24 24" aria-hidden="true">${ICON[k]}</svg><span>${l}</span>${k === 'alertas' && n ? `<span class="cnt" aria-label="${n} alertas activas">${n}</span>` : ''}</a>`).join('');
    }
    function paintTicker() {
        if (!S.data) return;
        const ids = ['spx', 'ndx', 'ipsa', 'vix', 'gold', 'wti', 'copper', 'btc', 'eth', 'eurusd', 'usdclp', 'uf'];
        const html = ids.map(item).filter(Boolean).map(i => `<span class="tk"><b>${esc(i.name)}</b>${fmt(i.value, i.dec > 2 ? 2 : i.dec)}<i class="${cls(i.chg1)}">${arrow(i.chg1)} ${chgTxt(i)}</i></span>`).join('');
        $('#track').innerHTML = html + html;
    }
    function paintStatus() {
        let txt = 'Conectando…', c = 'warn';
        if (S.data) {
            const t = new Date(S.data.generated_at);
            txt = 'Actualizado ' + timeFmt.format(t);
            c = S.err ? 'off' : (Date.now() - t > 5 * 60000 ? 'warn' : '');
            if (S.err) txt += ' · sin conexión';
        } else if (S.err) { txt = 'Sin conexión'; c = 'off'; }
        $$('.js-dot').forEach(el => { el.classList.toggle('off', c === 'off'); el.classList.toggle('warn', c === 'warn'); });
        $$('.js-status').forEach(el => el.textContent = txt);
    }
    function stateHTML() {
        if (S.data) return null;
        if (S.err) return `<div class="msg"><div><b>No se pudieron cargar los indicadores</b>Revisa tu conexión e inténtalo de nuevo.<br><small>${esc(S.err)}</small><br><button class="btn" data-retry>Reintentar</button></div></div>`;
        return '<div class="sk"></div><div class="sk tall"></div><div class="sk"></div><div class="sk"></div><p class="note center">Cargando indicadores…</p>';
    }
    function render(enter = true) {
        const a = document.activeElement, y = window.scrollY;
        const keep = !enter && a && view.contains(a) ? (a.id ? '#' + a.id : a.dataset.open ? `[data-open="${a.dataset.open}"]` : null) : null;
        const sel = keep && a.id ? [a.selectionStart, a.selectionEnd] : null;
        view.innerHTML = stateHTML() || V[S.tab]();
        view.classList.toggle('stagger', enter && !reduceMotion);
        view.setAttribute('aria-busy', S.data ? 'false' : 'true');
        const label = TABS.find(t => t[0] === S.tab)[1];
        $('#pageTitle').textContent = label; document.title = `${label} · Pulso Global`;
        paintNav();
        if (S.data) afterRender(enter);
        if (keep) { const el = $(keep, view); if (el) { el.focus({ preventScroll: true }); try { if (sel && sel[0] != null) el.setSelectionRange(...sel); } catch { } } }
        window.scrollTo(0, enter ? 0 : y);
    }
    function afterRender(enter) {
        $$('.bar-row i', view).forEach(el => el.style.left = el.dataset.l + '%');
        const settle = () => {
            $$('.bar-row i', view).forEach(el => el.style.width = el.dataset.w + '%');
            $$('.needle', view).forEach(el => el.style.transform = `rotate(${el.dataset.ang}deg)`);
        };
        if (enter) {
            if (!reduceMotion) $$('.cu', view).forEach(el => countUp(el, +el.dataset.v, +el.dataset.d));
            requestAnimationFrame(() => requestAnimationFrame(settle));
        } else {
            settle();
            $$('[data-fid]', view).forEach(el => {
                const id = el.dataset.fid, p = S.prev[id], c = item(id);
                if (p != null && c && p !== c.value) { el.classList.remove('flash-up', 'flash-down'); void el.offsetWidth; el.classList.add(c.value > p ? 'flash-up' : 'flash-down'); }
            });
        }
    }
    function countUp(el, to, dec, ms = 1000) {
        const t0 = performance.now(), from = to * .94;
        (function f(t) { const p = Math.min(1, (t - t0) / ms), e = 1 - Math.pow(1 - p, 3); el.textContent = fmt(from + (to - from) * e, dec); if (p < 1) requestAnimationFrame(f); })(t0);
    }

    /* ---------- Rutas (#/seccion) ---------- */
    const tabFromHash = () => { const h = location.hash.replace(/^#\/?/, ''); return TAB_IDS.includes(h) ? h : 'resumen'; };
    function applyRoute() { S.tab = tabFromHash(); closeSheet(); render(true); }
    addEventListener('hashchange', applyRoute);

    /* ---------- Datos ---------- */
    async function load() {
        if (S.loading) return;
        S.loading = true;
        const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), FETCH_TIMEOUT_MS);
        try {
            const r = await fetch('/api/snapshot', { signal: ctl.signal, headers: { Accept: 'application/json' } });
            if (!r.ok) throw new Error('El servidor respondió ' + r.status);
            const d = await r.json();
            S.prev = S.data ? Object.fromEntries(S.data.items.map(i => [i.id, i.value])) : {};
            const first = !S.data;
            S.data = d; S.byId = Object.fromEntries(d.items.map(i => [i.id, i])); S.err = null; S.lastOk = Date.now();
            paintTicker();
            if (first) render(true); else { render(false); S.prev = {}; if (S.sheet) paintSheet(false); }
        } catch (e) {
            S.err = e.name === 'AbortError' ? 'La solicitud tardó demasiado' : String(e.message || e);
            if (!S.data) render(true);
        } finally {
            clearTimeout(timer); S.loading = false; paintStatus();
        }
    }

    /* ---------- Eventos ---------- */
    document.addEventListener('click', e => {
        const t = e.target.closest('[data-tab],[data-open],[data-seg] button,[data-close],[data-range],[data-retry],#sbg'); if (!t) return;
        if (t.matches('#sbg,[data-close]')) return closeSheet();
        if (t.dataset.retry !== undefined) { S.err = null; render(true); return load(); }
        if (t.dataset.tab) { if (t.dataset.tab === S.tab) window.scrollTo({ top: 0 }); return; }
        if (t.dataset.open) return openSheet(t.dataset.open);
        if (t.dataset.range) { S.range = +t.dataset.range; return paintSheet(true); }
        const seg = t.closest('[data-seg]');
        if (seg) { S.seg[seg.dataset.seg] = t.dataset.k; render(false); }
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') closeSheet();
        const a = document.activeElement;
        if ((e.key === 'Enter' || e.key === ' ') && a && a.dataset.open) { e.preventDefault(); openSheet(a.dataset.open); }
    });
    view.addEventListener('input', e => { if (e.target.id === 'amt') { S.conv.amt = parseFloat(e.target.value.replace(',', '.')) || 0; $('#cout').innerHTML = convHTML(); } });
    view.addEventListener('change', e => { if (e.target.id === 'from') { S.conv.from = e.target.value; $('#cout').innerHTML = convHTML(); } });

    /* ---------- Arranque ---------- */
    S.tab = tabFromHash();
    render(true); paintStatus(); load();
    setInterval(() => { if (!document.hidden) load(); }, REFRESH_MS);
    setInterval(paintStatus, 30000);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && Date.now() - S.lastOk > REFRESH_MS) load(); });
})();