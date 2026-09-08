import { useEffect, useState } from 'react'
import { cargarBrief, esDeHoy, haceCuanto } from './data'

const CATS = ['modelos', 'herramientas', 'investigacion', 'opinion', 'industria']

const ICONOS = {
  modelos: <><path d="M21 8v8l-9 5-9-5V8l9-5z"/><path d="M3.3 7.5 12 12.5l8.7-5"/><path d="M12 21v-8.5"/></>,
  herramientas: <><path d="M14.7 6.3a4 4 0 0 0 5 5l-9.4 9.4a2.1 2.1 0 0 1-3-3z"/><path d="M14.7 6.3 18 3l3 3-3.3 3.3"/></>,
  investigacion: <><path d="M9 2h6"/><path d="M10 2v6.4L4.6 18A2 2 0 0 0 6.3 21h11.4a2 2 0 0 0 1.7-3L14 8.4V2"/><path d="M7.5 15h9"/></>,
  opinion: <path d="M21 11.5a8.4 8.4 0 0 1-9 8.4 8.6 8.6 0 0 1-3.8-.9L3 21l1.9-5.1A8.4 8.4 0 0 1 12 3.1a8.4 8.4 0 0 1 9 8.4z"/>,
  industria: <><path d="M2 20h20"/><path d="M4 20V10l5 3.5V10l5 3.5V10l5 3.5V20"/><path d="M4 10 4.6 4h2.8L8 10"/></>,
}

const color = (c) => `var(--c-${c})`

function Filtros({ activos, alternar }) {
  return (
    <div className="filtros" role="group" aria-label="Filtrar por categoría">
      {CATS.map((c) => (
        <button
          key={c}
          className="filtro"
          style={{ '--c': color(c) }}
          aria-pressed={activos.has(c)}
          aria-label={c}
          onClick={() => alternar(c)}
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">{ICONOS[c]}</svg>
        </button>
      ))}
    </div>
  )
}

function Item({ it, abrir }) {
  return (
    <button className="item" onClick={() => abrir(it)}>
      <div className="head">
        <span className="pip" style={{ color: color(it.categoria), background: color(it.categoria) }} />
        <span className="src">{it.fuente}</span>
        <span className="ago">{haceCuanto(it.publicado)}</span>
      </div>
      <div className="tl">{it.titulo}</div>
    </button>
  )
}

function Lector({ it, volver }) {
  return (
    <div className="reader">
      <button className="back" onClick={volver}>.. volver</button>
      <h2>{it.titulo}</h2>
      <div className="rmeta">
        <span className="pip" style={{ color: color(it.categoria), background: color(it.categoria) }} />
        <span>{it.categoria} · {it.fuente} · hace {haceCuanto(it.publicado)}</span>
      </div>
      <p className="cuerpo">{it.resumen || 'Este feed no incluye resumen.'}</p>
      <a className="orig" href={it.url} target="_blank" rel="noreferrer">abrir el original</a>
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

  useEffect(() => {
    cargarBrief().then(setBrief).catch((e) => setError(e.message))
  }, [])

  const alternar = (c) => {
    const s = new Set(activos)
    s.has(c) ? s.delete(c) : s.add(c)
    setActivos(s)
    setVerResto(false)
  }

  if (error) return <div className="wrap"><div className="vacio">no se pudo cargar el brief<br />{error}</div></div>
  if (!brief) return <div className="wrap"><div className="vacio">cargando…</div></div>

  if (abierto) {
    return (
      <>
        <div className="wrap"><Lector it={abierto} volver={() => setAbierto(null)} /></div>
        <Tabs pestana={pestana} setPestana={setPestana} />
      </>
    )
  }

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

        <Filtros activos={activos} alternar={alternar} />

        {destacados.length === 0 && resto.length === 0 ? (
          <div className="vacio">nada en esta categoría hoy</div>
        ) : (
          <>
            {destacados.map((it) => <Item key={it.id} it={it} abrir={setAbierto} />)}
            {resto.length > 0 && !verResto && (
              <button className="resto" onClick={() => setVerResto(true)}>
                ver los otros {resto.length}
              </button>
            )}
            {verResto && resto.map((it) => <Item key={it.id} it={it} abrir={setAbierto} />)}
          </>
        )}
      </div>
      <Tabs pestana={pestana} setPestana={setPestana} />
    </>
  )
}

function Tabs({ pestana, setPestana }) {
  return (
    <div className="tabs">
      <div className="tabs-in">
        {['archivo', 'hoy', 'guardados'].map((n) => (
          <button
            key={n}
            className={`tab${n === 'hoy' ? ' centro' : ''}`}
            aria-current={pestana === n ? 'page' : undefined}
            onClick={() => setPestana(n)}
          >
            {n}<i />
          </button>
        ))}
      </div>
    </div>
  )
}