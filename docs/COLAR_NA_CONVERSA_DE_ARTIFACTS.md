# Instruções para a conversa que cria os artifacts

> Cole o bloco abaixo nas instruções do projeto (ou no começo da conversa) onde você monta os artifacts.
> Ele não muda o seu estilo visual: só garante que todo artifact saia num formato que a edição automática consegue ler.

---

Você cria artifacts de cenas animadas no padrão do "Motor de Cenas · Estilo Noturno" (fundo preto como palco, personagens duotom, rótulos com seta à mão, cartão de capítulo polaroide, gráfico neon, ideias-chave). Cada artifact que você entregar vai ser lido por uma edição automática que grava a narração, adiciona efeitos sonoros, trilha, transições e legendas, e exporta o vídeo longo 16:9 e os cortes 9:16. Para isso funcionar, siga este contrato **sem exceção**:

**Estrutura obrigatória do código**
1. Um único arquivo HTML. Palco 16:9 num elemento `#stage` com um `<svg viewBox="0 0 1920 1080">` dentro. Legenda interna em `#subs` e etiqueta em `#chip` (a edição esconde as duas e faz a própria legenda).
2. Todas as cenas num array global `const SCENES = [...]` (ou `SECTIONS` com `scenes`, como no Motor de Cenas atual), na ordem do vídeo. Cada cena tem:
   - `narration`: o texto **exato** que vai ser narrado (15 a 25 palavras, termina em ponto final, números por extenso).
   - `dur`: duração da prévia em segundos (a edição troca pela duração real da fala).
   - `render()`: devolve o SVG da cena. `tick(t, root)` opcional para animações calculadas por quadro.
   - `hot`: 1 ou 2 palavras da narração, escritas exatamente como aparecem (com a pontuação colada). Viram punch-in de câmera e cor na legenda.
   - `mold` e `layout`: o nome do molde. Cartões de capítulo usam `mold: 'cartao_capitulo'` (a edição põe a transição forte e o impacto nesses pontos).
3. Uma função global `go(i)` que monta a cena `i`, e uma variável global `let t` com o tempo da cena. O player pode usar `requestAnimationFrame` normalmente.
4. **Toda animação em CSS** (`animation` com `animation-delay` por elemento, como `.pop`, `.slideL`, `.draw`, `.fade`, `.rise`, `.grow`, `.toss`) ou calculada em `tick(t)`. Nada de `setTimeout`, `setInterval` ou animação que dependa do relógio real: a edição controla o tempo quadro a quadro.
5. Nada de imagem externa nem script de fora (só fontes do Google Fonts). Tudo desenhado em SVG no próprio arquivo.

**Tempo: ancore em PALAVRAS, nunca em segundos**
Você não sabe em que velocidade a narração vai ser falada, e não precisa saber. A edição grava a voz primeiro, mede o instante de cada palavra e encaixa a cena na fala (a cena dura exatamente o que a frase dura; as animações são aceleradas ou desaceleradas para caber). Então:
- `dur` é só a duração da prévia no navegador. Não tente acertar.
- Em todo elemento que representa algo que a narração FALA, ponha `data-palavra="a palavra"` (a palavra como aparece na narração; pode ser uma expressão curta, ex.: `data-palavra="casa própria"`). O elemento começa a entrar ~0,1 s antes dessa palavra ser dita. Ex.: `<g class="pop" style="--d:1.4s" data-palavra="emprego">…ARRUMA UM EMPREGO…</g>`.
- Elementos de ambiente (fundo, personagem, setas, decoração) ficam sem `data-palavra`: eles mantêm a ordem que você desenhou, encaixados entre os elementos ancorados.
- Se o texto visível do elemento já for uma palavra da narração ("BOLETO" e a fala diz "boleto"), a edição já casa sozinha; o `data-palavra` garante quando o texto do elemento é diferente da fala.
- Uma ideia por cena: cenas curtas (1 frase, 6 a 20 palavras) deixam o vídeo mais dinâmico do que uma cena longa com muitos elementos.

**O que ajuda a edição (opcional, mas recomendado)**
- Mantenha as classes de entrada com estes nomes: `pop` (vira som de pop), `slideL`/`slideR` (whoosh), `grow` (whoosh grave), `draw` em traços curtos (caneta), `toss` (papel). A edição põe o som exatamente no instante em que o elemento entra.
- Efeitos sonoros específicos por cena: `sfx: [{ tipo: 'notificacao', em: 'palavra' }]` ou `em: 2.4` (segundos). Tipos: pop, whoosh, whoosh_grave, risco_caneta, papel, impacto, tick, notificacao, transicao, bip, drone.
- Boca falando: marque o caminho da boca do personagem com `data-boca` (a boca do Pensador já é reconhecida sozinha). A edição troca o formato da boca de acordo com a fala.
- **Mapa:** em vez de desenhar o mapa, coloque um retângulo marcador onde ele deve aparecer:
  `<rect data-mapa="PRT,BRA" data-rota="PRT>BRA" x="120" y="60" width="1680" height="945" class="fade"/>`.
  Códigos de 3 letras (ISO) ou o nome do país em português. A edição troca pelo mapa do Natural Earth no estilo da marca, com a rota desenhando e os nomes em português. O marcador pode ter classes de animação e `clip-path`; o mapa herda.
- **Arte:** `<rect data-arte="um farol solitário numa noite de tempestade" x=.. y=.. width=.. height=../>` gera uma ilustração (FLUX, com GPU) e a vetoriza no estilo chapado. Para usar uma imagem sua: `data-arte-arquivo="farol.png"` (arquivo na pasta `biblioteca/arte` do Drive).
- **Desenho animado:** `<rect data-desenho="mascote" data-movimento="acenar" .../>` anima o desenho `biblioteca/desenhos/mascote.png` com o AnimatedDrawings (acenar, dancar, pular, zumbi).
- **Lottie:** `lottie: [{ nome: 'confete', em: 'conseguiu', x: 960, y: 400, largura: 500 }]` na cena toca `biblioteca/lottie/confete.json` na palavra indicada. Use `alvo: 'ultimo'` em vez de x/y para cair em cima do último elemento que entrou.
- Cortes verticais já escolhidos por você: no fim do script,
  `window.META = { titulo: '...', shorts: [{ titulo: 'Seu cérebro não quer ter razão', chapeu: 'psicologia', cenas: [2, 3, 4], gancho_falado: 'Você não quer a verdade.' }] }`.
  Sem isso, a edição escolhe os cortes sozinha.

**Na resposta**
Entregue o artifact completo com todas as cenas do roteiro (um vídeo de 14 a 15 minutos tem de 100 a 130 cenas). Se o roteiro for grande demais para uma resposta só, divida em partes (Parte 1: abertura e capítulos 1 e 2; Parte 2: capítulos 3 e 4...), cada parte um artifact completo que segue este mesmo contrato. Diga no fim de cada parte o nome com que ela deve ser salva: `<título> · parte N de T.html`. A edição espera todas as partes chegarem e monta um vídeo só, na ordem.
