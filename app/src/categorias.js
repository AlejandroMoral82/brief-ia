// Categorias del brief: misma fuente que el pipeline (categorias.json en la raiz del repo).
// Los iconos SVG viven en App.jsx, indexados por id.
import datos from '../../categorias.json'

// Orden del fichero = orden de los filtros.
export const CATS = datos.categorias.map((c) => c.id)

const porId = Object.fromEntries(datos.categorias.map((c) => [c.id, c]))

// Nombre visible, con tildes. Si llega una categoria desconocida se muestra su id.
export const nombreCat = (id) => porId[id]?.nombre || id

// Color de la categoria. Desconocida: undefined, y React omite la propiedad.
export const colorCat = (id) => porId[id]?.color
