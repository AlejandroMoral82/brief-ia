const BASE = import.meta.env.BASE_URL

// Pasado este tiempo sin una pasada del pipeline, el brief se considera desactualizado.
export const HORAS_FRESCURA = 16

export async function cargarBrief(dia = 'latest') {
  const r = await fetch(`${BASE}data/${dia}.json`, { cache: 'no-cache' })
  if (!r.ok) throw new Error(`no se pudo cargar ${dia}`)
  const b = await r.json().catch(() => null)
  // Un JSON con otra forma iria a parar a una pantalla en blanco: mejor un error con reintento.
  if (!b || !Array.isArray(b.items)) throw new Error(`formato inesperado en ${dia}`)
  return { ...b, fuentes_fallidas: Array.isArray(b.fuentes_fallidas) ? b.fuentes_fallidas : [] }
}

export async function cargarDias() {
  const r = await fetch(`${BASE}data/index.json`, { cache: 'no-cache' })
  if (!r.ok) return { dias: [], bytes: 0 }
  const d = await r.json()
  return Array.isArray(d) ? { dias: d, bytes: 0 } : d
}

export function nombreDia(iso) {
  const [a, m, d] = iso.split('-')
  const f = new Date(Number(a), Number(m) - 1, Number(d))
  const hoy = new Date()
  const ayer = new Date(hoy); ayer.setDate(hoy.getDate() - 1)
  const mismo = (x, y) => x.toDateString() === y.toDateString()
  if (mismo(f, hoy)) return 'hoy'
  if (mismo(f, ayer)) return 'ayer'
  return f.toLocaleDateString('es-ES', { weekday: 'short', day: 'numeric', month: 'short' })
}

export function horasDesde(iso) {
  return (Date.now() - new Date(iso)) / 3600000
}

// Por antiguedad y no por dia natural: asi no salta cada madrugada antes de la pasada de la manana.
// Una fecha invalida cuenta como desactualizada.
export function estaDesactualizado(iso, horas = HORAS_FRESCURA) {
  const h = horasDesde(iso)
  return !(h <= horas)
}

export function haceCuanto(iso) {
  const h = Math.floor(horasDesde(iso))
  if (h < 1) return 'ahora'
  if (h < 24) return `${h} h`
  return `${Math.floor(h / 24)} d`
}

// Solo http(s): una URL de un feed con otro esquema no llega ni a enlaces ni a imagenes.
export function urlSegura(u) {
  if (typeof u !== 'string' || !u) return ''
  try {
    const x = new URL(u)
    return x.protocol === 'https:' || x.protocol === 'http:' ? x.href : ''
  } catch {
    return ''
  }
}

export async function cargarTexto(id) {
  const r = await fetch(`${BASE}data/articles/${id}.json`, { cache: 'force-cache' })
  if (!r.ok) throw new Error('sin texto')
  const { texto } = await r.json()
  if (typeof texto !== 'string') throw new Error('sin texto')
  return texto
}
