import { useEffect, useLayoutEffect, useMemo, useState, useRef } from 'react'
import {
  cargarBrief, cargarDias, nombreDia, estaDesactualizado, horasDesde, haceCuanto, cargarTexto, urlSegura,
} from './data'
import { listar, idsGuardados, alternar, escucharCambios } from './guardados'

const CATS = ['modelos', 'herramientas', 'investigacion', 'opinion', 'industria']

const NOMBRES = {
  modelos: 'Modelos',
  herramientas: 'Herramientas',
  investigacion: 'Investigación',
  opinion: 'Opinión',
  industria: 'Industria',
}
const nombreCat = (c) => NOMBRES[c] || c

const ICONOS = {
  modelos: <><path d="M21 8v8l-9 5-9-5V8l9-5z"/><path d="M3.3 7.5 12 12.5l8.7-5"/><path d="M12 21v-8.5"/></>,
  herramientas: <><path d="M14.7 6.3a4 4 0 0 0 5 5l-9.4 9.4a2.1 2.1 0 0 1-3-3z"/><path d="M14.7 6.3 18 3l3 3-3.3 3.3"/></>,
  investigacion: <><path d="M9 2h6"/><path d="M10 2v6.4L4.6 18A2 2 0 0 0 6.3 21h11.4a2 2 0 0 0 1.7-3L14 8.4V2"/><path d="M7.5 15h9"/></>,
  opinion: <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.8-.9L3 21l1.9-5.1A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z"/>,
  industria: <><path d="M2 20h20"/><path d="M4 20V10l5 3.5V10l5 3.5V10l5 3.5V20"/><path d="M4 10 4.6 4h2.8L8 10"/></>,
}

const color = (c) => `var(--c-${c})`

// Gesto de deslizar: a partir de UMBRAL_EJE px se decide si es horizontal o scroll.
const UMBRAL_EJE = 10
const UMBRAL_GUARDAR = 90

const horaMinutos = (iso) => new Date(iso).toTimeString().slice(0, 5)

function Filtros({ activos, alternar: alt }) {
  return (
    <div className="filtros" role="group" aria-label="Filtrar por categoría">
      {CATS.map((c) => (
        <button key={c} type="button" className="filtro" style={{ '--c': color(c) }}
          aria-pressed={activos.has(c)} aria-label={nombreCat(c)} title={nombreCat(c)}
          onClick={() => alt(c)}>
          <svg viewBox="0 0 24 24" aria-hidden="true">{ICONOS[c]}</svg>
        </button>
      ))}
    </div>
  )
}

function Item({ it, abrir, marcado, onGuardar, bloqueado, par }) {
  const [dx, setDx] = useState(0)
  const [arrastrando, setArrastrando] = useState(false)
  const inicio = useRef(null)
  const eje = useRef(null)
  const ultimoGesto = useRef(0)

  const fin = () => {
    if (eje.current === 'x' && dx > UMBRAL_GUARDAR) onGuardar?.(it)
    inicio.current = null
    eje.current = null
    setDx(0)
    setArrastrando(false)
  }

  const tocar = bloqueado ? {} : {
    onTouchStart: (e) => {
      const t = e.touches[0]
      inicio.current = { x: t.clientX, y: t.clientY }
      eje.current = null
    },
    onTouchMove: (e) => {
      if (!inicio.current) return
      const t = e.touches[0]
      const mx = t.clientX - inicio.current.x
      const my = t.clientY - inicio.current.y
      if (!eje.current) {
        if (Math.abs(mx) < UMBRAL_EJE && Math.abs(my) < UMBRAL_EJE) return
        // Se decide una sola vez por toque: si domina el vertical es scroll y se ignora.
        eje.current = Math.abs(mx) > Math.abs(my) ? 'x' : 'y'
        ultimoGesto.current = Date.now()
        if (eje.current === 'x') setArrastrando(true)
      }
      if (eje.current === 'x') setDx(Math.max(0, Math.min(130, mx)))
    },
    onTouchEnd: fin,
    onTouchCancel: fin,
  }

  // Tras un deslizamiento el navegador puede disparar un click: no abre el articulo.
  const pulsar = () => {
    if (Date.now() - ultimoGesto.current < 400) return
    abrir(it)
  }

  return (
    <div className="swipe">
      <div className={`swipe-bg${marcado ? ' quitando' : ''}`} aria-hidden="true"
        style={{ opacity: Math.min(dx / UMBRAL_GUARDAR, 1) }}>
        {marcado
          ? (dx > UMBRAL_GUARDAR ? 'quitar ✓' : 'quitar de guardados')
          : (dx > UMBRAL_GUARDAR ? 'guardar ✓' : 'guardar')}
      </div>
      <button type="button" data-item={it.id} className={`item${par ? ' par' : ''}`}
        style={{ transform: `translateX(${dx}px)`, transition: arrastrando ? 'none' : 'transform .3s cubic-bezier(.2,.9,.2,1)' }}
        onClick={pulsar}
        {...tocar}>
        <span className="head">
          <span className="pip" style={{ color: color(it.categoria), background: color(it.categoria) }} />
          <span className="src">{it.fuente}</span>
          <span className="ago">{haceCuanto(it.publicado)}</span>
        </span>
        <span className="tl">{it.titulo}</span>
        {marcado && <span className="marca" />}
      </button>
    </div>
  )
}

