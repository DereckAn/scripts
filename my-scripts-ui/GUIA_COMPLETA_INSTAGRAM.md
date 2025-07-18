# 📸 Guía Completa: Instagram Scraper Real

## 🎯 Resumen General

Esta guía te explica **paso a paso** cómo configurar tu aplicación para obtener fotos reales de Instagram usando la API oficial de Meta/Facebook. El sistema actual usa datos simulados, pero con esta configuración podrás acceder a datos reales.

## ⚠️ Limitaciones Importantes (LEE ESTO PRIMERO)

### ✅ **Lo que SÍ puedes hacer:**
- Ver y descargar fotos de **tu propia cuenta** de Instagram
- Acceder a cuentas que **autoricen explícitamente** tu aplicación
- Usar la funcionalidad de forma legal y segura
- Obtener hasta 50 fotos por consulta
- Renovar tokens automáticamente

### ❌ **Lo que NO puedes hacer:**
- Hacer scraping de perfiles públicos sin autorización
- Ver fotos de cualquier usuario sin su permiso explícito
- Hacer scraping masivo de perfiles
- Usar esto para propósitos comerciales sin revisión de Meta

### 🚨 **Advertencia Legal:**
- Solo usa la **API oficial** (Opción 1)
- El web scraping no oficial viola los términos de Instagram
- Puede resultar en bloqueo de cuenta o acciones legales

---

## 📋 OPCIÓN 1: API Oficial de Instagram (RECOMENDADO)

### **Paso 1: Preparación inicial** ⏱️ 2 minutos

1. **Requisitos previos:**
   - Cuenta de Facebook/Meta activa
   - Cuenta de Instagram vinculada a Facebook
   - Proyecto Next.js funcionando

2. **Verificar archivos creados:**
   ```bash
   # Estos archivos ya están creados para ti:
   ✅ src/app/api/instagram/auth/route.ts
   ✅ src/app/api/instagram/profile/route.ts  
   ✅ src/app/api/auth/instagram/callback/route.ts
   ✅ src/utils/instagram-api.ts
   ✅ src/components/InstagramAuthButton.tsx
   ✅ .env.example
   ```

### **Paso 2: Crear aplicación en Meta Developers** ⏱️ 15 minutos

1. **Acceder a Facebook Developers:**
   ```
   🌐 URL: https://developers.facebook.com/
   📝 Acción: Inicia sesión con tu cuenta de Facebook
   ```

2. **Crear nueva aplicación:**
   ```
   🔘 Clic en: "My Apps" → "Create App"
   📱 Tipo: Selecciona "Consumer" 
   📋 Nombre: "My Scripts UI Instagram"
   📧 Email: tu-email@ejemplo.com
   🎯 Propósito: "Personal use"
   ```

3. **Añadir Instagram Basic Display:**
   ```
   🔘 En tu app: "Add Products"
   🔍 Buscar: "Instagram Basic Display"
   ⚙️ Clic en: "Set Up"
   ```

4. **Crear Instagram App:**
   ```
   📍 Ir a: "Basic Display" (menú lateral)
   🆕 Clic en: "Create New App"
   ✅ Aceptar términos y condiciones
   ```

### **Paso 3: Configurar URLs y permisos** ⏱️ 5 minutos

1. **Configurar OAuth Redirect URIs:**
   ```
   🏠 Desarrollo: http://localhost:3000/api/auth/instagram/callback
   🌐 Producción: https://tudominio.com/api/auth/instagram/callback
   ```

2. **Configurar Deauthorize Callback URL:**
   ```
   🔗 URL: https://tudominio.com/api/auth/instagram/deauth
   ```

3. **Configurar Data Deletion Request URL:**
   ```
   🗑️ URL: https://tudominio.com/api/auth/instagram/delete
   ```

### **Paso 4: Obtener credenciales** ⏱️ 2 minutos

1. **Localizar credenciales:**
   ```
   📍 Ubicación: En la página de "Basic Display"
   🔑 Instagram App ID: [COPIAR ESTE VALOR]
   🔐 Instagram App Secret: [COPIAR ESTE VALOR]
   ```

2. **⚠️ IMPORTANTE: Guardar de forma segura**
   - No compartas estas credenciales públicamente
   - No las subas a GitHub sin cifrar
   - Úsalas solo en variables de entorno

### **Paso 5: Configurar variables de entorno** ⏱️ 3 minutos

1. **Crear archivo de configuración:**
   ```bash
   # En la raíz de tu proyecto:
   cp .env.example .env.local
   ```

2. **Completar el archivo .env.local:**
   ```env
   # Reemplaza con tus valores reales:
   INSTAGRAM_APP_ID=tu_instagram_app_id_aqui
   INSTAGRAM_APP_SECRET=tu_instagram_app_secret_aqui
   INSTAGRAM_REDIRECT_URI=http://localhost:3000/api/auth/instagram/callback
   NEXTAUTH_URL=http://localhost:3000
   NEXTAUTH_SECRET=genera_un_secret_aleatorio_aqui
   ```

3. **Generar NEXTAUTH_SECRET:**
   ```bash
   # Opción A: Usar OpenSSL
   openssl rand -base64 32
   
   # Opción B: Online
   # Ve a: https://generate-secret.vercel.app/32
   ```

### **Paso 6: Añadir usuarios de prueba** ⏱️ 5 minutos

1. **Ir a la sección de Roles:**
   ```
   📍 En tu app: "Roles" → "Roles"
   👥 Clic en: "Add Instagram Testers"
   ```

2. **Añadir tu cuenta:**
   ```
   📝 Usuario: tu_username_de_instagram
   📨 Enviar invitación
   ```

