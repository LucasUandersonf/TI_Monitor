#!/usr/bin/env node
/**
 * Renderiza um ARTIFACT de cenas (o HTML que vem da conversa de artifacts) quadro a quadro.
 * O visual é 100% o do artifact; por cima entram só as camadas de edição:
 *
 *   - duração de cada cena ajustada à narração e relógio das animações sincronizado com a fala
 *   - câmera extra: punch-in nas palavras fortes, tremor nos impactos
 *   - motion blur por supersampling, só nos quadros em que algo se move rápido
 *   - boca sincronizada (Rhubarb ou envelope da voz)
 *   - Lottie: animações prontas por cima da cena (lottie-web, controlado quadro a quadro)
 *   - camadas pedidas pelo artifact: mapa (Natural Earth), arte (FLUX/vtracer ou imagem sua),
 *     desenho animado (AnimatedDrawings), encaixadas nos marcadores data-mapa / data-arte / data-desenho
 *
 *   node render_artifact.mjs --artifact a.html --extrair > cenas.json
 *   node render_artifact.mjs --artifact a.html --plano plano.json --pasta clips/ [--de 0 --ate 10] [--blur 3]
 *
 * Contrato mínimo do artifact (o "Motor de Cenas" já cumpre sem mudar nada):
 *   const SCENES=[{narration, dur, render(), tick?(t,root), hot?}]  ·  function go(i)  ·  let t  ·  palco em #stage
 */
import { chromium } from 'playwright';
import { spawn } from 'node:child_process';
import { readFileSync, mkdirSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const A = {};
process.argv.slice(2).forEach((a, i, arr) => {
  if (a.startsWith('--')) A[a.slice(2)] = arr[i + 1] && !arr[i + 1].startsWith('--') ? arr[i + 1] : true;
});
const W = 1920, H = 1080;
const FPS = Number(A.fps || 30);
const BLUR = Math.max(1, Number(A.blur || 1));          // subquadros por quadro em movimento
const PALCO = A.palco || '#stage';
const OCULTAR = (A.ocultar || '#subs,#chip').split(',');

const browser = await chromium.launch({ args: ['--font-render-hinting=none', '--allow-file-access-from-files'] });
// --escala 1.333 = 1440p, 2 = 4K: o artifact é vetorial, então fica nítido em qualquer resolução
const ESCALA = Math.max(1, Number(A.escala || 1));
const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: ESCALA });
page.on('pageerror', e => console.error('[artifact]', e.message));

// 1) congela o relógio do artifact: nós controlamos o tempo
await page.addInitScript(() => { window.__RENDER = true; window.requestAnimationFrame = () => 0; });
await page.goto(pathToFileURL(resolve(A.artifact)).href, { waitUntil: 'networkidle' });
await page.evaluate(() => document.fonts.ready);
try { await page.addScriptTag({ path: require.resolve('lottie-web/build/player/lottie.min.js') }); } catch (e) { /* sem lottie-web */ }

// 2) palco ocupa a tela inteira; o resto da página some
await page.addStyleTag({ content: `
  html,body{margin:0!important;overflow:hidden!important;background:#000!important}
  ${PALCO}{position:fixed!important;inset:0!important;width:${W}px!important;height:${H}px!important;max-width:none!important;
    aspect-ratio:auto!important;border-radius:0!important;box-shadow:none!important;z-index:2147483646!important;margin:0!important}
  ${OCULTAR.join(',')}{display:none!important}
  ${PALCO} > svg{transform-origin:50% 50%;will-change:transform}
  .__lottie{position:absolute;pointer-events:none;z-index:5;transform:translate(-50%,-50%)}` });

