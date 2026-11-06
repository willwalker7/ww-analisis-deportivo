# Web Análisis Deportivo — motor de datos

Web pública de probabilidades y estadísticas de LaLiga. Recoge datos de **football-data.org**, calcula estadísticas y predicciones con un modelo de Poisson propio y guarda todo en `data/` como JSON. GitHub Actions lo ejecuta en la nube, sin depender de ningún ordenador encendido. La web solo tiene que leer esos JSON.

Por decisión del proyecto **no se muestran ni se calculan cuotas**: solo estadísticas y porcentajes.

## Estructura

```
src/
  config.py       Competición, temporada y ajustes
  api_client.py   Cliente de football-data.org (respeta 10 peticiones/minuto)
  model.py        Modelo de Poisson + evaluación + simulación retrospectiva
  stats.py        Normalización de datos y estadísticas por equipo
  update.py       El job que ejecuta GitHub Actions
  demo.py         Cliente simulado para probar sin clave
site/                     La web (HTML, CSS y JS sin dependencias)
scripts/check_access.py   Comprueba tu clave y el acceso a la temporada
scripts/preview.py        Vista previa local de la web
.github/workflows/        update-data.yml (cron), pages.yml (publica la web) y tests.yml
data/                     Salida (la lee la web)
```

## Puesta en marcha

### 1. Conseguir la clave y comprobarla

Regístrate gratis en football-data.org; la clave llega por email. Después, en la consola (CMD) dentro de esta carpeta:

```
py -m pip install -r requirements.txt
set FOOTBALL_DATA_KEY=tu_clave
py scripts\check_access.py
```

En PowerShell, la segunda línea es `$env:FOOTBALL_DATA_KEY="tu_clave"`.

### 2. Subir el proyecto a GitHub

Crea un repositorio y sube esta carpeta. Si el repositorio es **privado**, GitHub da 2.000 minutos gratis al mes; este job gasta unos 1.600 (cada ejecución cuenta como 1 minuto). Si es **público**, los minutos son ilimitados.

### 3. Guardar la clave como secreto

En el repositorio: **Settings → Secrets and variables → Actions → New repository secret**

- Nombre: `FOOTBALL_DATA_KEY`
- Valor: tu clave

Opcional, en la pestaña **Variables**: `COMPETITION` (`PD` = LaLiga) y `SEASON` (2026 = temporada 2026-27).

### 4. Primera ejecución

Pestaña **Actions → Actualizar datos → Run workflow** (marca "Forzar refresco completo"). En un minuto aparecerán los JSON en `data/` con un commit del bot. Desde ahí se ejecuta solo.

## La web

Se publica con GitHub Pages. Configuración (una sola vez): **Settings → Pages → Build and deployment → Source: GitHub Actions**.

- Cada vez que el job guarda datos nuevos, lanza `pages.yml` y la web se republica sola.
- Si cambias algo en `site/`, se republica al hacer push.
- Vista previa en tu ordenador: `py scripts\preview.py` (abre http://localhost:8000).

Secciones: próxima jornada con probabilidades (más el partido en juego, si lo hay), clasificación, ficha de cada equipo y rendimiento del modelo.

## Cómo hace las peticiones

El plan gratuito no tiene límite diario, solo 10 peticiones por minuto. Cada ejecución hace como mucho 2:

| Momento | Peticiones |
|---|---|
| Refresco completo diario (calendario + clasificación) | 2 |
| Cada 15 min **sin** partidos en juego | 0 (lo decide en local) |
| Cada 15 min **con** partidos en juego (marcadores del día) | 1 |
| Al terminar partidos (clasificación) | 1 |

## Limitaciones del plan gratuito

- **Marcadores con retraso:** el seguimiento durante el partido no es en directo real. El directo es un add-on de pago (unos 12 €/mes). El código no cambia, solo la clave.
- **Sin estadísticas de partido** (tiros, posesión, córners): son un add-on de pago. Todo lo que genera el proyecto se calcula a partir de los resultados.
- **12 competiciones gratis**, entre ellas LaLiga, Premier, Serie A, Bundesliga, Ligue 1 y Champions. Para cambiar de liga basta con cambiar `COMPETITION` (PL, SA, BL1, FL1, CL…).

## Archivos que genera (`data/`)

| Archivo | Contenido |
|---|---|
| `fixtures.json` | Todos los partidos con estado y marcador. Fechas en UTC. |
| `standings.json` | Clasificación oficial |
| `teams.json` | Por equipo: goles a favor y en contra, medias, % portería a cero, % ambos marcan, % más de 2,5, racha, casa/fuera |
| `predictions.json` | Próximas 2 jornadas: goles esperados, 1X2, más/menos 1,5/2,5/3,5, ambos marcan, 5 marcadores más probables |
| `history.json` | Predicción congelada antes de cada partido y su evaluación al terminar |
| `performance.json` | Aciertos del modelo en real y en simulación retrospectiva |
| `meta.json` | Última actualización |

Estados de partido: `NS` (sin empezar), `LIVE` (en juego), `HT` (descanso), `FT` (terminado), `PST`/`CANC`/`SUSP`/`AWD` (aplazado, cancelado, suspendido, resuelto en despacho). Las probabilidades van de 0 a 1 (0,5543 = 55,4 %).

## El modelo

Poisson con fuerza de ataque y defensa por equipo, relativa a la media de la liga, más dos ajustes:

- **Contracción:** cada equipo arranca con 5 partidos "de equipo medio", para que pocas jornadas no den resultados extremos.
- **Decaimiento:** los partidos recientes pesan más (vida media de 120 días).

`performance.json` incluye desde el primer día una **simulación retrospectiva**: cada partido ya jugado se predice usando solo los anteriores. Así se puede mostrar el acierto real del modelo en la web.

## Probar sin clave

```
py -m src.update --demo        (genera demo_data\ con una liga simulada)
py -m pip install -r requirements-dev.txt
py -m pytest -q
```
