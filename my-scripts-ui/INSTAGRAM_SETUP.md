# 📸 Configuración del Instagram Scraper Real

## 🎯 Resumen
Esta guía te explica paso a paso cómo configurar tu aplicación para usar la API oficial de Instagram y obtener fotos reales de perfiles.

## 🚨 Limitaciones importantes
- **Solo tu propio perfil**: La API de Instagram Basic Display solo permite acceder a tu propia cuenta
- **Perfiles autorizados**: Los usuarios deben autorizar explícitamente tu app
- **No scraping público**: No es posible scrapear perfiles públicos sin autorización
- **Términos de servicio**: Siempre respeta los términos de Instagram

## 📋 Opción 1: Instagram Basic Display API (Oficial - Recomendado)

### Paso 1: Crear aplicación en Facebook/Meta Developers

1. **Ve a Facebook Developers**
   - Visita: https://developers.facebook.com/
   - Inicia sesión con tu cuenta de Facebook

2. **Crear nueva aplicación**
   - Haz clic en "My Apps" → "Create App"
   - Selecciona "Consumer" como tipo de aplicación
   - Completa la información:
     ```
     App Name: My Scripts UI Instagram
     App Contact Email: tu-email@ejemplo.com
     App Purpose: Personal use
     ```

### Paso 2: Configurar Instagram Basic Display

1. **Añadir el producto Instagram**
   - En tu app, ve a "Add Products"
   - Busca "Instagram Basic Display"
   - Haz clic en "Set Up"

2. **Crear Instagram App**
   - Ve a "Basic Display" en el menú lateral
   - Haz clic en "Create New App"
   - Acepta los términos y condiciones

### Paso 3: Configurar URLs y permisos

1. **OAuth Redirect URIs**
   ```
   Desarrollo: http://localhost:3000/api/auth/instagram/callback
   Producción: https://tudominio.com/api/auth/instagram/callback
   ```

2. **Deauthorize Callback URL**
   ```
   https://tudominio.com/api/auth/instagram/deauth
   ```

3. **Data Deletion Request URL**
   ```
   https://tudominio.com/api/auth/instagram/delete
   ```

### Paso 4: Obtener credenciales

1. **Copia las credenciales**
   - Instagram App ID
   - Instagram App Secret
   - Guárdalas de forma segura

### Paso 5: Configurar variables de entorno

1. **Crear archivo .env.local**
   ```bash
   cp .env.example .env.local
   ```

2. **Completar las variables**
   ```env
   INSTAGRAM_APP_ID=tu_instagram_app_id_aqui
   INSTAGRAM_APP_SECRET=tu_instagram_app_secret_aqui
   INSTAGRAM_REDIRECT_URI=http://localhost:3000/api/auth/instagram/callback
   NEXTAUTH_URL=http://localhost:3000
   NEXTAUTH_SECRET=genera_un_secret_aleatorio_aqui
   ```

### Paso 6: Añadir usuarios de prueba

1. **Ir a Roles**
   - En tu app, ve a "Roles" → "Roles"
   - Haz clic en "Add Instagram Testers"

2. **Añadir cuentas**
   - Añade las cuentas de Instagram que quieres usar
   - Los usuarios deben aceptar la invitación en Instagram

### Paso 7: Probar la integración

1. **Iniciar servidor de desarrollo**
   ```bash
   bun dev
   ```

2. **Ir a la página de Instagram**
   - Visita: http://localhost:3000/instagram-photos
   - Haz clic en "Conectar con Instagram"
   - Autoriza la aplicación

## 📋 Opción 2: Scraping No Oficial (NO RECOMENDADO)

### ⚠️ ADVERTENCIAS
- **Viola términos de servicio** de Instagram
- **Riesgo de bloqueo** de IP o cuenta
- **Posibles acciones legales**
- **Puede dejar de funcionar** en cualquier momento

### Implementación con Puppeteer (Solo para referencia educativa)

```typescript
// SOLO PARA FINES EDUCATIVOS - NO USAR EN PRODUCCIÓN
import puppeteer from 'puppeteer';

async function scrapeInstagramProfile(username: string) {
  const browser = await puppeteer.launch({ headless: true });
  const page = await browser.newPage();
  
  try {
    // Configurar user agent
    await page.setUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36');
    
    // Navegar al perfil
    await page.goto(`https://instagram.com/${username}`);
    
    // Esperar y extraer datos
    await page.waitForSelector('article img', { timeout: 10000 });
    
    const photos = await page.evaluate(() => {
      const images = Array.from(document.querySelectorAll('article img'));
      return images.map(img => ({
        url: img.src,
        alt: img.alt
      }));
    });
    
    return photos;
    
  } catch (error) {
    throw new Error('Error scraping profile');
  } finally {
    await browser.close();
  }
}
```

## 🔧 Instalación de dependencias adicionales

Si eliges la opción no oficial (no recomendado):

```bash
bun add puppeteer
bun add @types/puppeteer --dev
```

## 📝 Notas importantes

### Para desarrollo local:
- Usa `http://localhost:3000` en todas las URLs
- Los certificados SSL no son necesarios para desarrollo

### Para producción:
- Usa HTTPS obligatoriamente
- Actualiza todas las URLs a tu dominio real
- Configura las variables de entorno en tu plataforma de hosting

### Limitaciones de la API oficial:
- Solo 200 solicitudes por hora por usuario
- Máximo 50 medios por solicitud
- Token expira cada 60 días (renovable)

## 🚀 Próximos pasos

1. **Configurar la aplicación** siguiendo los pasos de la Opción 1
2. **Probar con tu cuenta** de Instagram
3. **Solicitar revisión** si planeas usar en producción con muchos usuarios
4. **Implementar renovación** automática de tokens

## 📞 Soporte

Si tienes problemas:
1. Verifica que todas las URLs estén correctamente configuradas
2. Asegúrate de que las variables de entorno sean correctas
3. Revisa que el usuario esté en la lista de testers
4. Consulta la documentación oficial de Instagram Basic Display API

## 🔗 Enlaces útiles

- [Instagram Basic Display API Docs](https://developers.facebook.com/docs/instagram-basic-display-api)
- [Facebook App Dashboard](https://developers.facebook.com/apps/)
- [Instagram API Testing](https://developers.facebook.com/docs/instagram-basic-display-api/guides/getting-started#step-4--add-an-instagram-test-user)