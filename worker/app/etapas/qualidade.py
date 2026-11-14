"""
Conferência automática (o "editor revisor"):

  ANTES de gastar crédito  conferir_creditos: quantos caracteres faltam narrar (o que já está no cache não conta)
                           e se o saldo da ElevenLabs dá. Se não der, para na hora, sem renderizar nada.
  DEPOIS do vídeo pronto   conferir: lê o plano e o MP4 final e aponta tudo que um editor apontaria:
     - buraco de áudio entre falas, silêncio total, volume fora do padrão do YouTube (-14 LUFS), pico estourando
     - imagem congelada, tela preta, vídeo e áudio com durações diferentes
     - cena longa demais (perde ritmo) ou curta demais, animação do HTML longa demais para a fala
     - palavra pedida no data-palavra / no JSON do diretor que não está na narração
  e grava na pasta do vídeo:
     relatorio_qualidade.txt   nota de 0 a 10 + cada problema com a cena e o que fazer
     tempos_das_cenas.csv      cena, início, duração (o tempo real de cada imagem) e a narração
"""
from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

from . import narracao, texto_fala

LUFS_ALVO = -14.0


def _mmss(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def conferir_creditos(cenas: list[dict], avisos: list[str], motor: str | None = None) -> dict:
    motor = motor or narracao.motor_atual()
    if motor != "elevenlabs":
        return {"motor": motor}
    faltam = [c for c in cenas if c.get("narracao") and not narracao.em_cache(c["narracao"])]
    caracteres = sum(len(texto_fala.preparar(c["narracao"])) for c in faltam)
    precisa = round(caracteres * narracao.custo_por_caractere())
    saldo = narracao.saldo_elevenlabs()
    info = {"motor": motor, "estimado": precisa, "cenas_a_narrar": len(faltam), "saldo_antes": saldo and saldo["restante"]}
    if saldo is None:
        avisos.append("não consegui ler o saldo da ElevenLabs (a chave precisa da permissão 'User: read'); seguindo assim mesmo")
    elif precisa > saldo["restante"]:
        raise RuntimeError(f"ElevenLabs: este vídeo precisa de ~{precisa} créditos e restam {saldo['restante']}. "
                           f"Nada foi gasto. Recarregue os créditos ou use ELEVENLABS_MODELO=eleven_flash_v2_5 (metade do custo).")
    return info


def _analisar_midia(arq: Path) -> dict:
    """Uma passada do FFmpeg: tela preta, imagem congelada, silêncio e loudness."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(arq),
                        "-vf", "blackdetect=d=1.0:pix_th=0.02:pic_th=0.999,freezedetect=n=-60dB:d=2.5",
                        "-af", "silencedetect=n=-50dB:d=1.0,ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    log = r.stderr
    num = lambda pad: [float(x) for x in re.findall(pad, log)]
    pretos = list(zip(num(r"black_start:([\d.]+)"), num(r"black_duration:([\d.]+)")))
    congelados = list(zip(num(r"freeze_start: ([\d.]+)"), num(r"freeze_duration: ([\d.]+)")))
    silencios = list(zip(num(r"silence_start: ([\d.]+)"), num(r"silence_duration: ([\d.]+)")))
    resumo = log[log.rfind("Summary:"):] if "Summary:" in log else ""
    I = re.search(r"I:\s+(-?[\d.]+) LUFS", resumo)
    tp = re.search(r"Peak:\s+(-?[\d.]+) dBFS", resumo)
    dur = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,duration", "-of", "csv=p=0", str(arq)],
                         capture_output=True, text=True).stdout
    duracoes = {l.split(",")[0]: float(l.split(",")[1]) for l in dur.splitlines() if "," in l and l.split(",")[1] not in ("", "N/A")}
    return {"pretos": pretos, "congelados": congelados, "silencios": silencios,
            "lufs": float(I.group(1)) if I else None, "pico": float(tp.group(1)) if tp else None, "duracoes": duracoes}


def conferir(pl: dict, cenas: list[dict], final: Path, pasta: Path, titulo: str, creditos: dict, avisos: list[str]) -> dict:
    problemas: list[dict] = []

    def add(gravidade: str, onde: str, o_que: str, fazer: str):
        problemas.append({"gravidade": gravidade, "onde": onde, "problema": o_que, "como_resolver": fazer})

    def cena_em(t: float) -> str:
        for c in pl["cenas"]:
            if c["inicio"] <= t < c["inicio"] + c["dur"]:
                return f"cena {c['global'] + 1} ({_mmss(t)})"
        return _mmss(t)

    # ---------- plano
    pc = pl["cenas"]
    for k, (c, orig) in enumerate(zip(pc, cenas)):
        n = k + 1
        fala = c["fala"]["duracao"]
        if fala > 13:
            add("sugestao", f"cena {n}", f"cena longa ({fala:.1f} s de fala numa imagem só): o ritmo cai",
                "na conversa do roteiro, divida a frase em 2 cenas (uma ideia por cena)")
        if orig.get("dur", 0) / max(c["dur"], 0.1) > 2.4 and orig.get("entradas"):
            add("aviso", f"cena {n}", f"o HTML tinha {orig['dur']:.1f} s de animação para {c['dur']:.1f} s de fala; "
                "as animações foram aceleradas ao máximo (2x)", "na conversa do HTML, menos elementos nesta cena")
        for e in c.get("entradas_info") or []:
            if e["origem"] == "palavra_nao_achada":
                add("aviso", f"cena {n}", f"data-palavra/diretor pede \"{e.get('pedida')}\", que não está na narração "
                    f"(elemento \"{e.get('texto') or e['k'] + 1}\")", "corrija a palavra para uma que aparece na fala desta cena")
        for el in orig.get("_diretor_nao_achado") or []:
            add("aviso", f"cena {n}", f"o JSON do diretor cita o elemento \"{el}\", que não existe na cena",
                "use o texto visível do elemento ou o número da ordem em que ele aparece")
        if k + 1 < len(pc):
            fim_fala = c["inicio"] + c["fala"]["em"] + fala
            prox = pc[k + 1]["inicio"] + pc[k + 1]["fala"]["em"]
            if prox - fim_fala > 0.8:
                add("erro", f"cena {n} → {n + 1}", f"buraco de {prox - fim_fala:.2f} s sem fala", "verifique a narração da cena")

    # ---------- arquivo final
    m = _analisar_midia(final)
    for ini, d in m["silencios"]:
        add("erro", cena_em(ini), f"{d:.1f} s de silêncio total (nem voz, nem trilha)", "confira a trilha e a narração desse trecho")
    for ini, d in m["congelados"]:
        add("aviso", cena_em(ini), f"imagem parada por {d:.1f} s", "adicione um elemento com data-palavra nesse trecho")
    for ini, d in m["pretos"]:
        add("aviso", cena_em(ini), f"tela totalmente preta por {d:.1f} s", "confira se a cena do HTML desenha algo")
    if m["lufs"] is not None and abs(m["lufs"] - LUFS_ALVO) > 1.0:
        add("aviso", "áudio", f"volume integrado {m['lufs']:.1f} LUFS (padrão do YouTube: {LUFS_ALVO})", "a mixagem corrige na próxima edição")
    if m["pico"] is not None and m["pico"] > -0.5:
        add("aviso", "áudio", f"pico em {m['pico']:.1f} dBFS (risco de distorção)", "a mixagem corrige na próxima edição")
    dv, da = m["duracoes"].get("video"), m["duracoes"].get("audio")
    if dv and da and abs(dv - da) > 0.15:
        add("erro", "arquivo", f"vídeo ({dv:.2f} s) e áudio ({da:.2f} s) com durações diferentes", "rode de novo")

    peso = {"erro": 2.0, "aviso": 0.5, "sugestao": 0.1}
    nota = round(max(0.0, 10 - sum(peso[p["gravidade"]] for p in problemas)), 1)

    # ---------- arquivos
    pasta.mkdir(parents=True, exist_ok=True)
    tempos = pasta / "tempos_das_cenas.csv"
    with tempos.open("w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: abre certo no Excel
        w = csv.writer(f, delimiter=";")
        w.writerow(["cena", "parte", "inicio", "duracao_s", "palavras", "elementos_na_palavra", "narracao"])
        for k, (c, orig) in enumerate(zip(pc, cenas)):
            ents = c.get("entradas_info") or []
            anc = sum(1 for e in ents if e["origem"] in ("diretor", "data-palavra", "texto"))
            w.writerow([k + 1, orig.get("capitulo") or "", _mmss(c["inicio"]), f"{c['dur']:.2f}".replace(".", ","),
                        len(orig.get("narracao", "").split()), f"{anc}/{len(ents)}", orig.get("narracao", "")])
    rel = pasta / "relatorio_qualidade.txt"
    linhas = [f"RELATÓRIO DE QUALIDADE · {titulo}", "",
              f"Nota: {nota}/10", f"Duração: {_mmss(pl['duracao'])} · {len(pc)} cenas · "
              f"média {pl['duracao'] / max(1, len(pc)):.1f} s por cena",
              f"Áudio: {m['lufs'] if m['lufs'] is not None else '?'} LUFS (alvo {LUFS_ALVO}) · pico {m['pico'] if m['pico'] is not None else '?'} dBFS"]
    if creditos.get("motor") == "elevenlabs":
        linhas.append(f"ElevenLabs: {creditos.get('gastos', 0)} créditos gastos · {creditos.get('cenas_do_cache', 0)} cenas "
                      f"reaproveitadas do cache · saldo antes: {creditos.get('saldo_antes', '?')}")
    else:
        linhas.append(f"Voz: {creditos.get('motor')}")
    linhas.append("")
    if not problemas:
        linhas.append("Nenhum problema encontrado.")
    for p in sorted(problemas, key=lambda p: ["erro", "aviso", "sugestao"].index(p["gravidade"])):
        linhas.append(f"[{p['gravidade'].upper()}] {p['onde']}: {p['problema']}")
        linhas.append(f"    → {p['como_resolver']}")
    if avisos:
        linhas += ["", "Avisos da edição:"] + [f"  - {a}" for a in avisos]
    rel.write_text("\n".join(linhas) + "\n", encoding="utf-8")
    return {"nota": nota, "problemas": problemas, "arquivos": {"relatorio": str(rel), "tempos": str(tempos)}, "midia": m}
