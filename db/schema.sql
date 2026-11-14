-- Base de dados da fábrica (Postgres). Carregada automaticamente no primeiro start do container.

CREATE TABLE IF NOT EXISTS tendencias (
  id           BIGSERIAL PRIMARY KEY,
  coletado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  fonte        TEXT NOT NULL,            -- youtube | google_trends | wikipedia | reddit
  regiao       TEXT NOT NULL,            -- BR | US | GLOBAL
  termo        TEXT NOT NULL,
  url          TEXT,
  metrica      TEXT,                     -- views_por_hora | buscas_aprox | pageviews | upvotes
  score_bruto  DOUBLE PRECISION,
  score        DOUBLE PRECISION,         -- normalizado + bônus de cruzamento entre fontes/países
  cruzamento   JSONB,
  extra        JSONB
);
CREATE INDEX IF NOT EXISTS tendencias_data ON tendencias (coletado_em DESC);
CREATE INDEX IF NOT EXISTS tendencias_termo ON tendencias USING gin (to_tsvector('simple', termo));

CREATE TABLE IF NOT EXISTS pautas (
  id         BIGSERIAL PRIMARY KEY,
  criado_em  TIMESTAMPTZ NOT NULL DEFAULT now(),
  tema       TEXT NOT NULL,
  angulo     TEXT,
  origem     TEXT,                       -- brasil | gringa | ambos
  titulo     TEXT,
  roteiro    TEXT,                       -- markdown que vai para a conversa de artifacts
  dados      JSONB
);

CREATE TABLE IF NOT EXISTS videos (
  job_id         TEXT PRIMARY KEY,
  pauta_id       BIGINT REFERENCES pautas(id),
  titulo         TEXT,
  duracao        DOUBLE PRECISION,
  resultado      JSONB,                  -- caminhos do longo, shorts, legendas, títulos e hashtags
  publicado      JSONB,                  -- ids de YouTube/TikTok quando publicar
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- termos que mais apareceram nos últimos 7 dias (útil para olhar no n8n ou num painel)
CREATE OR REPLACE VIEW tendencias_semana AS
SELECT termo, regiao, count(*) AS dias_em_alta, max(score) AS pico, array_agg(DISTINCT fonte) AS fontes
FROM tendencias WHERE coletado_em > now() - interval '7 days'
GROUP BY termo, regiao ORDER BY pico DESC;