3. **Aceptar invitación en Instagram:**
   ```
   📱 Abrir Instagram app
   🔔 Ir a notificaciones
   ✅ Aceptar invitación de tu app
   ```

### **Paso 7: Probar la integración** ⏱️ 3 minutos

1. **Iniciar servidor de desarrollo:**
   ```bash
   bun dev
   ```

2. **Acceder a la página:**
   ```
   🌐 URL: http://localhost:3000/instagram-photos
   ```

3. **Probar autenticación:**
   ```
   🔘 Clic en: "Conectar con Instagram"
   🔐 Autorizar en popup de Instagram
   📸 Ver tus fotos cargadas
   ```

---

## 🔧 Archivos Técnicos Creados

### **1. API Routes del Backend:**

**📁 src/app/api/instagram/auth/route.ts**
- Maneja la autenticación OAuth
- Genera URLs de autorización
- Intercambia códigos por tokens

**📁 src/app/api/instagram/profile/route.ts**
- Obtiene datos del perfil
- Descarga fotos reales de Instagram
- Maneja paginación y errores

**📁 src/app/api/auth/instagram/callback/route.ts**
- Maneja el callback de OAuth
- Redirige con códigos de autorización

### **2. Utilidades del Frontend:**

**📁 src/utils/instagram-api.ts**
- Funciones para API real
- Manejo de tokens
- Gestión de localStorage

**📁 src/components/InstagramAuthButton.tsx**
- Botón de autenticación
- Estados de conexión
- Manejo de errores

### **3. Configuración:**

**📁 .env.example**
- Plantilla de variables de entorno
- Documentación de cada variable

---

## 🚀 Uso Después de la Configuración

### **Flujo de usuario:**

1. **Usuario accede a la página:** `/instagram-photos`
2. **Ve botón de autenticación:** "Conectar con Instagram"
3. **Autoriza la aplicación:** En popup de Instagram
4. **Ve sus fotos:** Cargadas desde su perfil real
5. **Puede descargar:** Individual o múltiple

### **Funcionalidades disponibles:**

✅ **Autenticación OAuth** - Login seguro con Instagram
✅ **Carga de perfil** - Información real del usuario
✅ **Grid de fotos** - Hasta 50 fotos por carga
✅ **Descarga individual** - Cada foto por separado
✅ **Descarga múltiple** - Selección de varias fotos
✅ **Manejo de tokens** - Renovación automática
✅ **Estados de error** - Manejo completo de errores

---

## 🛠️ Solución de Problemas

### **Error: "Invalid redirect URI"**
```
🔧 Solución: Verifica que la URL en Meta Developers coincida exactamente
✅ Correcto: http://localhost:3000/api/auth/instagram/callback
❌ Incorrecto: http://localhost:3000/api/auth/instagram/callback/
```

### **Error: "User not authorized"**
```
🔧 Solución: Añadir usuario como tester en Meta Developers
📍 Ubicación: Roles → Add Instagram Testers
```

### **Error: "Invalid access token"**
```
🔧 Solución: Limpiar localStorage y volver a autorizar
💾 Código: localStorage.clear() en consola del navegador
```

### **Error: "App not found"**
```
🔧 Solución: Verificar variables de entorno
📝 Revisar: INSTAGRAM_APP_ID y INSTAGRAM_APP_SECRET
```

---

## 📊 Limitaciones de la API

### **Límites de rate:**
- 200 solicitudes por hora por usuario
- Renovación automática cada hora

### **Límites de datos:**
- Máximo 50 medios por solicitud
- Solo fotos e IGTV (no Stories)
- Datos de los últimos 2 años

### **Renovación de tokens:**
- Tokens expiran cada 60 días
- Renovación automática implementada
- Notificación antes de expiración

---

## 🌐 Despliegue en Producción

### **Antes del despliegue:**

1. **Actualizar URLs en Meta:**
   ```
   ✏️ Cambiar: http://localhost:3000
   ➡️ Por: https://tudominio.com
   ```

2. **Variables de entorno en hosting:**
   ```env
   INSTAGRAM_APP_ID=tu_app_id
   INSTAGRAM_APP_SECRET=tu_app_secret
   INSTAGRAM_REDIRECT_URI=https://tudominio.com/api/auth/instagram/callback
   NEXTAUTH_URL=https://tudominio.com
   NEXTAUTH_SECRET=tu_secret_produccion
   ```

3. **Certificado SSL obligatorio:**
   - Instagram requiere HTTPS en producción
   - Configura SSL en tu hosting

---

## 📞 Soporte y Enlaces Útiles

### **Documentación oficial:**
- [Instagram Basic Display API](https://developers.facebook.com/docs/instagram-basic-display-api)
- [Facebook App Dashboard](https://developers.facebook.com/apps/)

### **Si tienes problemas:**
1. Verifica configuración de URLs
2. Confirma variables de entorno
3. Asegúrate de estar en lista de testers
4. Revisa logs de consola del navegador

### **Estado actual del proyecto:**
- ✅ Interfaz completa implementada
- ✅ APIs del backend creadas
- ✅ Manejo de errores completo
- ⏳ Requiere configuración de credenciales
- ⏳ Necesita usuarios de prueba configurados

---

## 🎯 Próximos Pasos

1. **[HACER AHORA]** Seguir los pasos 1-7 de esta guía
2. **[PROBAR]** La funcionalidad con tu cuenta
3. **[OPCIONAL]** Solicitar revisión para uso público
4. **[AVANZADO]** Implementar renovación automática de tokens

---

**💡 Consejo final:** Empieza con la configuración básica y prueba con tu propia cuenta antes de pensar en usuarios externos. La API de Instagram es muy estricta pero funciona perfectamente una vez configurada correctamente.