#!/usr/bin/env node
/**
 * pdf_runner.js — dynamic PDF JS layer (PDF.js + Node vm sandbox)
 *
 * Mission: execute the JavaScript embedded in a PDF in an environment where
 * strace can observe the resulting syscalls.
 *
 * Strategy:
 *   1. Load the PDF with pdfjs-dist (Mozilla parser — robust on malformed PDFs)
 *   2. Extract ALL the JS blocks:
 *        - /OpenAction and /AA at the document level
 *        - /AA per page
 *        - /A and /AA in the annotations (form fields, links, etc.)
 *        - /JavaScript in the names (/Names tree)
 *   3. Execute each block in a sandboxed Node vm with a stubbed Adobe-like
 *      context. The stubbed APIs that do network/disk I/O trigger REAL syscalls
 *      visible to strace.
 *
 * Why vm + stubs rather than PDF.js's native sandbox?
 *   - PDF.js sandbox uses QuickJS via WebAssembly → syscalls buried in wasm
 *   - Node vm is direct V8 → clear, attributable syscalls
 *   - We control which APIs trigger what (fine granularity for detection)
 *
 * Output: stdout = JSON events (one per line) for debug.
 *         stderr = execution traces.
 *         All suspicious behaviour goes through real syscalls that strace -f
 *         intercepts upstream.
 *
 * Usage: node pdf_runner.js <path-to-pdf>
 *
 * Exit codes:
 *   0  — PDF loaded, JS extracted and attempted (partial or full success)
 *   1  — missing argv
 *   2  — unreadable PDF (parser error)
 *   3  — fatal exception (signal itself — a PDF that crashes the parser is suspicious)
 */

const fs = require('fs');
const vm = require('vm');
const dns = require('dns');
const net = require('net');
const http = require('http');
const https = require('https');

// ─────────────────────────────────────────────────────────────────────
// Stubbed PDF JS context — mimics the Adobe Acrobat API
// ─────────────────────────────────────────────────────────────────────
//
// When the PDF JS calls app.launchURL("evil.com"), our stub makes a REAL
// dns.lookup + net.connect → strace catches the connect() syscall
// → the c2_communication hypothesis detects it → the score rises.
//
// We DO NOT BLOCK — we let it through to observe. The K8s sandbox
// (NetworkPolicy + isolated namespace) bounds the blast radius.

function createAdobeContext() {
    const log = (sig, data) => {
        try {
            process.stdout.write(JSON.stringify({sig, data}) + '\n');
        } catch (_) {}
    };

    // Helper — triggers a real connect() without blocking
    function realConnect(host, port) {
        try {
            dns.lookup(host, () => {});                          // syscall: sendto (DNS)
            const sock = net.connect({host, port: port || 80});  // syscall: connect
            sock.on('connect', () => sock.end());
            sock.on('error', () => {});
            sock.setTimeout(1500, () => sock.destroy());
        } catch (_) {}
    }

    function urlConnect(url) {
        try {
            const u = new URL(url);
            realConnect(u.hostname, u.port || (u.protocol === 'https:' ? 443 : 80));
        } catch (_) {}
    }

    const app = {
        alert:        (msg, icon, type, title) => log('app.alert', {msg: String(msg).slice(0, 200)}),
        launchURL:    (url) => { log('app.launchURL', {url}); urlConnect(url); },
        mailMsg:      (bUI, cTo, cCc, cBcc, cSubject) => {
            log('app.mailMsg', {to: cTo, subject: cSubject});
            if (cTo) realConnect(cTo.split('@').pop() || 'localhost', 25);
        },
        beep:         () => log('app.beep', {}),
        setTimeOut:   (cExpr, ms) => { log('app.setTimeOut', {ms}); /* don't actually run */ },
        clearTimeOut: () => {},
        execMenuItem: (cMenuItem) => log('app.execMenuItem', {menu: cMenuItem}),
        viewerVersion: 11,
        viewerType:    'Reader',
        platform:      'WIN',
        language:      'ENU',
    };

    // PDF "this" — a Document
    const thisDoc = {
        getField:    (name) => ({
            value: '', name, type: 'text',
            setAction: (trigger, code) => log('field.setAction', {trigger, code: code.slice(0, 80)}),
        }),
        getURL:      (url) => { log('this.getURL', {url}); urlConnect(url); },
        submitForm:  (url) => { log('this.submitForm', {url}); urlConnect(url); },
        mailDoc:     (bUI, cTo) => { log('this.mailDoc', {to: cTo}); },
        exportAsFDF: () => log('this.exportAsFDF', {}),
        importAnFDF: () => log('this.importAnFDF', {}),
        saveAs:      (path) => { log('this.saveAs', {path}); try { fs.writeFileSync(path, ''); } catch(_) {} },
        info:        {Title: '', Author: '', Subject: ''},
        path:        '/tmp/sample.pdf',
        numPages:    1,
    };

    const util = {
        printf:           (fmt, ...args) => String(fmt),
        stringFromStream: () => '',
        byteToChar:       (b) => String.fromCharCode(b),
        printd:           (fmt, date) => String(date || ''),
    };

    return {app, this: thisDoc, util, console, log, unescape: decodeURIComponent};
}

