# El Diario de Paco

Un periódico personal, limpio y tranquilo: **sin titulares cebo, sin anuncios, sin cookies y sin deporte**.

👉 **https://ansertoken.github.io/diario-paco/**

Cada dos horas, GitHub ejecuta `diario.py`, que:

1. Lee los canales RSS de los medios de `fuentes.json` (si un canal cambia de dirección, lo busca solo en la portada del medio).
2. Quita titulares cebo, publicidad, deporte, opinión, directos y noticias repetidas (si varios medios cuentan lo mismo, se ve una vez y debajo pone «También lo cuentan…»).
3. Ordena por secciones y publica páginas estáticas en GitHub Pages. Las noticias de **Gáldar y Barrial** salen arriba del todo, en «Desde Gáldar».

No hace falta ningún servidor ni pagar nada, y Paco no necesita a Claude para nada.

## Secciones y fuentes

| Sección | Fuentes |
|---|---|
| Gran Canaria y Canarias | Televisión Canaria (RTVC), Canarias Ahora, EFE Canarias, Europa Press Canarias, Infonorte Digital |
| España | EFE, RTVE, Europa Press, elDiario.es, Civio, Maldita.es |
| Mundo | EFE, RTVE, Europa Press, BBC News Mundo, France 24, DW |
| Ciencia y espacio | Agencia SINC, Instituto de Astrofísica de Canarias, Eureka (Daniel Marín), Europa Press Ciencia, CSIC, Naukas, The Conversation |
| Historia y arqueología | La Brújula Verde, Desperta Ferro, Historia National Geographic, El Museo Canario, Cueva Pintada de Gáldar, The Conversation |
| Música | Efe Eme, Ruta 66, Popular 1 |

Criterio: agencias de noticias, medios públicos, medios financiados por sus lectores, divulgación científica hecha por científicos y revistas especializadas. Los grandes diarios comerciales quedan fuera por los titulares cebo.

## Cómo cambiar cosas (desde la web de GitHub, sin instalar nada)

- **Quitar una fuente:** abre `fuentes.json`, pulsa el lápiz ✏️, pon `"activa": false` en su bloque y guarda («Commit changes»). A los pocos minutos la web se regenera.
- **Añadir una fuente:** copia un bloque, cambia el nombre, la sección y la dirección de su portada en `home` (el canal RSS se busca solo; si lo sabes, ponlo en `feeds`).
- **Más o menos noticias:** `max` en cada sección (total) y en cada fuente (máximo de esa fuente).
- **Actualizar ahora mismo:** pestaña **Actions** › **Diario de Paco** › **Run workflow**.
- **¿Qué fuentes fallan?** Abre `…/diario-paco/estado.html` (enlazado al final de la página de fuentes como «Informe técnico»). Ahí también se ven todos los titulares descartados y por qué, para ajustar los filtros.

Los filtros (palabras de cebo, deporte, opinión…) están al principio de `diario.py`.

## Puesta en marcha (una sola vez)

1. **Settings › Pages › Build and deployment › Source: GitHub Actions.**
2. Pestaña **Actions** › **Diario de Paco** › **Run workflow**. En un par de minutos la web está en la dirección de arriba.

El repositorio tiene que ser **público** para que GitHub Pages sea gratis. No contiene nada privado.

## La app de la tablet

`El Diario de Paco` (APK aparte, no va dentro de Crucigramas) abre esta web a pantalla completa, guarda la última edición para leerla sin conexión, y abre las noticias en **modo lectura**: sin JavaScript, sin cookies y bloqueando rastreadores, así que no salen avisos de cookies ni anuncios. Tiene botones para agrandar la letra, volver al diario y abrir la noticia en el navegador si alguna no se ve bien.

La clave para firmar la app **no está en este repositorio** (ni debe estarlo).

## Probar en local

```
python diario.py --out _site                          # con internet
python diario.py --muestras carpeta_xml --out _site   # sin internet, con canales de prueba
```

Solo usa la biblioteca estándar de Python 3.9+.

---
El tiempo: datos de [Open-Meteo](https://open-meteo.com/) (CC BY 4.0).
Letras: Lora y Poppins (SIL Open Font License).