function Lector({ it, volver, onGuardar, guardado }) {
  const titulo = useRef(null)
  const [carga, setCarga] = useState({ id: null })
  const hayQueCargar = !it.texto && Boolean(it.texto_disponible)

  useEffect(() => {
    if (!hayQueCargar) return
    let vigente = true
    cargarTexto(it.id)
      .then((texto) => { if (vigente) setCarga({ id: it.id, texto }) })
      .catch(() => { if (vigente) setCarga({ id: it.id, fallo: true }) })
    return () => { vigente = false }
  }, [it.id, hayQueCargar])

  // El foco va al titulo para que el lector de pantalla anuncie el articulo.
  useEffect(() => { titulo.current?.focus({ preventScroll: true }) }, [it.id])

  const propio = carga.id === it.id ? carga : {}
  const texto = it.texto || propio.texto || null
  const fallo = !texto && (!it.texto_disponible || propio.fallo)
  const enlace = urlSegura(it.url)
  const imagen = urlSegura(it.imagen)

  return (
    <div className="reader">
      <button type="button" className="back" onClick={volver}>.. volver</button>
      <h2 ref={titulo} tabIndex={-1}>{it.titulo}</h2>
      <div className="rmeta">
        <span className="pip" style={{ color: color(it.categoria), background: color(it.categoria) }} />
        <span>{nombreCat(it.categoria)} · {it.fuente} · hace {haceCuanto(it.publicado)}</span>
      </div>

      {imagen && (
        <img className="portada" src={imagen} alt="" referrerPolicy="no-referrer" loading="lazy"
          onError={(e) => { e.currentTarget.style.display = 'none' }} />
      )}

      {texto
        ? texto.split('\n').filter((p) => p.trim()).map((p, i) => (
            <p className="cuerpo" key={i}>{p}</p>
          ))
        : (
          <>
            <p className="cuerpo">{it.resumen || 'Este feed no incluye resumen.'}</p>
            {fallo && (
              <div className="aviso" style={{ marginTop: 22 }}>
                No se pudo recuperar el texto completo.{enlace && ' Ábrelo en el original.'}
              </div>
            )}
          </>
        )}

      <div>
        <button type="button" className={`quitar${guardado ? ' activo' : ''}`}
          onClick={() => onGuardar(it, texto || '')}>
          {guardado ? 'quitar de guardados' : 'guardar'}
        </button>
      </div>
      {enlace
        ? (
          <a className="orig" href={enlace} target="_blank" rel="noreferrer">
            {texto ? 'ver en el original, con imágenes' : 'abrir el original'}
          </a>
        )
        : <div className="aviso" style={{ marginTop: 38 }}>El enlace original no es válido.</div>}
    </div>
  )
}

