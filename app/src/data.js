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

export function esDeHoy(iso) {
  const hoy = new Date().toISOString().slice(0, 10)
  return iso?.slice(0, 10) === hoy
}

export function haceCuanto(iso) {
  const h = Math.floor((Date.now() - new Date(iso)) / 3600000)
  if (h < 1) return 'ahora'
  if (h < 24) return `${h} h`
  return `${Math.floor(h / 24)} d`
}