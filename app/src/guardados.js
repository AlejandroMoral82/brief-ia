const CLAVE = 'brief:guardados'
const TOPE_TEXTO = 25

function leer() {
  try {
    const l = JSON.parse(localStorage.getItem(CLAVE) || '[]')
    return Array.isArray(l) ? l : []
  } catch {
    return []        // localStorage bloqueado o contenido corrupto
  }
}

function escribir(l) {
  try {
    localStorage.setItem(CLAVE, JSON.stringify(l))
    return true
  } catch {
    return false     // cuota llena o almacenamiento no disponible
  }
}

export function listar() {
  return leer()
}

// Para que la app consulte un Set en memoria en vez de parsear localStorage por item.
export function idsGuardados() {
  return new Set(leer().map((x) => x.id))
}

// Avisa si los guardados cambian en otra pestaña.
export function escucharCambios(cb) {
  const f = (e) => { if (e.key === CLAVE || e.key === null) cb() }
  window.addEventListener('storage', f)
  return () => window.removeEventListener('storage', f)
}

/**
 * Guarda o quita un item. Devuelve lo que ha pasado de verdad:
 *   ok        la escritura funciono
 *   guardado  estado final del item
 *   sinTexto  se guardo, pero sin el texto, porque no cabia
 */
export function alternar(item, texto = '') {
  const l = leer()
  const i = l.findIndex((x) => x.id === item.id)

  if (i >= 0) {
    const resto = l.filter((_, n) => n !== i)
    return escribir(resto) ? { ok: true, guardado: false } : { ok: false, guardado: true }
  }

  const conTexto = l.filter((x) => x.texto).length
  const nuevo = {
    ...item,
    texto: conTexto < TOPE_TEXTO ? texto : '',
    guardado_en: new Date().toISOString(),
  }
  if (escribir([nuevo, ...l])) return { ok: true, guardado: true }

  // Cuota llena: reintenta sin el texto, que es lo que mas ocupa.
  if (nuevo.texto && escribir([{ ...nuevo, texto: '' }, ...l])) {
    return { ok: true, guardado: true, sinTexto: true }
  }
  return { ok: false, guardado: false }
}
