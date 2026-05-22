#!/usr/bin/env node
/**
 * pdf_runner.js — couche dynamique JS PDF (PDF.js + Node vm sandbox)
 *
 * Mission : exécuter le JavaScript embarqué dans un PDF dans un environnement
 * où strace peut observer les syscalls qui en résultent.
 *
 * Stratégie :
 *   1. Charger le PDF avec pdfjs-dist (parser Mozilla — robuste sur PDFs malformés)
 *   2. Extraire TOUS les blocs JS :
 *        - /OpenAction et /AA au niveau document
 *        - /AA par page
 *        - /A et /AA dans les annotations (form fields, links, etc.)
 *        - /JavaScript dans les noms (/Names tree)
 *   3. Exécuter chaque bloc dans un Node vm sandboxé avec un contexte
 *      Adobe-like stubbé. Les API stubbées qui font de la network/disk I/O
 *      déclenchent de VRAIS syscalls visibles par strace.
 *
 * Pourquoi vm + stubs plutôt que PDF.js sandbox natif ?
 *   - PDF.js sandbox utilise QuickJS via WebAssembly → syscalls noyés dans wasm
 *   - vm Node est V8 direct → syscalls clairs et attribuables
 *   - On contrôle quelles API déclenchent quoi (granularité fine pour la détection)
 *
 * Sortie : stdout = events JSON (one per line) pour debug.
 *          stderr = traces d'exécution.
 *          Tous les comportements suspects passent par des syscalls réels
 *          que strace -f intercepte en amont.
 *
 * Usage : node pdf_runner.js <path-to-pdf>
 *
 * Exit codes :
 *   0  — PDF chargé, JS extrait et tenté (succès partiel ou total)
 *   1  — argv manquant
 *   2  — PDF illisible (parser error)
 *   3  — exception fatale (signal lui-même — un PDF qui crashe le parser est suspect)
 */

const fs = require('fs');
const vm = require('vm');
const dns = require('dns');
const net = require('net');
const http = require('http');
const https = require('https');

// ─────────────────────────────────────────────────────────────────────
// Contexte PDF JS stubbé — mime l'API Adobe Acrobat
// ─────────────────────────────────────────────────────────────────────
//
// Quand le JS PDF appelle app.launchURL("evil.com"), notre stub fait
// un VRAI dns.lookup + net.connect → strace catch le syscall connect()
// → hypothèse c2_communication détecte → score remonte.
//
// On NE BLOQUE PAS — on laisse passer pour observer. La sandbox K8s
// (NetworkPolicy + namespace isolé) borde le blast radius.

function createAdobeContext() {
    const log = (sig, data) => {
        try {
            process.stdout.write(JSON.stringify({sig, data}) + '\n');
        } catch (_) {}
    };

    // Helper — déclenche un connect() réel sans bloquer
    function realConnect(host, port) {
        try {
            dns.lookup(host, () => {});                          // syscall : sendto (DNS)
            const sock = net.connect({host, port: port || 80});  // syscall : connect
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

    // PDF "this" — un Document
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
// Extraction JS depuis le PDF
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
            isEvalSupported: false,    // on gère eval nous-mêmes via vm
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

    // Exécution : un seul contexte partagé (les scripts PDF se voient entre eux)
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

    // Laisse 1s aux opérations async (connect, dns) pour produire des syscalls
    await new Promise(r => setTimeout(r, 1000));

    await doc.destroy();
    process.stdout.write(JSON.stringify({sig: 'done', data: {scripts_run: scripts.length}}) + '\n');
}

main().catch(e => {
    process.stderr.write(`fatal: ${e.message}\n`);
    process.stderr.write((e.stack || '').slice(0, 500) + '\n');
    process.exit(3);
});