// 3) adaptador
await page.evaluate((palco) => {
  const temMotor = !!window.MOTOR_RENDER;
  // aceita os dois formatos do Motor de Cenas: SCENES (antigo) ou SECTIONS achatado em SC (novo)
  const lista = () => temMotor ? window.MOTOR_RENDER.cenas()
    : (typeof SCENES !== 'undefined' ? SCENES : (typeof SC !== 'undefined' ? SC : window.CENAS));
  const parteDe = (s) => {
    if (s.capitulo ?? s.chapter ?? s.parte) return s.capitulo ?? s.chapter ?? s.parte;
    try { if (typeof SECTIONS !== 'undefined' && s.sec != null) return SECTIONS[s.sec].name; } catch (e) {}
    return null;
  };
  const raiz = () => document.querySelector(palco);
  const svg = () => raiz().querySelector('svg');
  const NS = 'http://www.w3.org/2000/svg';
  const BOCA_PENSADOR = 'M-38,-346 Q0,-330 38,-346';
  const BOCAS = window.BOCAS || {
    X: BOCA_PENSADOR, A: 'M-30,-344 L30,-344', B: 'M-34,-350 Q0,-332 34,-350 Q0,-340 -34,-350Z',
    C: 'M-36,-354 Q0,-322 36,-354 Q0,-340 -36,-354Z', D: 'M-40,-358 Q0,-306 40,-358 Q0,-344 -40,-358Z',
    E: 'M-24,-356 Q0,-316 24,-356 Q0,-350 -24,-356Z', F: 'M-14,-352 Q0,-326 14,-352 Q0,-346 -14,-352Z',
    G: 'M-34,-350 Q0,-334 34,-350 L30,-342 Q0,-338 -30,-342Z', H: 'M-36,-354 Q0,-318 36,-354 Q0,-342 -36,-354Z' };
  // animações que contam como "movimento rápido" (recebem motion blur enquanto acontecem)
  const RAPIDAS = /^(pop|slideL|slideR|grow|toss|rise|zoom|shake|bounce|spin|drop|fall|swing|enter|in)/i;
  let atual = -1, cenaPlano = null, sequencias = [], lotties = [];

  const caixa = (el) => {
    const n = (k) => parseFloat(el.getAttribute(k));
    if (!isNaN(n('width')) && !isNaN(n('height'))) return { x: n('x') || 0, y: n('y') || 0, w: n('width'), h: n('height') };
    const b = el.getBBox(); return { x: b.x, y: b.y, w: b.width, h: b.height };
  };
  const encaixar = (camada) => {
    const s = svg();
    const alvo = camada.alvo === 'fundo' ? null : s.querySelector(camada.alvo);
    const cx = alvo ? caixa(alvo) : { x: 0, y: 0, w: 1920, h: 1080 };
    const g = document.createElementNS(NS, 'g');
    if (alvo) { // herda as animações e o recorte do marcador
      if (alvo.getAttribute('class')) g.setAttribute('class', alvo.getAttribute('class'));
      if (alvo.getAttribute('style')) g.setAttribute('style', alvo.getAttribute('style'));
      if (alvo.getAttribute('transform')) g.setAttribute('transform', alvo.getAttribute('transform'));
      if (alvo.getAttribute('clip-path')) g.setAttribute('clip-path', alvo.getAttribute('clip-path'));
    }
    if (camada.tipo === 'svg') {
      g.innerHTML = `<svg x="${cx.x}" y="${cx.y}" width="${cx.w}" height="${cx.h}" viewBox="${camada.viewBox || '0 0 1920 1080'}" preserveAspectRatio="xMidYMid slice" overflow="hidden">${camada.svg}</svg>`;
    } else {
      const img = document.createElementNS(NS, 'image');
      ['x', 'y'].forEach(k => img.setAttribute(k, cx[k]));
      img.setAttribute('width', cx.w); img.setAttribute('height', cx.h);
      img.setAttribute('preserveAspectRatio', camada.ajuste || 'xMidYMid slice');
      img.setAttribute('href', camada.href || (camada.quadros || [])[0] || '');
      g.appendChild(img);
      if (camada.tipo === 'sequencia') sequencias.push({ img, quadros: camada.quadros, fps: camada.fps || 24 });
    }
    if (alvo) { alvo.parentNode.insertBefore(g, alvo.nextSibling); alvo.style.visibility = 'hidden'; }
    else { const ref = s.querySelector(':scope > rect'); s.insertBefore(g, ref ? ref.nextSibling : s.firstChild); }
  };

  // "entradas": animações finitas e curtas (não as de ambiente, que duram a cena toda), agrupadas por elemento
  let entradasAtuais = [];
  const entradas = (D) => {
    const m = new Map();
    for (const a of raiz().getAnimations({ subtree: true })) {
      const tm = a.effect.getTiming(); const el = a.effect.target;
      if (!el || tm.iterations === Infinity || a.effect.pseudoElement) continue;
      const d = (tm.duration || 0) / 1000;
      if (!(d > 0) || d >= Math.max(1.6, 0.6 * D)) continue;
      if (!m.has(el)) m.set(el, { el, anims: [], atraso: Infinity, duracao: 0, nome: a.animationName || '' });
      const e = m.get(el); e.anims.push({ a, delay: tm.delay || 0 });
      if ((tm.delay || 0) / 1000 < e.atraso) { e.atraso = (tm.delay || 0) / 1000; e.nome = a.animationName || e.nome; e.duracao = d; }
    }
    const lista = [...m.values()].sort((x, y) => x.atraso - y.atraso);
    lista.forEach((e, k) => {
      e.k = k;
      const ancora = e.el.closest?.('[data-palavra]');
      e.palavra = ancora ? ancora.getAttribute('data-palavra') : null;
      e.grupo = ancora ? lista.findIndex(o => o.el === ancora || ancora.contains(o.el)) : k;
      e.texto = (e.el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
    });
    return lista;
  };
  window.__FAB = {
    cenas() {
      return lista().map((s, i) => ({
        indice: i, narracao: s.narration ?? s.narracao ?? s.n ?? s.texto ?? '', dur: s.dur ?? s.duracao ?? 7,
        destaques: s.hot ?? s.destaques ?? [], molde: s.mold ?? s.molde ?? s.m ?? null, layout: s.layout ?? null,
        capitulo: parteDe(s), sfx: s.sfx ?? s.efeito_sonoro ?? null, camera: s.camera ?? null,
        mapa: s.mapa ?? null, arte: s.arte ?? null, desenho: s.desenho ?? null, lottie: s.lottie ?? null }));
    },
    marcadores() {
      const out = [];
      svg().querySelectorAll('[data-mapa],[data-arte],[data-arte-arquivo],[data-desenho]').forEach((el, k) => {
        const d = { ...el.dataset };
        const tipo = d.mapa !== undefined ? 'mapa' : d.desenho !== undefined ? 'desenho' : 'arte';
        el.dataset.fabId = String(k);
        out.push({ tipo, seletor: `[data-fab-id="${k}"]`, dados: d, caixa: caixa(el) });
      });
      return out;
    },
    abrir(i, dur, plano) {
      const s = lista()[i];
      if (temMotor) window.MOTOR_RENDER.abrir(i, dur); else { s.dur = dur; go(i); }
      atual = i; cenaPlano = plano || null; sequencias = []; lotties.forEach(l => { l.anim.destroy(); l.div.remove(); }); lotties = [];
      raiz().querySelectorAll('path').forEach(p => { if (p.getAttribute('d') === BOCA_PENSADOR) { p.dataset.boca = '1'; p.setAttribute('fill', p.getAttribute('stroke')); } });
      // marca os marcadores para as camadas acharem (mesma numeração do extrair)
      svg().querySelectorAll('[data-mapa],[data-arte],[data-arte-arquivo],[data-desenho]').forEach((el, k) => el.dataset.fabId = String(k));
      for (const c of (plano?.camadas || [])) { try { encaixar(c); } catch (e) { console.error('camada', e.message); } }
      for (const l of (plano?.lottie || [])) {
        if (!window.lottie) break;
        const div = document.createElement('div'); div.className = '__lottie';
        div.style.width = (l.largura || 360) + 'px'; div.style.height = (l.largura || 360) + 'px'; div.style.opacity = 0;
        raiz().appendChild(div);
        const anim = window.lottie.loadAnimation({ container: div, renderer: 'svg', loop: false, autoplay: false, animationData: l.dados });
        lotties.push({ ...l, div, anim, posicionado: false });
      }
      entradasAtuais = entradas(dur);
      // o plano diz em que instante (tempo do artifact) cada elemento entra: casa com a palavra falada
      for (const q of (plano?.entradas || [])) {
        const e = entradasAtuais[q.k]; if (!e) continue;
        const delta = q.em * 1000 - e.atraso * 1000;
        for (const { a, delay } of e.anims) { try { a.effect.updateTiming({ delay: Math.max(0, delay + delta) }); } catch (err) {} }
      }
      if (!plano) window.__FAB.ultimasEntradas = entradasAtuais.map(e => ({ k: e.k, atraso: +e.atraso.toFixed(3), duracao: +e.duracao.toFixed(3),
        nome: e.nome, texto: e.texto, palavra: e.palavra, grupo: e.grupo }));
      return raiz().getAnimations({ subtree: true }).map(a => {
        const tm = a.effect.getTiming(); const alvo = a.effect.target;
        return { nome: a.animationName || '', atraso: (tm.delay || 0) / 1000, duracao: (tm.duration || 0) / 1000,
          infinita: tm.iterations === Infinity, classe: alvo?.getAttribute?.('class') || '' };
      }).filter(a => !a.infinita);
    },
    seek(i, tReal, mov, boca, plano) {
      if (i !== atual || plano) this.abrir(i, mov.dur, plano);
      const tt = Math.max(0, tReal) * (mov.relogio || 1);
      const ms = tt * 1000;
      let rapido = false, ultimo = null, ultimoIni = -1;
      for (const a of raiz().getAnimations({ subtree: true })) {
        a.pause(); a.currentTime = ms;
        const tm = a.effect.getTiming(), ini = (tm.delay || 0), fim = ini + (tm.duration || 0);
        if (tm.iterations !== Infinity && RAPIDAS.test(a.animationName || '') && ms >= ini && ms <= fim) rapido = true;
        if (tm.iterations !== Infinity && ms >= ini && ini > ultimoIni && a.effect.target?.getBoundingClientRect) { ultimo = a.effect.target; ultimoIni = ini; }
      }
      if (temMotor) window.MOTOR_RENDER.seek(i, tt);
      else {
        try { t = tt; } catch (e) {}
        const s = lista()[i];
        // o player do artifact chama as animações calculadas em update(); o formato antigo usa s.tick(t, svg)
        if (typeof update === 'function') { try { update(); } catch (e) {} }
        else if (s.tick) s.tick(tt, svg());
      }
      svg().style.transform = `translate(${mov.x.toFixed(2)}px,${mov.y.toFixed(2)}px) scale(${mov.s.toFixed(4)})`;
      if (boca) raiz().querySelectorAll('[data-boca]').forEach(p => p.setAttribute('d', BOCAS[boca] || BOCAS.X));
      for (const sq of sequencias) sq.img.setAttribute('href', sq.quadros[Math.floor(tt * sq.fps) % sq.quadros.length]);
      for (const l of lotties) {
        const d = tReal - l.em;
        if (d < 0) { l.div.style.opacity = 0; continue; }
        if (!l.posicionado) { // "alvo: ultimo" = em cima do elemento que acabou de entrar
          let x = l.x ?? 960, y = l.y ?? 540;
          if (l.alvo === 'ultimo' && ultimo) { const r = ultimo.getBoundingClientRect(); x = r.left + r.width / 2; y = r.top + r.height / 2; }
          l.div.style.left = x + 'px'; l.div.style.top = y + 'px'; l.posicionado = true;
        }
        const total = l.anim.getDuration(false) * 1000;
        l.div.style.opacity = d * 1000 < total ? 1 : 0;
        l.anim.goToAndStop(Math.min(d * 1000, total - 1), false);
      }
      return rapido || (mov.s > 1.0005 && mov.ds > 0.0004) || Math.abs(mov.x) > 0.5;
    }
  };
}, PALCO);

if (A.extrair) {
  const cenas = await page.evaluate(() => window.__FAB.cenas());
  for (const c of cenas) {
    c.animacoes = await page.evaluate(([i, d]) => window.__FAB.abrir(i, d, null), [c.indice, c.dur]);
    c.entradas = await page.evaluate(() => window.__FAB.ultimasEntradas || []);
    c.tem_boca = await page.evaluate((p) => !!document.querySelector(p + ' [data-boca]'), PALCO);
    c.marcadores = await page.evaluate(() => window.__FAB.marcadores());
  }
  const meta = await page.evaluate(() => ({ titulo_documento: document.title, ...(window.META || {}) }));
  process.stdout.write(JSON.stringify({ meta, cenas }, null, 1));
  await browser.close();
  process.exit(0);
}

// ---------------------------------------------------------------- render
const plano = JSON.parse(readFileSync(resolve(A.plano), 'utf8'));
const pasta = resolve(A.pasta || 'clips');
mkdirSync(pasta, { recursive: true });
const de = Number(A.de || 0), ate = Math.min(Number(A.ate ?? plano.cenas.length), plano.cenas.length);

/* câmera: punch-in (zoom rápido que volta devagar) e tremor (decai em ~0,35 s) */
function escala(cena, tt) {
  let s = 1, x = 0, y = 0;
  const dv = cena.deriva;
  if (dv) { // zoom/pan lento do começo ao fim da cena (Ken Burns), suave nas pontas
    const p = Math.min(1, Math.max(0, (tt + (cena.cabeca || 0)) / (cena.dur + (cena.cabeca || 0))));
    const k = p * p * (3 - 2 * p) * 0.6 + p * 0.4;
    s *= dv.de + (dv.ate - dv.de) * k; x += (dv.dx || 0) * (k - 0.5); y += (dv.dy || 0) * (k - 0.5);
  }
  for (const m of cena.movimento || []) {
    const d = tt - m.em;
    if (m.tipo === 'punch' && d > -0.12) {
      const sobe = Math.min(1, (d + 0.12) / 0.12), desce = d > 0.5 ? Math.max(0, 1 - (d - 0.5) / 0.7) : 1;
      const env = sobe * desce; const k = env * env * (3 - 2 * env);
      s *= 1 + ((m.forca || 1.045) - 1) * k;
    }
    if (m.tipo === 'tremor' && d >= 0 && d < (m.dur || 0.35)) {
      const amp = (m.forca || 9) * (1 - d / (m.dur || 0.35));
      x += Math.sin(d * 97) * amp; y += Math.cos(d * 83) * amp * 0.7;
    }
  }
  return { s, x, y };
}
function movimento(cena, tt) {
  const a = escala(cena, tt), b = escala(cena, tt + 1 / FPS);
  return { ...a, ds: Math.abs(b.s - a.s), dur: cena.dur_artifact ?? cena.dur, relogio: cena.relogio || 1 };
}
const bocaEm = (cena, tt) => { const v = (cena.boca || []).find(v => tt >= v[0] && tt < v[1]); return v ? v[2] : (cena.boca ? 'X' : null); };

for (let i = de; i < ate; i++) {
  const cena = plano.cenas[i];
  const cabeca = cena.cabeca || 0;                          // a imagem entra antes, durante a transição
  const total = cabeca + cena.dur - (cena.corte || 0) + (cena.cauda || 0);
  const nq = Math.round(total * FPS);
  const saida = join(pasta, `cena_${String(cena.global ?? i).padStart(3, '0')}.mp4`);
  // com motion blur: entram BLUR subquadros por quadro e o FFmpeg tira a média (tmix) e fica com 1 de cada BLUR
  const vf = BLUR > 1 ? ['-vf', `tmix=frames=${BLUR},select='eq(mod(n\\,${BLUR})\\,${BLUR - 1})',setpts=N/(${FPS}*TB)`] : [];
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS * BLUR), '-c:v', 'mjpeg', '-i', '-',
    ...vf, '-c:v', 'libx264', '-preset', A.preset || 'medium', '-crf', String(A.crf || 17), '-pix_fmt', 'yuv420p', '-r', String(FPS), saida],
    { stdio: ['pipe', 'inherit', 'inherit'] });
  const escrever = b => new Promise(ok => ff.stdin.write(b) ? ok() : ff.stdin.once('drain', ok));
  const foto = () => page.screenshot({ type: 'jpeg', quality: 93 });
  const seek = (tReal) => {
    const tt = Math.min(tReal, cena.dur - 1 / FPS);          // antes do início e na cauda, segura o quadro
    const pl = planoEnviado ? null : cena;                     // camadas e lottie só vão no primeiro quadro
    planoEnviado = true;
    return page.evaluate(([i, tt, mov, boca, pl]) => window.__FAB.seek(i, tt, mov, boca, pl),
      [cena.indice ?? i, tt, movimento(cena, tt), bocaEm(cena, tt), pl]);
  };
  let borrados = 0, planoEnviado = false;
  for (let q = 0; q < nq; q++) {
    const t0 = q / FPS - cabeca;
    const mexe = await seek(t0);
    if (BLUR > 1 && mexe && t0 >= 0 && t0 < cena.dur) {
      // obturador de 180°: subquadros espalhados por meio quadro, centrados no instante do quadro
      for (let k = 0; k < BLUR; k++) {
        await seek(Math.max(0, t0 + ((k + 0.5) / BLUR - 0.5) * 0.5 / FPS));
        await escrever(await foto());
      }
      borrados++;
    } else {
      const b = await foto();
      for (let k = 0; k < BLUR; k++) await escrever(b);
    }
  }
  ff.stdin.end();
  await new Promise((ok, erro) => ff.on('close', c => c === 0 ? ok() : erro(new Error('ffmpeg ' + c))));
  process.stdout.write(JSON.stringify({ evento: 'cena', indice: i, saida, quadros: nq, com_blur: borrados }) + '\n');
}
await browser.close();
