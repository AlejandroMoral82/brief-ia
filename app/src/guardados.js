const CLAVE = 'brief:guardados'

function leer() {
  try {
    return JSON.parse(localStorage.getItem(CLAVE) || '[]')
  } catch {
    return []
  }
}

export function listar() {
  return leer()
}

export function estaGuardado(id) {
  return leer().some((x) => x.id === id)
}

export function alternar(item) {
  const l = leer()
  const i = l.findIndex((x) => x.id === item.id)
  if (i >= 0) l.splice(i, 1)
  else l.unshift({ ...item, guardado_en: new Date().toISOString() })
  try {
    localStorage.setItem(CLAVE, JSON.stringify(l))
  } catch (e) {
    console.warn('no se pudo guardar', e)
  }
  return i < 0
}