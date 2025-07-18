import { ImageFile, ImageAnalysisResult, AIProviderConfig } from '@/types/image-analysis';

// Función para validar archivos de imagen
export function validateImageFile(file: File): { valid: boolean; error?: string } {
  const maxSize = 50 * 1024 * 1024; // 50MB
  const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/webp', 'image/bmp', 'image/tiff'];

  if (!allowedTypes.includes(file.type)) {
    return { 
      valid: false, 
      error: 'Tipo de archivo no soportado. Use: JPEG, PNG, WebP, BMP, TIFF' 
    };
  }

  if (file.size > maxSize) {
    return { 
      valid: false, 
      error: `Archivo muy grande. Máximo: ${formatFileSize(maxSize)}` 
    };
  }

  return { valid: true };
}

// Función para crear objeto ImageFile
export function createImageFile(file: File): ImageFile {
  return {
    id: `img_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    file,
    preview: URL.createObjectURL(file),
    filename: file.name,
    fileSize: file.size
  };
}

// Función para formatear tamaño de archivo
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 Bytes';
  
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Función para obtener dimensiones de imagen
export function getImageDimensions(file: File): Promise<{ width: number; height: number }> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);
    
    img.onload = () => {
      URL.revokeObjectURL(url);
      resolve({
        width: img.naturalWidth,
        height: img.naturalHeight
      });
    };
    
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error('No se pudieron obtener las dimensiones de la imagen'));
    };
    
    img.src = url;
  });
}

// Función para convertir imagen a base64
export function imageToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        resolve(reader.result);
      } else {
        reject(new Error('Error al convertir imagen a base64'));
      }
    };
    
    reader.onerror = () => reject(new Error('Error al leer el archivo'));
    reader.readAsDataURL(file);
  });
}

// Función para analizar imagen con IA local
export async function analyzeImageWithAI(
  imageFile: ImageFile,
  prompt: string,
  config: AIProviderConfig
): Promise<string> {
  try {
    // Convertir imagen a base64
    const base64Image = await imageToBase64(imageFile.file);
    
    // Configurar payload según el proveedor
    let payload: any;
    let endpoint: string;
    
    switch (config.provider) {
      case 'ollama':
        endpoint = `${config.endpoint}/api/generate`;
        payload = {
          model: config.model,
          prompt: prompt,
          images: [base64Image.split(',')[1]], // Remover data:image/...;base64,
          stream: false,
          options: {
            temperature: config.temperature || 0.1,
            num_predict: config.maxTokens || 4000
          }
        };
        break;
        
      case 'llamastudio':
        endpoint = `${config.endpoint}/v1/chat/completions`;
        payload = {
          model: config.model,
          messages: [
            {
              role: "user",
              content: [
                { type: "text", text: prompt },
                { type: "image_url", image_url: { url: base64Image } }
              ]
            }
          ],
          temperature: config.temperature || 0.1,
          max_tokens: config.maxTokens || 4000
        };
        break;
        
      case 'custom':
        endpoint = `${config.endpoint}/analyze`;
        payload = {
          model: config.model,
          image: base64Image,
          prompt: prompt,
          temperature: config.temperature || 0.1,
          max_tokens: config.maxTokens || 4000
        };
        break;
        
      default:
        throw new Error('Proveedor de IA no soportado');
    }

    // Realizar petición a la IA
    const response = await fetch(endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
      },
      body: JSON.stringify(payload)
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Error del servidor de IA: ${response.status} - ${errorText}`);
    }

    const result = await response.json();
    
    // Extraer respuesta según el proveedor
    switch (config.provider) {
      case 'ollama':
        return result.response || 'No se recibió respuesta de Ollama';
        
      case 'llamastudio':
        return result.choices?.[0]?.message?.content || 'No se recibió respuesta de LM Studio';
        
      case 'custom':
        return result.analysis || result.response || result.content || 'No se recibió respuesta del servidor personalizado';
        
      default:
        return 'Respuesta no procesable';
    }
    
  } catch (error) {
    console.error('Error analyzing image:', error);
    
    if (error instanceof TypeError && error.message.includes('fetch')) {
      throw new Error('No se pudo conectar con el servidor de IA. Verifica que esté ejecutándose.');
    }
    
    throw error;
  }
}

// Función para verificar conectividad con el servidor de IA
export async function testAIConnection(config: AIProviderConfig): Promise<{ connected: boolean; error?: string }> {
  try {
    let testEndpoint: string;
    
    switch (config.provider) {
      case 'ollama':
        testEndpoint = `${config.endpoint}/api/tags`;
        break;
      case 'llamastudio':
        testEndpoint = `${config.endpoint}/v1/models`;
        break;
      case 'custom':
        testEndpoint = `${config.endpoint}/health`;
        break;
      default:
        return { connected: false, error: 'Proveedor no soportado' };
    }

    const response = await fetch(testEndpoint, {
      method: 'GET',
      headers: {
        ...(config.apiKey && { 'Authorization': `Bearer ${config.apiKey}` })
      }
    });

    if (response.ok) {
      return { connected: true };
    } else {
      return { connected: false, error: `Error ${response.status}: ${response.statusText}` };
    }
    
  } catch (error) {
    return { 
      connected: false, 
      error: error instanceof Error ? error.message : 'Error de conexión desconocido' 
    };
  }
}

// Función para descargar resultados como CSV
export function downloadResultsAsCSV(results: ImageAnalysisResult[]): void {
  const headers = ['Filename', 'File Size', 'Dimensions', 'Processing Time', 'Analysis', 'Timestamp'];
  
  const csvContent = [
    headers.join(','),
    ...results.map(result => [
      `"${result.filename}"`,
      `"${formatFileSize(result.fileSize)}"`,
      `"${result.dimensions.width}x${result.dimensions.height}"`,
      `"${result.processingTime ? result.processingTime.toFixed(2) + 's' : 'N/A'}"`,
      `"${result.analysis.replace(/"/g, '""')}"`, // Escapar comillas
      `"${new Date(result.timestamp).toLocaleString()}"`
    ].join(','))
  ].join('\n');

  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement('a');
  link.href = url;
  link.download = `image-analysis-results-${Date.now()}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  
  URL.revokeObjectURL(url);
}

// Función para descargar resultados como JSON
export function downloadResultsAsJSON(results: ImageAnalysisResult[]): void {
  const jsonContent = JSON.stringify(results, null, 2);
  const blob = new Blob([jsonContent], { type: 'application/json;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  
  const link = document.createElement('a');
  link.href = url;
  link.download = `image-analysis-results-${Date.now()}.json`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  
  URL.revokeObjectURL(url);
}