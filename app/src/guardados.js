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

const TOPE_TEXTO = 25

export function alternar(item, texto = '') {
  const l = leer()
  const i = l.findIndex((x) => x.id === item.id)
  if (i >= 0) {
    l.splice(i, 1)
  } else {
    const con = l.filter((x) => x.texto).length
    l.unshift({
      ...item,
      texto: con < TOPE_TEXTO ? texto : '',
      guardado_en: new Date().toISOString(),
    })
  }
  try {
    localStorage.setItem(CLAVE, JSON.stringify(l))
  } catch {
    // cuota llena: reintenta sin el texto
    if (i < 0) { l[0].texto = '' }
    try { localStorage.setItem(CLAVE, JSON.stringify(l)) } catch {}
  }
  return i < 0
}