function Archivo({ abrirDia }) {
  const [info, setInfo] = useState(null)
  useEffect(() => { cargarDias().then(setInfo).catch(() => setInfo({ dias: [], bytes: 0 })) }, [])

  if (!info) return <div className="vacio">cargando…</div>
  if (!info.dias.length) return <div className="vacio">todavía no hay archivo</div>

  const mb = (info.bytes / 1048576).toFixed(1)

  return (
    <>
      <div className="titulo-seccion">Archivo</div>
      <div className="date">
        {info.dias.length} días · {mb} MB · se borra a los 30 días
      </div>
      {info.dias.map((d) => (
        <button key={d} type="button" className="dia" onClick={() => abrirDia(d)}>
          {nombreDia(d)}<span>{d}</span>
        </button>
      ))}
    </>
  )
}

function Guardados({ abrir, quitar, ids }) {
  // Solo se relee localStorage cuando cambia el conjunto de guardados.
  const items = useMemo(() => listar().filter((x) => ids.has(x.id)), [ids])
  if (!items.length) {
    return <div className="vacio">nada guardado todavía<br />desliza un titular a la derecha</div>
  }
  return (
    <>
      <div className="titulo-seccion">Guardados</div>
      <div className="date">{items.length} artículos</div>
      {items.map((it, n) => (
        <div key={it.id} className="fila-guardado">
          <Item it={it} abrir={abrir} marcado bloqueado par={n % 2 === 1} />
          <button type="button" className="quitar activo" onClick={() => quitar(it)}>quitar</button>
        </div>
      ))}
    </>
  )
}

function Brief({ brief, dia, activos, alternarFiltro, verResto, mostrarResto, abrir, guardados, guardar }) {
  const esUltimo = dia === 'latest'

  const filtra = (l) => (activos.size ? l.filter((i) => activos.has(i.categoria)) : l)
  const destacados = filtra(brief.items.filter((i) => i.destacado))
  const resto = filtra(brief.items.filter((i) => !i.destacado))
  const total = destacados.length + resto.length
  const visibles = verResto ? total : destacados.length

  // generado_en: de cuando es el contenido. comprobado_en: la ultima vez que corrio el pipeline.
  const comprobado = brief.comprobado_en || brief.generado_en
  const desactualizado = esUltimo && estaDesactualizado(comprobado)
  const horas = Math.floor(horasDesde(comprobado))
  const generado = new Date(brief.generado_en)
  const fecha = Number.isNaN(generado.getTime())
    ? (esUltimo ? '' : dia)
    : generado.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })

  return (
    <>
      <div className="bar">
        <span>Bienvenido a tu brief-ia</span>
        {esUltimo
          ? (
            <span className={desactualizado ? 'mal' : 'ok'}>
              {desactualizado ? 'sin actualizar' : `sincronizado ${horaMinutos(comprobado)}`}
            </span>
          )
          : <span>archivo</span>}
      </div>

      <div className="cabecera">
        <div className="prompt">{esUltimo ? '~/hoy' : `~/archivo/${dia}`} <em>listo</em><span className="cur" /></div>
        <div className="date">
          {fecha}{fecha && ' · '}{visibles} de {total}
        </div>
      </div>

      {(desactualizado || brief.modo === 'degradado' || brief.fuentes_fallidas.length > 0) && (
        <div className="aviso">
          {desactualizado && (
            Number.isFinite(horas)
              ? <>El brief lleva {horas} h sin actualizarse. Última comprobación: {new Date(comprobado).toLocaleString('es-ES', { dateStyle: 'short', timeStyle: 'short' })}.<br /></>
              : <>El brief no indica cuándo se actualizó.<br /></>
          )}
          {brief.modo === 'degradado' && <>Sin selección: el modelo no respondió, los items van por fecha.<br /></>}
          {brief.fuentes_fallidas.length > 0 && <>Fuentes con fallo: {brief.fuentes_fallidas.join(', ')}</>}
        </div>
      )}

      <Filtros activos={activos} alternar={alternarFiltro} />

      {total === 0 ? (
        <div className="vacio">nada en esta categoría{esUltimo && ' hoy'}</div>
      ) : (
        <>
          {destacados.map((it, n) => (
            <Item key={it.id} it={it} abrir={abrir} par={n % 2 === 1}
              marcado={guardados.has(it.id)} onGuardar={guardar} />
          ))}
          {resto.length > 0 && !verResto && (
            <button type="button" className="resto" onClick={mostrarResto}>
              ver los otros {resto.length}
            </button>
          )}
          {verResto && resto.map((it) => (
            <Item key={it.id} it={it} abrir={abrir}
              marcado={guardados.has(it.id)} onGuardar={guardar} />
          ))}
        </>
      )}
    </>
  )
}

