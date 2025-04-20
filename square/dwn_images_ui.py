import os
from dotenv import load_dotenv
from pathlib import Path
import requests
from square.client import Client
from PIL import Image
import io
import re
import flet as ft
import threading

def main(page: ft.Page):
    # Get the current directory of the script
    script_dir = Path(__file__).resolve().parent

    # Get the parent directory (where .env is located)
    parent_dir = script_dir.parent
    
    # Load environment variables from .env file if exists
    env_file = parent_dir / '.env'
    if env_file.exists():
        load_dotenv(env_file)
        token_value = os.getenv('SQUARE_ACCESS_TOKEN', '')
    else:
        token_value = ''
    
    # Create directory for images if it doesn't exist
    images_dir = parent_dir / 'product_images'
    if not images_dir.exists():
        images_dir.mkdir(parents=True)
    
    # UI components
    page.title = "Descargador de Imágenes Square"
    
    token_input = ft.TextField(
        label="Token de Square",
        value=token_value,
        password=True,
        can_reveal_password=True,
        width=600
    )
    
    progress_bar = ft.ProgressBar(width=600, visible=False)
    status_text = ft.Text("Estado: Listo para descargar", size=16)
    
    download_logs = ft.ListView(
        expand=True,
        spacing=10,
        auto_scroll=True,
        height=400,
        width=600
    )
    
    def add_log_entry(message, color="black"):
        download_logs.controls.append(ft.Text(message, color=color))
        page.update()
    
    def update_progress(value, max_value):
        progress_bar.value = value / max_value
        page.update()
    
    def download_images():
        # Reset UI
        download_logs.controls.clear()
        progress_bar.visible = True
        progress_bar.value = 0
        status_text.value = "Estado: Conectando con Square..."
        page.update()
        
        # Get token
        square_token = token_input.value
        
        if not square_token:
            status_text.value = "Estado: Error - Token no proporcionado"
            progress_bar.visible = False
            page.update()
            return
        
        try:
            # Create Square client
            client = Client(
                access_token=square_token,
                environment='production'
            )
            
            # First fetch - get all food and beverage items
            add_log_entry("Buscando productos de comida y bebida...")
            items_result = client.catalog.search_catalog_items(
                body={
                    "product_types": [
                        "FOOD_AND_BEV"
                    ]
                }
            )
            
            # Second fetch - get all images
            add_log_entry("Buscando todas las imágenes...")
            images_result = client.catalog.search_catalog_objects(
                body={
                    "object_types": [
                        "IMAGE"
                    ],
                    "include_deleted_objects": False,
                    "include_related_objects": False,
                    "include_category_path_to_root": False
                }
            )
            
            if items_result.is_success() and images_result.is_success():
                # Create a dictionary of image_id to image_url
                image_map = {
                    img['id']: img['image_data']['url']
                    for img in images_result.body['objects']
                }
                
                items = items_result.body['items']
                total_items = len(items)
                processed_items = 0
                
                add_log_entry(f"Encontrados {total_items} productos para procesar")
                status_text.value = f"Estado: Descargando {total_items} productos..."
                
                # Process each item
                for item in items:
                    # Get the item name and image IDs
                    item_name = item['item_data']['name']
                    image_ids = item['item_data'].get('image_ids', [])
                    
                    if not image_ids:
                        add_log_entry(f"El producto '{item_name}' no tiene imágenes asociadas", "orange")
                    
                    # Process each image ID for this item
                    for img_id in image_ids:
                        if img_id in image_map:
                            # Get the image URL
                            image_url = image_map[img_id]
                            
                            try:
                                # Download the image
                                add_log_entry(f"Descargando imagen para '{item_name}'...", "blue")
                                response = requests.get(image_url)
                                response.raise_for_status()  # Raise an exception for bad status codes
                                
                                # Open the image with Pillow
                                img = Image.open(io.BytesIO(response.content))
                                
                                # Create safe filename
                                safe_name = re.sub(r'[<>:"/\\|?*\'&,!@#$%^()+={}[\]~`]+', '', item_name)
                                safe_name = re.sub(r'\s+', '_', safe_name)
                                webp_filename = images_dir / f'{safe_name}.webp'
                                
                                # Convert and save as WebP
                                img.save(str(webp_filename), 'WEBP', quality=85)
                                add_log_entry(f"✅ Imagen guardada como: {webp_filename.name}", "green")
                                
                            except requests.RequestException as e:
                                add_log_entry(f"❌ Error al descargar imagen para '{item_name}': {e}", "red")
                            except Exception as e:
                                add_log_entry(f"❌ Error al procesar imagen para '{item_name}': {e}", "red")
                        else:
                            add_log_entry(f"⚠️ ID de imagen {img_id} no encontrado para '{item_name}'", "orange")
                    
                    processed_items += 1
                    update_progress(processed_items, total_items)
                
                status_text.value = f"Estado: ¡Completado! Se procesaron {total_items} productos."
                add_log_entry("\nArchivos creados en:", "green")
                add_log_entry(str(images_dir), "green")
                
                # List created files
                file_count = 0
                for file in images_dir.glob('*.webp'):
                    add_log_entry(f"- {file.name}", "blue")
                    file_count += 1
                
                add_log_entry(f"\nTotal de archivos creados: {file_count}", "green")
                
            else:
                if items_result.is_error():
                    error_msg = "Error obteniendo productos: " + str(items_result.errors)
                    add_log_entry(error_msg, "red")
                    status_text.value = "Estado: Error obteniendo productos"
                
                if images_result.is_error():
                    error_msg = "Error obteniendo imágenes: " + str(images_result.errors)
                    add_log_entry(error_msg, "red")
                    status_text.value = "Estado: Error obteniendo imágenes"
        
        except Exception as e:
            error_msg = f"Error general: {e}"
            add_log_entry(error_msg, "red")
            status_text.value = "Estado: Error en el proceso"
        
        # Reset progress bar
        progress_bar.visible = False
        page.update()
    
    def start_download(_):
        # Run the download function in a separate thread to avoid blocking the UI
        threading.Thread(target=download_images).start()
    
    # Corregido para evitar el uso de MaterialState que causaba el error
    download_button = ft.ElevatedButton(
        "Descargar Imágenes", 
        on_click=start_download, 
        color=ft.colors.WHITE,
        bgcolor=ft.colors.BLUE,
        width=200,
        height=50
    )
    
    # Add all components to the page
    page.add(
        ft.Column([
            ft.Text("Descarga de Imágenes de Square", size=24, weight=ft.FontWeight.BOLD),
            ft.Text("Ingresa tu token de acceso y haz clic en 'Descargar Imágenes'", size=16),
            ft.Container(height=20),
            token_input,
            ft.Container(height=20),
            download_button,
            ft.Container(height=20),
            status_text,
            ft.Container(height=10),
            progress_bar,
            ft.Container(height=20),
            ft.Text("Registro de actividad:", size=16, weight=ft.FontWeight.BOLD),
            download_logs,
        ], alignment=ft.MainAxisAlignment.START, horizontal_alignment=ft.CrossAxisAlignment.CENTER)
    )

if __name__ == '__main__':
    ft.app(target=main)