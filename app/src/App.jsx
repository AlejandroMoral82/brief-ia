import { useEffect, useState } from 'react'
import { cargarBrief, cargarDias, nombreDia, esDeHoy, haceCuanto, cargarTexto } from './data'
import { listar, estaGuardado, alternar } from './guardados'

const CATS = ['modelos', 'herramientas', 'investigacion', 'opinion', 'industria']

const ICONOS = {
  modelos: <><path d="M21 8v8l-9 5-9-5V8l9-5z"/><path d="M3.3 7.5 12 12.5l8.7-5"/><path d="M12 21v-8.5"/></>,
  herramientas: <><path d="M14.7 6.3a4 4 0 0 0 5 5l-9.4 9.4a2.1 2.1 0 0 1-3-3z"/><path d="M14.7 6.3 18 3l3 3-3.3 3.3"/></>,
  investigacion: <><path d="M9 2h6"/><path d="M10 2v6.4L4.6 18A2 2 0 0 0 6.3 21h11.4a2 2 0 0 0 1.7-3L14 8.4V2"/><path d="M7.5 15h9"/></>,
  opinion: <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.8-.9L3 21l1.9-5.1A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z"/>,
  industria: <><path d="M2 20h20"/><path d="M4 20V10l5 3.5V10l5 3.5V10l5 3.5V20"/><path d="M4 10 4.6 4h2.8L8 10"/></>,
}

const color = (c) => `var(--c-${c})`

function Filtros({ activos, alternar: alt }) {
  return (
    <div className="filtros" role="group" aria-label="Filtrar por categoría">
      {CATS.map((c) => (
        <button key={c} className="filtro" style={{ '--c': color(c) }}
          aria-pressed={activos.has(c)} aria-label={c} onClick={() => alt(c)}>
          <svg viewBox="0 0 24 24" aria-hidden="true">{ICONOS[c]}</svg>
        </button>
      ))}
    </div>
  )
}

function Item({ it, abrir, marcado, onGuardar, bloqueado }) {
  const [dx, setDx] = useState(0)
  const [x0, setX0] = useState(null)

  const fin = () => {
    if (dx > 90) onGuardar?.(it)
    setDx(0); setX0(null)
  }

  const tocar = bloqueado ? {} : {
    onTouchStart: (e) => setX0(e.touches[0].clientX),
    onTouchMove: (e) => x0 !== null && setDx(Math.max(0, Math.min(130, e.touches[0].clientX - x0))),
    onTouchEnd: fin,
    onTouchCancel: fin,
  }

  return (
    <div className="swipe">
      <div className={`swipe-bg${marcado ? ' quitando' : ''}`} style={{ opacity: Math.min(dx / 90, 1) }}>
        {marcado
          ? (dx > 90 ? 'quitar ✓' : 'quitar de guardados')
          : (dx > 90 ? 'guardar ✓' : 'guardar')}
      </div>
      <button className="item"
        style={{ transform: `translateX(${dx}px)`, transition: x0 ? 'none' : 'transform .3s cubic-bezier(.2,.9,.2,1)' }}
        onClick={() => dx === 0 && abrir(it)}
        {...tocar}>
        <div className="head">
          <span className="pip" style={{ color: color(it.categoria), background: color(it.categoria) }} />
          <span className="src">{it.fuente}</span>
          <span className="ago">{haceCuanto(it.publicado)}</span>
        </div>
        <div className="tl">{it.titulo}</div>
        {marcado && <span className="marca" />}
      </button>
    </div>
  )
}

function Lector({ it, volver, onGuardar }) {
  const [texto, setTexto] = useState(null)
  const [fallo, setFallo] = useState(false)

  useEffect(() => {
    setTexto(null); setFallo(false)
    if (it.texto) { setTexto(it.texto); return }
    if (!it.texto_disponible) { setFallo(true); return }
    cargarTexto(it.id).then(setTexto).catch(() => setFallo(true))
  }, [it.id])

  return (
    <div className="reader">
      <button className="back" onClick={volver}>.. volver</button>
      <h2>{it.titulo}</h2>
      <div className="rmeta">
        <span className="pip" style={{ color: color(it.categoria), background: color(it.categoria) }} />
        <span>{it.categoria} · {it.fuente} · hace {haceCuanto(it.publicado)}</span>
      </div>

      {it.imagen && (
        <img className="portada" src={it.imagen} alt=""
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
                No se pudo recuperar el texto completo. Ábrelo en el original.
              </div>
            )}
          </>
        )}

      <div>
                <button className={`quitar${estaGuardado(it.id) ? ' activo' : ''}`}
          onClick={() => onGuardar(it, texto || '')}>
          {estaGuardado(it.id) ? 'quitar de guardados' : 'guardar'}
        </button>
      </div>
      <a className="orig" href={it.url} target="_blank" rel="noreferrer">
        {texto ? 'ver en el original, con imágenes' : 'abrir el original'}
      </a>
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
        <button key={d} className="dia" onClick={() => abrirDia(d)}>
          {nombreDia(d)}<span>{d}</span>
        </button>
      ))}
    </>
  )
}