function Tabs({ pestana, ir }) {
  return (
    <nav className="tabs" aria-label="Secciones">
      <div className="tabs-in">
        {['archivo', 'hoy', 'guardados'].map((n) => (
          <button key={n} type="button" className={`tab${n === 'hoy' ? ' centro' : ''}`}
            aria-current={pestana === n ? 'page' : undefined}
            onClick={() => ir(n)}>
            {n}<i aria-hidden="true" />
          </button>
        ))}
      </div>
    </nav>
  )
}

export default function App() {
  const [pestana, setPestana] = useState('hoy')
  const [dia, setDia] = useState('latest')
  const [intento, setIntento] = useState(0)
  const [carga, setCarga] = useState({ clave: null })
  const [activos, setActivos] = useState(new Set())
  const [verResto, setVerResto] = useState(false)
  const [abierto, setAbierto] = useState(null)
  const [guardados, setGuardados] = useState(() => idsGuardados())
  const [aviso, setAviso] = useState('')

  // Cada carga se identifica por dia + intento. Una respuesta que llega tarde
  // (se cambio de dia mientras tanto) se descarta, y al cambiar de dia o
  // reintentar el error anterior deja de aplicar sin tener que borrarlo.
  const clave = `${dia}|${intento}`
  useEffect(() => {
    let vigente = true
    const k = `${dia}|${intento}`
    cargarBrief(dia)
      .then((brief) => { if (vigente) setCarga({ clave: k, brief, error: null }) })
      .catch((e) => { if (vigente) setCarga({ clave: k, brief: null, error: e.message }) })
    return () => { vigente = false }
  }, [dia, intento])
  const actual = carga.clave === clave ? carga : null
  const brief = actual?.brief
  const error = actual?.error

  useEffect(() => escucharCambios(() => setGuardados(idsGuardados())), [])

  // ---------- aviso discreto ----------
  const temporizador = useRef(null)
  const avisar = (msg) => {
    clearTimeout(temporizador.current)
    setAviso(msg)
    temporizador.current = setTimeout(() => setAviso(''), 4000)
  }
  useEffect(() => () => clearTimeout(temporizador.current), [])

  // ---------- guardar ----------
  const enCurso = useRef(new Set())
  const guardar = async (it, texto = '') => {
    if (enCurso.current.has(it.id)) return
    enCurso.current.add(it.id)
    try {
      let t = texto
      // Desde la lista no hay texto a mano: si el articulo lo tiene, se descarga para leerlo offline.
      if (!t && !guardados.has(it.id) && it.texto_disponible) {
        t = await cargarTexto(it.id).catch(() => '')
      }
      const r = alternar(it, t)
      setGuardados(idsGuardados())
      if (!r.ok) avisar(r.guardado ? 'no se pudo quitar de guardados' : 'no se pudo guardar: almacenamiento lleno o bloqueado')
      else if (r.sinTexto) avisar('guardado sin el texto: no queda espacio')
    } finally {
      enCurso.current.delete(it.id)
    }
  }

  // ---------- historial: el gesto de atras navega dentro de la app ----------
  const vista = abierto ? `articulo:${abierto.id}` : `${pestana}:${dia}`
  const primera = useRef(true)

  useEffect(() => {
    if (primera.current) {
      history.replaceState({ vista }, '')
      primera.current = false
      return
    }
    if (history.state?.vista !== vista) history.pushState({ vista }, '')
  }, [vista])

  const ultimoAbierto = useRef(null)
  useEffect(() => { if (abierto) ultimoAbierto.current = abierto }, [abierto])

  useEffect(() => {
    const atras = (e) => {
      const v = e.state?.vista || 'hoy:latest'
      if (v.startsWith('articulo:')) {
        const it = ultimoAbierto.current
        setAbierto(it && `articulo:${it.id}` === v ? it : null)
        return
      }
      const [p, d] = v.split(':')
      setAbierto(null)
      setPestana(p)
      setDia(d)
    }
    window.addEventListener('popstate', atras)
    return () => window.removeEventListener('popstate', atras)
  }, [])

  // ---------- scroll y foco entre lista y lector ----------
  const retorno = useRef(null)
  const abrir = (it) => {
    retorno.current = { vista: `${pestana}:${dia}`, y: window.scrollY, id: it.id }
    setAbierto(it)
  }

  useLayoutEffect(() => {
    if (abierto) {
      window.scrollTo(0, 0)
      return
    }
    const r = retorno.current
    retorno.current = null
    // Solo se restaura si se vuelve a la misma lista desde la que se abrio.
    if (!r || r.vista !== `${pestana}:${dia}`) return
    window.scrollTo(0, r.y)
    document.querySelector(`[data-item="${CSS.escape(r.id)}"]`)?.focus({ preventScroll: true })
  }, [abierto, pestana, dia])

  // ---------- navegacion ----------
  const ir = (n) => {
    setAbierto(null)
    setPestana(n)
    if (n !== 'guardados') setDia('latest')
  }

  const alternarFiltro = (c) => {
    const s = new Set(activos)
    if (s.has(c)) s.delete(c)
    else s.add(c)
    setActivos(s)
    setVerResto(false)
  }

  let contenido
  let conParticulas = false

  if (abierto) {
    contenido = <Lector it={abierto} volver={() => setAbierto(null)} onGuardar={guardar} guardado={guardados.has(abierto.id)} />
  } else if (pestana === 'guardados') {
    contenido = <Guardados abrir={abrir} quitar={guardar} ids={guardados} />
  } else if (pestana === 'archivo' && dia === 'latest') {
    contenido = <Archivo abrirDia={setDia} />
  } else if (error) {
    contenido = (
      <div className="vacio">
        no se pudo cargar el brief<br />{error}<br />
        <button type="button" className="reintentar" onClick={() => setIntento((n) => n + 1)}>reintentar</button>
      </div>
    )
  } else if (!brief) {
    contenido = <div className="vacio">cargando…</div>
  } else {
    conParticulas = true
    contenido = (
      <Brief brief={brief} dia={dia} activos={activos} alternarFiltro={alternarFiltro}
        verResto={verResto} mostrarResto={() => setVerResto(true)}
        abrir={abrir} guardados={guardados} guardar={guardar} />
    )
  }

  return (
    <>
      {conParticulas && <Particulas />}
      <main className="wrap">{contenido}</main>
      <Tabs pestana={pestana} ir={ir} />
      <div className="toast" role="status" aria-live="polite">{aviso}</div>
    </>
  )
}

