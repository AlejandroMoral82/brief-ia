const BASE = import.meta.env.BASE_URL

export async function cargarBrief(dia = 'latest') {
  const r = await fetch(`${BASE}data/${dia}.json`, { cache: 'no-cache' })
  if (!r.ok) throw new Error(`no se pudo cargar ${dia}`)
  return r.json()
}

export async function cargarDias() {
  const r = await fetch(`${BASE}data/index.json`, { cache: 'no-cache' })
  return r.ok ? r.json() : []
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

export function esDeHoy(iso) {
  const d = new Date(iso)
  const hoy = new Date()
  return d.getFullYear() === hoy.getFullYear()
    && d.getMonth() === hoy.getMonth()
    && d.getDate() === hoy.getDate()
}

export function haceCuanto(iso) {
  const h = Math.floor((Date.now() - new Date(iso)) / 3600000)
  if (h < 1) return 'ahora'
  if (h < 24) return `${h} h`
  return `${Math.floor(h / 24)} d`
}