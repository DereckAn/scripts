"""Exercise the actual shared browser converter: .venv/bin/python -m unittest test_svg_import"""
import base64
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
import unittest

import pymupdf
from playwright.sync_api import sync_playwright


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.end_headers()
            self.wfile.write(b'<html><body></body></html>')
        else:
            super().do_GET()


class SvgImportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0),
                                        partial(Handler, directory=str(Path(__file__).parent / 'web')))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def convert(self, inputs):
        page = self.browser.new_page()
        try:
            page.goto(f'http://127.0.0.1:{self.server.server_port}/')
            return page.evaluate('''async inputs => {
              const {svgSheetsToPdf} = await import('/vendor/score-pdf-bridge.js');
              try {
                const files = inputs.map(i => new File([i.content], i.name, {type:'image/svg+xml'}));
                const pdf = await svgSheetsToPdf(files);
                const bytes = new Uint8Array(await pdf.arrayBuffer());
                let binary = ''; for (const byte of bytes) binary += String.fromCharCode(byte);
                return {pdf:btoa(binary), executed:window.svgExecuted || false};
              } catch (error) { return {error:error.message}; }
            }''', inputs)
        finally:
            page.close()

    def test_natural_order_page_sizes_vectors_and_safe_local_references(self):
        svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="{width}px" height="200px"
                  onload="window.svgExecuted=true">
          <script>window.svgExecuted=true</script>
          <defs><path id="head" d="M 60 80 L 90 80 L 90 90 Z"/>
            <clipPath id="clip"><rect width="100" height="100"/></clipPath></defs>
          <g style="clip-path: url( #clip )"><use href="#head"/></g>
          <text x="20" y="30" font-family="Helvetica">{name}</text>
        </svg>'''
        result = self.convert([{'name': 'page-10.svg', 'content': svg.format(width=400, name='Page Ten')},
                               {'name': 'page-2.svg', 'content': svg.format(width=300, name='Page Two')}])
        self.assertNotIn('error', result, result)
        self.assertFalse(result['executed'])
        with pymupdf.open(stream=base64.b64decode(result['pdf']), filetype='pdf') as pdf:
            self.assertEqual(len(pdf), 2)
            self.assertAlmostEqual(pdf[0].rect.width, 225, places=2)
            self.assertAlmostEqual(pdf[1].rect.width, 300, places=2)
            self.assertAlmostEqual(pdf[0].rect.height, 150, places=2)
            self.assertIn('Page Two', pdf[0].get_text())
            self.assertIn('Page Ten', pdf[1].get_text())
            self.assertTrue(pdf[0].get_drawings(), 'Vector artwork must survive conversion')

    def test_invalid_and_external_svg_inputs_fail_cleanly(self):
        for content in ['<invalid/>', '<svg',
                        '<svg xmlns="http://www.w3.org/2000/svg"><use href="https://example.com/score.svg#head"/></svg>']:
            result = self.convert([{'name': 'bad.svg', 'content': content}])
            self.assertIn('error', result)


if __name__ == '__main__':
    unittest.main()
