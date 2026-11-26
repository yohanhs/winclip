# vertical-reframe Specification

## Purpose
Transforma fragmentos de video a relación de aspecto vertical 9:16 (1080x1920) manteniendo enfocado al hablante de forma estable o aplicando encuadres manuales, con fondo desenfocado o sin recorte si la fuente ya es vertical.

## Requirements

### Requirement: Seguimiento facial suavizado en modo face
El sistema SHALL analizar el fragmento de video muestreando entre 2 y 4 fotogramas por segundo en modo `face`, calcular una trayectoria horizontal suavizada con límite de velocidad de paneo y producir la lista de puntos normalizados `[t, x_norm]` dentro de `[0.0, 1.0]`.

#### Scenario: Rostro en movimiento continuo
- **WHEN** se reencuadra en modo `face` un fragmento horizontal donde una persona se desplaza lateralmente
- **THEN** la ventana de recorte 9:16 sigue la posición horizontal del rostro con cambios progresivos sin saltos bruscos ni superar la velocidad máxima de paneo

#### Scenario: Micro-movimientos del hablante
- **WHEN** el rostro oscila menos de un pequeño umbral lateral alrededor de la misma posición
- **THEN** la trayectoria amortigua el temblor evitando vibraciones perceptibles en el encuadre final

#### Scenario: Límites del fotograma fuente
- **WHEN** el rostro se sitúa cerca del borde izquierdo o derecho del video original
- **THEN** la ventana de recorte queda acotada dentro de los límites del fotograma sin generar bandas negras laterales

### Requirement: Detección de cambio de plano
El sistema SHALL detectar cortes bruscos de cámara durante el análisis en modo `face` y reiniciar el suavizado en cada nuevo plano para encuadrar de inmediato al hablante visible tras el corte.

#### Scenario: Corte entre dos planos con hablantes en lados opuestos
- **WHEN** el fragmento cambia abruptamente de un plano con el hablante a la izquierda a otro con el hablante a la derecha
- **THEN** la trayectoria salta directamente a la nueva posición en el instante del corte en lugar de realizar un paneo lento sobre el cambio de plano

### Requirement: Respaldo automático sin rostros
El sistema SHALL aplicar un respaldo automático al encuadre centrado cuando en modo `face` no se detecten rostros en un plano o en la totalidad del fragmento.

#### Scenario: Fragmento sin rostros detectables
- **WHEN** se ejecuta el reencuadre en modo `face` sobre un fragmento sin personas visibles (por ejemplo, diapositivas o paisaje)
- **THEN** el sistema completa el reencuadre centrando la ventana horizontal en `0.5` sin fallar

### Requirement: Modo center con ajustes manuales
El sistema SHALL ofrecer el modo `center` con recorte estático centrado por defecto y parámetros opcionales `crop_x_pct`, `crop_y_pct` y `zoom_pct` para desplazar la ventana y acercar el encuadre.

#### Scenario: Recorte centrado por defecto
- **WHEN** se selecciona el modo `center` sin overrides de posición ni zoom
- **THEN** el recorte toma la región 9:16 centrada horizontal y verticalmente (`crop_x_pct=50`, `crop_y_pct=50`, `zoom_pct=100`) y la escala a `1080x1920`

#### Scenario: Recorte desplazado con zoom
- **WHEN** se selecciona el modo `center` con `crop_x_pct=30`, `crop_y_pct=40` y `zoom_pct=125`
- **THEN** el encuadre refleja el desplazamiento y el acercamiento solicitados respetando los límites del fotograma fuente

#### Scenario: Parámetros de recorte fuera de rango
- **WHEN** se proporcionan valores inválidos como `crop_x_pct` fuera de `[0, 100]` o `zoom_pct` menor que `100`
- **THEN** el sistema rechaza la configuración antes de iniciar el renderizado con un mensaje de error claro

### Requirement: Modo blur sobre fondo desenfocado
El sistema SHALL ofrecer el modo `blur` que conserva íntegro el cuadro original sin recortar sus laterales, centrado verticalmente sobre una copia ampliada, desenfocada y atenuada del mismo video a `1080x1920`.

#### Scenario: Video horizontal en modo blur
- **WHEN** se renderiza un video 16:9 en modo `blur`
- **THEN** el cuadro completo del video original se muestra centrado a lo ancho de `1080` píxeles y las zonas superior e inferior se rellenan con la versión desenfocada del propio video

### Requirement: Preservación de fuentes ya verticales
El sistema SHALL detectar automáticamente cuando el video de entrada ya posee orientación vertical 9:16 y evitar cualquier recorte horizontal, limitándose a escalar a `1080x1920` si la resolución difiere.

#### Scenario: Video origen vertical 1080x1920 o 720x1280
- **WHEN** el usuario solicita modo `face` o `center` sobre un video origen con relación de aspecto 9:16
- **THEN** el sistema omite el análisis de recorte lateral, conserva el encuadre íntegro escalado a `1080x1920` y registra en `render.json` que no se aplicó recorte horizontal