// ─────────────────────────────────────────────────────────────────────
// JS extraction from the PDF
// ─────────────────────────────────────────────────────────────────────

async function extractAllJs(doc) {
    const scripts = [];

    // 1. Document-level JS actions (OpenAction, AA — DC/WC/WS/DS/WP/DP)
    try {
        const docJs = await doc.getJSActions();
        if (docJs) {
            for (const [event, actions] of Object.entries(docJs)) {
                const arr = Array.isArray(actions) ? actions : [actions];
                for (const code of arr) {
                    if (typeof code === 'string') scripts.push({where: `doc.${event}`, code});
                }
            }
        }
    } catch (e) {
        process.stderr.write(`doc_js_extract_error: ${e.message}\n`);
    }

    // 2. Per-page JS + annotations
    const pageLimit = Math.min(doc.numPages, 50);
    for (let i = 1; i <= pageLimit; i++) {
        try {
            const page = await doc.getPage(i);

            // Page-level JS
            try {
                const pageJs = await page.getJSActions();
                if (pageJs) {
                    for (const [event, actions] of Object.entries(pageJs)) {
                        const arr = Array.isArray(actions) ? actions : [actions];
                        for (const code of arr) {
                            if (typeof code === 'string') scripts.push({where: `page${i}.${event}`, code});
                        }
                    }
                }
            } catch (_) {}

            // Annotation actions (link, widget, etc.)
            try {
                const annots = await page.getAnnotations({intent: 'display'});
                for (const a of annots) {
                    if (a.actions) {
                        for (const [event, actions] of Object.entries(a.actions)) {
                            const arr = Array.isArray(actions) ? actions : [actions];
                            for (const code of arr) {
                                if (typeof code === 'string') scripts.push({where: `p${i}.annot.${a.subtype || 'X'}.${event}`, code});
                            }
                        }
                    }
                }
            } catch (_) {}

            page.cleanup();
        } catch (e) {
            process.stderr.write(`page_${i}_error: ${e.message}\n`);
        }
    }

    return scripts;
}

// ─────────────────────────────────────────────────────────────────────
// Main
// ─────────────────────────────────────────────────────────────────────

async function main() {
    if (process.argv.length < 3) {
        process.stderr.write('Usage: pdf_runner.js <path-to-pdf>\n');
        process.exit(1);
    }

    const pdfPath = process.argv[2];
    const data = new Uint8Array(fs.readFileSync(pdfPath));

    // pdfjs-dist : legacy build (CommonJS, no DOM polyfill needed)
    const pdfjs = require('pdfjs-dist/legacy/build/pdf.js');

    let doc;
    try {
        doc = await pdfjs.getDocument({
            data,
            isEvalSupported: false,    // we handle eval ourselves via vm
            disableFontFace: true,
            useSystemFonts: false,
            verbosity: 0,
        }).promise;
    } catch (e) {
        process.stderr.write(`parse_error: ${e.message}\n`);
        process.exit(2);
    }

    process.stdout.write(JSON.stringify({sig: 'pdf_loaded', data: {pages: doc.numPages}}) + '\n');

    const scripts = await extractAllJs(doc);
    process.stdout.write(JSON.stringify({sig: 'js_extracted', data: {count: scripts.length}}) + '\n');

    // Execution: a single shared context (PDF scripts can see each other)
    const ctx = createAdobeContext();
    vm.createContext(ctx);

    for (const {where, code} of scripts) {
        process.stdout.write(JSON.stringify({sig: 'js_exec', data: {where, preview: code.slice(0, 120)}}) + '\n');
        try {
            vm.runInContext(code, ctx, {timeout: 2000, breakOnSigint: true});
        } catch (e) {
            process.stderr.write(`exec_err ${where}: ${e.message}\n`);
        }
    }

    // Give async operations (connect, dns) 1s to produce syscalls
    await new Promise(r => setTimeout(r, 1000));

    await doc.destroy();
    process.stdout.write(JSON.stringify({sig: 'done', data: {scripts_run: scripts.length}}) + '\n');
}

main().catch(e => {
    process.stderr.write(`fatal: ${e.message}\n`);
    process.stderr.write((e.stack || '').slice(0, 500) + '\n');
    process.exit(3);
});
