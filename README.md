# El Diario de Paco

Un periódico personal, limpio y tranquilo: **sin titulares cebo, sin anuncios y sin cookies**.

👉 **https://diariodepaco.github.io/**

Cada dos horas, GitHub ejecuta `diario.py`, que:

1. Lee los canales RSS de los medios de `fuentes.json` (si un canal cambia de dirección, lo busca solo en la portada del medio).
2. Quita titulares cebo, publicidad, opinión, directos, noticias en otros idiomas y noticias repetidas; el fútbol va a su sección (la UD Las Palmas primero) y el resto de deportes fuera; en Música no entra el reguetón (si varios medios cuentan lo mismo, se ve una vez y debajo pone «También lo cuentan…»).
3. Ordena por secciones y publica páginas estáticas en GitHub Pages. Las noticias de **Gáldar y Barrial** salen arriba del todo, en «Desde Gáldar».

No hace falta ningún servidor ni pagar nada, y Paco no necesita a Claude para nada.

## Secciones y fuentes

| Sección | Fuentes |
|---|---|
| Gran Canaria y Canarias | Televisión Canaria (RTVC), EFE Canarias, Canarias Ahora, Europa Press Canarias, Infonorte Digital (norte de Gran Canaria) |
| España | EFE, RTVE, Europa Press, elDiario.es, Civio, Maldita.es |
| Mundo | EFE, Europa Press, BBC News Mundo, France 24, DW |
| Ciencia y espacio | Agencia SINC, Instituto de Astrofísica de Canarias, Eureka (Daniel Marín), Naukas, The Conversation |
| Historia y arqueología | La Brújula Verde, Desperta Ferro, El Museo Canario, The Conversation |
| La Bodega: vino y buena mesa | EFE Agro (solo vino, quesos, mieles, frutas y gastronomía), La Prensa del Rioja, Vinetur (solo vino y quesos); lo canario, arriba |
| Música | Efe Eme, Ruta 66 (sin nada de reguetón) |
| UD Las Palmas y fútbol | Web de la UD Las Palmas, Europa Press Deportes y el fútbol de las demás fuentes; la UD siempre arriba |

Desactivadas (siguen en `fuentes.json` con una nota de por qué): Servimedia (RSS abandonado en 2022), CSIC, Historia National Geographic y Cueva Pintada de Gáldar (bloquean las lecturas automáticas), Popular 1, Europa Press Ciencia, Vinos de Canarias (certificado de seguridad mal puesto) y Sobremesa (sin RSS). Si algún día vuelven a funcionar, basta con quitar `"activa": false`.

Cómo se leen las que no tienen RSS: EFE y Televisión Canaria con la API de WordPress (`wp:` en `fuentes.json`), RTVE con su API en JSON, y El Museo Canario completando su certificado de seguridad incompleto (igual que hacen los navegadores).

Criterio: agencias de noticias, medios públicos, medios financiados por sus lectores, divulgación científica hecha por científicos y revistas especializadas. Los grandes diarios comerciales quedan fuera por los titulares cebo.

## Cómo cambiar cosas (desde la web de GitHub, sin instalar nada)

- **Quitar una fuente:** abre `fuentes.json`, pulsa el lápiz ✏️, pon `"activa": false` en su bloque y guarda («Commit changes»). A los pocos minutos la web se regenera.
- **Añadir una fuente:** copia un bloque, cambia el nombre, la sección y la dirección de su portada en `home` (el canal RSS se busca solo; si lo sabes, ponlo en `feeds`).
- **Más o menos noticias:** `max` en cada sección (total) y en cada fuente (máximo de esa fuente).
- **Actualizar ahora mismo:** pestaña **Actions** › **Diario de Paco** › **Run workflow**.
- **¿Qué fuentes fallan?** Abre `https://diariodepaco.github.io/estado.html` (enlazado al final de la página de fuentes como «Informe técnico»). Ahí también se ven todos los titulares descartados y por qué, para ajustar los filtros.

Los filtros (palabras de cebo, deporte, opinión…) están al principio de `diario.py`.

## Puesta en marcha (una sola vez)

1. **Settings › Pages › Build and deployment › Source: GitHub Actions.**
2. Pestaña **Actions** › **Diario de Paco** › **Run workflow**. En un par de minutos la web está en la dirección de arriba.

El repositorio tiene que ser **público** para que GitHub Pages sea gratis. No contiene nada privado.

## Leer las noticias dentro del Diario (sin cookies)

Al tocar un titular, la noticia se lee **dentro del Diario**: solo el texto, sin anuncios ni avisos de cookies. **Nada se abre fuera**: las noticias de las que no se consigue el texto no se publican, y dentro de los textos no hay enlaces a otras webs. El texto sale del propio canal del medio (RSS completo, API de WordPress o de RTVE) o, si el canal solo trae un resumen, de la página de la noticia (`lectura.py`).

Esos textos se publican **cifrados** con una clave familiar (secreto `CLAVE_DIARIO` en *Settings › Secrets and variables › Actions*): la web es pública, pero solo los dispositivos que han abierto el enlace con la clave (el del QR, `https://diariodepaco.github.io/#clave=…`) pueden leerlos. Para cualquier otra persona, el Diario solo muestra titulares. No hay archivo: cada edición lleva solo las noticias de esos días y luego desaparecen. Sin el secreto, todo funciona igual pero las noticias se abren en la web de cada medio.

## La «app» de la tablet

El Diario se instala desde Chrome como una aplicación más (es una *aplicación web*): se abre https://diariodepaco.github.io en la tablet y se toca **«Instalar El Diario en esta tablet»** (o menú ⋮ de Chrome › **Instalar aplicación** / **Añadir a pantalla de inicio**). Queda un icono en la pantalla de inicio, se abre a pantalla completa, se actualiza sola (no hay que reinstalar nada nunca) y guarda la última edición para leerla sin internet (`web/sw.js`). Las noticias se abren dentro, en una pestaña de Chrome con una X para volver.

(Hubo una APK propia, pero Google Play Protect la bloqueaba por ser una app desconocida que abre webs; con la aplicación web no hay avisos ni hay que dar permisos.)

## Probar en local

```
python diario.py --out _site                          # con internet
python diario.py --muestras carpeta_xml --out _site   # sin internet, con canales de prueba
```

Solo usa la biblioteca estándar de Python 3.9+.

---
El tiempo: datos de [Open-Meteo](https://open-meteo.com/) (CC BY 4.0).
Letras: Lora y Poppins (SIL Open Font License).
