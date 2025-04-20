# Download images from Square

## Prerequisites

- Agregar la clave de acceso a la variable de entorno `SQUARE_ACCESS_TOKEN` en el archivo `.env`
- Activar el ambiente virtual
- Instalar las dependencias con `pip`. Solo si es necesario.
- Puse los paquetes que tenemos que installar en el archivo `requirements.txt`
- Hay muchos problemas a la hora de crear el script, si no funciona en el futuro, no es de gran importancia.
- Esperar mucho tiempo. Aproximadamente como 15 min. Porque esta descargando las imagenes de square.

## Instrucciones

1. Correr el entorno virtual con `source myenv/bin/activate` o `myenv\Scripts\activate`
2. Ejecutar el script con `python square/download_square_images.py`
3. El script creará un directorio llamado `product_images` en el directorio raíz del proyecto.

## Proposito

Este script es hace dos llamdas a la API de Square, una para obtener todos los productos de tipo `FOOD_AND_BEV` y otra para obtener todas las imágenes de esos productos. Luego, se procesa cada producto y se descarga la imagen correspondiente.
Se comparan los IDs de las imágenes con los IDs de los productos para asegurarse de que se está descargando la imagen correcta.
Despues de descargar la imagen, se convierte a WebP y se guarda en el directorio `product_images`.

# Recuerda que tarda mucho tiempo en descargar las imágenes de square, por lo que es recomendable que se ejecute este script cada vez que se agregue una nueva imagen a square.