function Guardados({ abrir, quitar }) {
  const items = listar()
  if (!items.length) {
    return <div className="vacio">nada guardado todavía<br />desliza un titular a la derecha</div>
  }
  return (
    <>
      <div className="titulo-seccion">Guardados</div>
      <div className="date">{items.length} artículos</div>
      {items.map((it) => (
        <div key={it.id} className="fila-guardado">
          <Item it={it} abrir={abrir} marcado bloqueado />
          <button className="quitar activo" onClick={() => quitar(it)}>quitar</button>
        </div>
      ))}
    </>
  )
}

function Tabs({ pestana, setPestana, setDia, cerrar }) {
  return (
    <div className="tabs">
      <div className="tabs-in">
        {['archivo', 'hoy', 'guardados'].map((n) => (
          <button key={n} className={`tab${n === 'hoy' ? ' centro' : ''}`}
            aria-current={pestana === n ? 'page' : undefined}
            onClick={() => { cerrar(); setPestana(n); if (n === 'hoy') setDia('latest') }}>
            {n}<i />
          </button>
        ))}
      </div>
    </div>
  )
}

export default function App() {
  const [brief, setBrief] = useState(null)
  const [error, setError] = useState(null)
  const [activos, setActivos] = useState(new Set())
  const [verResto, setVerResto] = useState(false)
  const [abierto, setAbierto] = useState(null)
  const [pestana, setPestana] = useState('hoy')
  const [dia, setDia] = useState('latest')
  const [, setVersion] = useState(0)

  useEffect(() => {
    setBrief(null)
    cargarBrief(dia).then(setBrief).catch((e) => setError(e.message))
  }, [dia])

    const guardar = (it, texto = '') => { alternar(it, texto); setVersion((v) => v + 1) }

  const alternarFiltro = (c) => {
    const s = new Set(activos)
    s.has(c) ? s.delete(c) : s.add(c)
    setActivos(s)
    setVerResto(false)
  }

  if (abierto) {
    return (
      <>
        <div className="wrap">
          <Lector it={abierto} volver={() => setAbierto(null)} onGuardar={guardar} />
        </div>
        <Tabs pestana={pestana} setPestana={setPestana} setDia={setDia} cerrar={() => setAbierto(null)} />
      </>
    )
  }

  if (pestana === 'archivo') {
    return (
      <>
        <div className="wrap">
          <Archivo abrirDia={(d) => { setDia(d); setPestana('hoy') }} />
        </div>
        <Tabs pestana={pestana} setPestana={setPestana} setDia={setDia} cerrar={() => setAbierto(null)} />
      </>
    )
  }

  if (pestana === 'guardados') {
    return (
      <>
        <div className="wrap"><Guardados abrir={setAbierto} quitar={guardar} /></div>
        <Tabs pestana={pestana} setPestana={setPestana} setDia={setDia} cerrar={() => setAbierto(null)} />
      </>
    )
  }

  if (error) return <div className="wrap"><div className="vacio">no se pudo cargar el brief<br />{error}</div></div>
  if (!brief) return <div className="wrap"><div className="vacio">cargando…</div></div>

  const filtra = (l) => (activos.size ? l.filter((i) => activos.has(i.categoria)) : l)
  const destacados = filtra(brief.items.filter((i) => i.destacado))
  const resto = filtra(brief.items.filter((i) => !i.destacado))

  const desactualizado = !esDeHoy(brief.generado_en)
  const fecha = new Date(brief.generado_en)

  return (
    <>
      <div className="wrap">
        <div className="bar">
          <span>brief · v1</span>
          <span className={desactualizado ? 'mal' : 'ok'}>
            {desactualizado ? 'sin actualizar' : `sincronizado ${fecha.toTimeString().slice(0, 5)}`}
          </span>
        </div>

        <div className="prompt">~/hoy <em>listo</em><span className="cur" /></div>
        <div className="date">
          {fecha.toLocaleDateString('es-ES', { weekday: 'long', day: 'numeric', month: 'long' })}
          {' · '}{brief.destacados} de {brief.candidatos}
        </div>

        {(desactualizado || brief.modo === 'degradado' || brief.fuentes_fallidas.length > 0) && (
          <div className="aviso">
            {desactualizado && <>El brief no es de hoy. El último es del {fecha.toLocaleDateString('es-ES')}.<br /></>}
            {brief.modo === 'degradado' && <>Sin selección: el modelo no respondió, los items van por fecha.<br /></>}
            {brief.fuentes_fallidas.length > 0 && <>Fuentes con fallo: {brief.fuentes_fallidas.join(', ')}</>}
          </div>
        )}

        <Filtros activos={activos} alternar={alternarFiltro} />

        {destacados.length === 0 && resto.length === 0 ? (
          <div className="vacio">nada en esta categoría hoy</div>
        ) : (
          <>
            {destacados.map((it) => (
              <Item key={it.id} it={it} abrir={setAbierto}
                marcado={estaGuardado(it.id)} onGuardar={guardar} />
            ))}
            {resto.length > 0 && !verResto && (
              <button className="resto" onClick={() => setVerResto(true)}>
                ver los otros {resto.length}
              </button>
            )}
            {verResto && resto.map((it) => (
              <Item key={it.id} it={it} abrir={setAbierto}
                marcado={estaGuardado(it.id)} onGuardar={guardar} />
            ))}
          </>
        )}
      </div>
      <Tabs pestana={pestana} setPestana={setPestana} setDia={setDia} cerrar={() => setAbierto(null)} />
    </>
  )
}