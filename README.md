# brief-ia

Brief diario de noticias de IA. Un job nocturno lee los feeds del OPML,
descarta lo ya visto, pide al LLM que elija y clasifique, y escribe un JSON
en el repo. La PWA solo lee ese JSON.

El LLM **no genera texto**: titulos y resumenes son siempre los del feed
original. El modelo solo decide que entra, en que orden y con que categoria.

## Puesta en marcha

1. Repo **publico** (Actions gratis sin limite de minutos).
2. Consigue una API key en Google AI Studio.
3. Settings → Secrets and variables → Actions → New secret: `GEMINI_API_KEY`.
4. Settings → Actions → General → Workflow permissions → **Read and write**.
5. Actions → "brief diario" → Run workflow, para probar sin esperar al cron.

## En local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GEMINI_API_KEY=...
python -m pipeline.build
```

Sin la variable de entorno funciona igual, en modo degradado.

## Contrato de `data/latest.json`

```json
{
  "generado_en": "2026-09-07T04:31:02+00:00",
  "modo": "normal",
  "fuentes_fallidas": ["Anthropic News (RSSHub): HTTPError"],
  "candidatos": 61,
  "items": [
    {
      "id": "a1b2c3d4e5f6",
      "url": "https://...",
      "titulo": "titulo original del feed",
      "fuente": "Simon Willison",
      "publicado": "2026-09-07T02:11:00+00:00",
      "resumen": "resumen original del feed, sin etiquetas",
      "categoria": "herramientas",
      "posicion": 1
    }
  ]
}
```

La PWA debe comprobar `generado_en` contra la fecha de hoy y avisar si no
coincide, y pintar `fuentes_fallidas` y `modo: degradado` como aviso.

## Variables

| Variable | Por defecto | Que hace |
|---|---|---|
| `GEMINI_API_KEY` | — | Sin ella, modo degradado |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Comprueba el nombre vigente en AI Studio |
| `MAXIMO_ITEMS` | `8` | Items del brief |
| `VENTANA_HORAS` | `26` | Margen sobre 24h por si el cron se retrasa |

## Decisiones que no conviene cambiar sin pensar

- `seen.json` solo se actualiza con lo procesado. Si un feed falla, sus items
  entran manana en vez de perderse.
- Una sola llamada al LLM con todos los candidatos: para priorizar necesita
  verlos juntos.
- Si el LLM devuelve un `id` que no estaba en la entrada, se descarta.
- Anadir una fuente es editar `feeds.opml`, nunca el codigo.

## Siguiente

- [ ] PWA que consuma `latest.json`
- [ ] Extraccion del texto completo (`content:encoded` primero, `trafilatura` como fallback)
- [ ] Conjunto de evaluacion: 10 articulos elegidos a mano para comparar con la seleccion del LLM
