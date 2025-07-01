import { NextRequest, NextResponse } from 'next/server';
import { ScriptConfig } from '@/types/script-generator';
import { generateInstallScript, generateReadme } from '@/utils/script-generator';

export async function POST(request: NextRequest) {
  try {
    const config: ScriptConfig = await request.json();
    
    // Validate the configuration
    if (!config.os || !config.selectedApps || config.selectedApps.length === 0) {
      return NextResponse.json(
        { error: 'Invalid configuration: OS and selectedApps are required' },
        { status: 400 }
      );
    }

    // Generate the script and readme
    const script = generateInstallScript(config);
    const readme = generateReadme(config);

    return NextResponse.json({
      script,
      readme,
      filename: `install-script-${config.os}.sh`,
      readmeFilename: `README-${config.os}.md`
    });
  } catch (error) {
    console.error('Error generating script:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    message: 'Script Generator API',
    endpoints: {
      POST: '/api/generate-script - Generate installation script',
    },
    usage: 'Send a POST request with ScriptConfig in the body'
  });
}