function Particulas() {
  const ref = useRef(null)

  useEffect(() => {
    const c = ref.current
    if (!c || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const ctx = c.getContext('2d')
    const dpr = window.devicePixelRatio || 1
    let w, h, raf

    const medir = () => {
      w = c.offsetWidth; h = c.offsetHeight
      c.width = w * dpr; c.height = h * dpr
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    medir()

        const GLIFOS = '01{}[]<>/\\|$#*+=~^_'
        const ps = Array.from({ length: Math.round(h / 5) }, () => ({
      x: Math.random() * w,
      y: Math.random() * h,
      v: 0.05 + Math.random() * 0.12,
      ch: GLIFOS[Math.floor(Math.random() * GLIFOS.length)],
      a: 0.1 + Math.random() * 0.28,
      t: Math.random() * 200,
    }))

    const pintar = () => {
      ctx.clearRect(0, 0, w, h)
      ctx.font = '11px "IBM Plex Mono", monospace'
      for (const p of ps) {
        p.y += p.v
        p.t += 1
        if (p.t > 160) {                 // cambia de glifo de vez en cuando
          p.ch = GLIFOS[Math.floor(Math.random() * GLIFOS.length)]
          p.t = 0
        }
        if (p.y > h + 8) { p.y = -8; p.x = Math.random() * w }
        ctx.fillStyle = `rgba(76,224,126,${p.a})`
        ctx.fillText(p.ch, p.x, p.y)
      }
      raf = requestAnimationFrame(pintar)
    }
    pintar()

    window.addEventListener('resize', medir)
    return () => { cancelAnimationFrame(raf); window.removeEventListener('resize', medir) }
  }, [])

  return <canvas className="particulas" ref={ref} aria-hidden="true" />
}
