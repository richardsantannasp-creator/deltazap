// Gateway de WhatsApp por QR code (sessão tipo WhatsApp Web), usando a biblioteca não oficial Baileys.
// ATENÇÃO: não é a API oficial da Meta. O uso pode violar os Termos do WhatsApp e o número pode ser banido.
// Este processo só conecta, envia e repassa mensagens. O ritmo de envio é controlado pelo servidor Python (fila).
import express from 'express'
import QRCode from 'qrcode'
import pino from 'pino'
import fs from 'fs'
import * as Baileys from '@whiskeysockets/baileys'

// A biblioteca é CommonJS (6.x) ou ESM (7.x): resolve as funções nos dois formatos, sem depender de "import default"
const lib = { ...(typeof Baileys.default === 'object' ? Baileys.default : {}), ...Baileys }
const makeWASocket = typeof Baileys.default === 'function' ? Baileys.default : (lib.makeWASocket || lib.default)
const { useMultiFileAuthState, DisconnectReason, fetchLatestBaileysVersion, downloadMediaMessage } = lib
if (typeof makeWASocket !== 'function' || !useMultiFileAuthState || !DisconnectReason) {
  console.error('A biblioteca @whiskeysockets/baileys foi carregada em um formato inesperado. Rode: npm install @whiskeysockets/baileys@latest')
  process.exit(1)
}

// Lê o .env do projeto (../.env) quando a variável não veio do terminal: assim GATEWAY_SECRET é o mesmo do servidor
for (const f of [new URL('../.env', import.meta.url), new URL('./.env', import.meta.url)]) {
  try {
    for (const line of fs.readFileSync(f, 'utf8').split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Za-z_0-9]+)\s*=\s*(.*?)\s*$/)
      if (m && process.env[m[1]] === undefined) process.env[m[1]] = m[2].replace(/^['"]|['"]$/g, '')
    }
  } catch {}
}

const PORT = Number(process.env.GATEWAY_PORT || 3001)
const SECRET = process.env.GATEWAY_SECRET || ''
const INBOUND_URL = process.env.INBOUND_URL || 'http://127.0.0.1:8000/gateway/inbound'
const AUTH_DIR = process.env.AUTH_DIR || './auth'
const JID_FILE = process.env.JID_FILE || './jids.json'
const MAX_MEDIA = 8 * 1024 * 1024
const MAX_VIDEO = 16 * 1024 * 1024
const log = pino({ level: process.env.LOG_LEVEL || 'warn' })

if (!SECRET) { console.error('Defina GATEWAY_SECRET (o mesmo valor do servidor Python).'); process.exit(1) }

// Várias linhas (números) no mesmo gateway: cada uma é uma sessão independente identificada por um id curto.
// A linha "main" usa a pasta AUTH_DIR (compatível com instalações antigas); as demais usam AUTH_DIR-<id>.
const LINES_FILE = process.env.LINES_FILE || './lines.json'
const MAX_LINES = Number(process.env.LINES_MAX || 5)
const validId = (s) => typeof s === 'string' && /^[a-z0-9_-]{1,20}$/.test(s)
const authDirFor = (id) => (id === 'main' ? AUTH_DIR : `${AUTH_DIR}-${id}`)
const sessions = new Map()
const newSession = (id) => ({ id, sock: null, state: 'connecting', qrData: null, me: null, removed: false, timer: null })
const saveLines = () => { try { fs.writeFileSync(LINES_FILE, JSON.stringify([...sessions.keys()].filter((k) => k !== 'main'))) } catch {} }

let jids = {}
try { jids = JSON.parse(fs.readFileSync(JID_FILE, 'utf8')) } catch { jids = {} }
const jk = (id, phone) => (id === 'main' ? phone : `${id}:${phone}`)   // o mesmo contato pode ter ids diferentes em contas diferentes
let saveTimer = null
const saveJids = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => fs.writeFile(JID_FILE, JSON.stringify(jids), () => {}), 500) }
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function start(s) {
  if (s.removed) return
  if (s.sock) { // garante um único socket ativo por linha (vários ao mesmo tempo causam "conexão substituída")
    try { s.sock.ev.removeAllListeners('connection.update'); s.sock.ev.removeAllListeners('messages.upsert'); s.sock.end(undefined) } catch {}
    s.sock = null
  }
  const tag = s.id === 'main' ? '' : `[${s.id}] `
  const { state: auth, saveCreds } = await useMultiFileAuthState(authDirFor(s.id))
  const { version } = await fetchLatestBaileysVersion()
  const sock = makeWASocket({ version, auth, logger: log, printQRInTerminal: false, markOnlineOnConnect: false, syncFullHistory: false })
  s.sock = sock
  sock.ev.on('creds.update', saveCreds)

  sock.ev.on('connection.update', async ({ connection, lastDisconnect, qr }) => {
    if (s.sock !== sock || s.removed) return
    if (qr) {
      // margem de 4 módulos (zona de silêncio exigida pelos leitores de QR) e tamanho maior
      s.qrData = await QRCode.toDataURL(qr, { width: 420, margin: 4, errorCorrectionLevel: 'M' }); s.state = 'qr'
      console.log(`\n${tag}Novo QR code (também aparece no painel). Escaneie em até ~20 segundos:\n`)
      console.log(await QRCode.toString(qr, { type: 'terminal', small: true }))
    }
    if (connection) console.log(tag + '[conexão]', connection, lastDisconnect?.error ? `código ${lastDisconnect.error?.output?.statusCode}: ${lastDisconnect.error?.message}` : '')
    if (connection === 'open') {
      s.state = 'open'; s.qrData = null
      s.me = (sock.user?.id || '').split(':')[0].split('@')[0] || null
      console.log(tag + 'WhatsApp conectado:', s.me)
    } else if (connection === 'connecting' && s.state !== 'qr') {
      s.state = 'connecting'
    } else if (connection === 'close') {
      const code = lastDisconnect?.error?.output?.statusCode
      s.state = 'closed'; s.me = null; s.qrData = null
      if (code === DisconnectReason.loggedOut) fs.rmSync(authDirFor(s.id), { recursive: true, force: true })
      if (code === 405) console.error('Código 405: a versão da biblioteca está desatualizada para o WhatsApp. Rode: npm update @whiskeysockets/baileys e reinicie.')
      if (code === 515) console.log(tag + 'Reiniciando a conexão após o pareamento (normal logo depois de escanear)...')
      if (code === 440) console.error(tag + 'Código 440: esta conta foi aberta em outro lugar. Mantenha apenas um gateway rodando.')
      clearTimeout(s.timer)
      s.timer = setTimeout(() => start(s).catch((e) => console.error(tag + 'falha ao reiniciar:', e?.message || e)), code === DisconnectReason.loggedOut || code === 515 ? 500 : 3000)
    }
  })

  sock.ev.on('messages.upsert', async ({ messages, type }) => {
    if (type !== 'notify') return
    for (const m of messages) {
      try { await onMessage(s, m) } catch (e) { console.error(tag + 'erro ao repassar mensagem:', e?.message || e) }
    }
  })
}

async function onMessage(s, m) {
  if (!m.message || m.key.fromMe) return
  const jid = m.key.remoteJid
  if (!jid || jid.endsWith('@g.us') || jid.endsWith('@broadcast') || jid === 'status@broadcast') return
  const alt = m.key.remoteJidAlt || m.key.senderPn // quando o contato vem como @lid, tenta o número real
  const phoneJid = jid.endsWith('@lid') && alt ? alt : jid
  const phone = phoneJid.split('@')[0].split(':')[0]
  jids[jk(s.id, phone)] = jid; saveJids()

  const msg = m.message
  let kind = 'text', mime = null, media = null
  let text = msg.conversation || msg.extendedTextMessage?.text || msg.imageMessage?.caption || msg.documentMessage?.caption || msg.videoMessage?.caption || ''
  if (msg.imageMessage) { kind = 'image'; mime = msg.imageMessage.mimetype }
  else if (msg.documentMessage) { kind = 'document'; mime = msg.documentMessage.mimetype }
  else if (msg.audioMessage) { kind = 'audio'; mime = msg.audioMessage.mimetype }
  else if (msg.videoMessage || msg.ptvMessage) { kind = 'video'; mime = (msg.videoMessage || msg.ptvMessage).mimetype || 'video/mp4' } // vídeo, GIF animado e vídeo-mensagem
  else if (msg.reactionMessage) return // reação com emoji: não é conversa
  else if (msg.locationMessage || msg.liveLocationMessage) {
    const l = msg.locationMessage || msg.liveLocationMessage
    kind = 'text'
    text = `[o lead compartilhou uma localização: ${[l.name, l.address].filter(Boolean).join(' ')} (${l.degreesLatitude}, ${l.degreesLongitude}) https://maps.google.com/?q=${l.degreesLatitude},${l.degreesLongitude}]`
  } else if (msg.contactMessage || msg.contactsArrayMessage) {
    const cs = msg.contactMessage ? [msg.contactMessage] : (msg.contactsArrayMessage.contacts || [])
    const one = c => { const t = (String(c.vcard || '').match(/waid=(\d+)|TEL[^:]*:([+\d\s()-]+)/) || []); return `${c.displayName || 'sem nome'}${(t[1] || t[2]) ? ' (' + String(t[1] || t[2]).trim() + ')' : ''}` }
    kind = 'text'
    text = '[o lead compartilhou um contato: ' + cs.map(one).join('; ') + ']'
  } else if (msg.buttonsResponseMessage || msg.listResponseMessage || msg.templateButtonReplyMessage) {
    kind = 'text'
    text = msg.buttonsResponseMessage?.selectedDisplayText || msg.listResponseMessage?.title || msg.templateButtonReplyMessage?.selectedDisplayText || ''
  } else if (!text) kind = Object.keys(msg)[0] || 'outro'

  if (kind === 'image' || kind === 'document' || kind === 'audio' || kind === 'video') {
    try {
      const buf = await downloadMediaMessage(m, 'buffer', {}, { logger: log, reuploadRequest: s.sock.updateMediaMessage })
      if (buf.length <= (kind === 'video' ? MAX_VIDEO : MAX_MEDIA)) media = buf.toString('base64')
    } catch (e) { console.error('falha ao baixar mídia:', e?.message || e) }
  }
  try { await s.sock.readMessages([m.key]) } catch {}

  await fetch(INBOUND_URL, {
    method: 'POST',
    headers: { 'content-type': 'application/json', 'x-secret': SECRET },
    body: JSON.stringify({ from: phone, name: m.pushName || '', id: m.key.id, type: kind, text, mime, media, line: s.id, me: s.me }),
  })
}

const app = express()
app.use(express.json({ limit: '20mb' })) // /send-media recebe o arquivo em base64
// Página de apoio para escanear sem o painel: http://127.0.0.1:3001/qr?key=SEU_GATEWAY_SECRET (só na própria máquina)
app.get('/qr', (req, res) => {
  if (req.query.key !== SECRET) return res.status(403).send('forbidden')
  res.type('html').send(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>QR WhatsApp</title>
<body style="margin:0;background:#fff;color:#111;font:16px system-ui;display:flex;flex-direction:column;align-items:center;gap:12px;padding:24px">
<h3 id="t">Aguardando…</h3><img id="q" style="width:min(80vmin,420px);height:auto;display:none"><p id="s" style="color:#555;text-align:center"></p>
<script>const k=${JSON.stringify(SECRET)},L=new URLSearchParams(location.search).get('line')||'main';async function f(){try{const r=await (await fetch('/status',{headers:{'x-secret':k,'x-line':L}})).json();
const t=document.getElementById('t'),q=document.getElementById('q'),s=document.getElementById('s');
if(r.state==='qr'&&r.qr){t.textContent='Escaneie com o WhatsApp';if(q.src!==r.qr)q.src=r.qr;q.style.display='block';s.textContent='WhatsApp > Aparelhos conectados > Conectar um aparelho. O QR renova sozinho.'}
else{q.style.display='none';t.textContent=r.state==='open'?'Conectado'+(r.me?' como +'+r.me:''):'Estado: '+r.state;s.textContent=''}}catch(e){}}f();setInterval(f,2000)</script>`)
})

app.use((req, res, next) => (req.get('x-secret') === SECRET ? next() : res.status(403).json({ error: 'forbidden' })))

// Escolhe a linha pelo cabeçalho x-line (ou ?line=). Sem ele, vale "main".
const pick = (req, res) => {
  const id = String(req.get('x-line') || req.query?.line || 'main')
  const s = sessions.get(id)
  if (!s) { res.status(404).json({ error: 'linha desconhecida' }); return null }
  return s
}

app.get('/status', (req, res) => { const s = pick(req, res); if (s) res.json({ state: s.state, qr: s.qrData, me: s.me, line: s.id }) })
app.get('/lines', (_req, res) => res.json([...sessions.values()].map((s) => ({ id: s.id, state: s.state, me: s.me }))))

// Cria (ou garante) uma linha. Idempotente: o servidor chama isto para sincronizar as linhas cadastradas.
app.post('/line/add', async (req, res) => {
  const id = String(req.body?.id || '')
  if (!validId(id)) return res.status(400).json({ error: 'id inválido (use letras minúsculas, números, - e _; até 20 caracteres)' })
  if (sessions.has(id)) return res.json({ ok: true, existed: true })
  if (sessions.size >= MAX_LINES) return res.status(400).json({ error: `limite de ${MAX_LINES} linhas (LINES_MAX)` })
  const s = newSession(id); sessions.set(id, s); saveLines()
  start(s).catch((e) => console.error(`[${id}] falha ao iniciar:`, e?.message || e))
  res.json({ ok: true, existed: false })
})

app.post('/line/remove', async (req, res) => {
  const id = String(req.body?.id || '')
  if (id === 'main') return res.status(400).json({ error: 'a linha principal não pode ser removida' })
  const s = sessions.get(id)
  if (!s) return res.json({ ok: true, existed: false })
  s.removed = true; clearTimeout(s.timer)
  try { await s.sock?.logout() } catch {}
  try { s.sock?.ev.removeAllListeners('connection.update'); s.sock?.ev.removeAllListeners('messages.upsert'); s.sock?.end(undefined) } catch {}
  sessions.delete(id); saveLines()
  fs.rmSync(authDirFor(id), { recursive: true, force: true })
  for (const k of Object.keys(jids)) if (k.startsWith(id + ':')) delete jids[k]
  saveJids()
  res.json({ ok: true, existed: true })
})

// Foto de perfil (do contato ou do próprio número com to="me"). Devolve os bytes da imagem; 404 quando não há foto ou ela é privada.
app.get('/photo', async (req, res) => {
  const s = pick(req, res); if (!s) return
  if (s.state !== 'open') return res.status(503).json({ error: 'WhatsApp não conectado' })
  try {
    const to = String(req.query.to || '').replace(/[^0-9a-z@.:_-]/gi, '')
    let jid
    if (to === 'me') { if (!s.me) return res.status(404).json({ error: 'sem número' }); jid = `${s.me}@s.whatsapp.net` }
    else if (!to) return res.status(400).json({ error: 'to é obrigatório' })
    else { jid = jids[jk(s.id, to)] || `${to.replace(/\D/g, '')}@s.whatsapp.net` }
    let url
    try { url = await s.sock.profilePictureUrl(jid, 'image') } catch { return res.status(404).json({ error: 'sem foto' }) }
    if (!url) return res.status(404).json({ error: 'sem foto' })
    const r = await fetch(url)
    if (!r.ok) return res.status(404).json({ error: 'sem foto' })
    const buf = Buffer.from(await r.arrayBuffer())
    if (!buf.length || buf.length > 400000) return res.status(404).json({ error: 'foto grande demais' })
    res.type(r.headers.get('content-type') || 'image/jpeg').send(buf)
  } catch (e) {
    res.status(500).json({ error: String(e?.message || e) })
  }
})

app.post('/send', async (req, res) => {
  const s = pick(req, res); if (!s) return
  if (s.state !== 'open') return res.status(503).json({ error: 'WhatsApp não conectado' })
  const { to, text, typing_ms = 0 } = req.body || {}
  if (!to || !text) return res.status(400).json({ error: 'to e text são obrigatórios' })
  try {
    const key = jk(s.id, to)
    let jid = jids[key]
    if (!jid) { // confirma que o número existe no WhatsApp antes de enviar
      const r = await s.sock.onWhatsApp(to)
      if (!r?.[0]?.exists) return res.status(404).json({ error: 'número sem WhatsApp' })
      jid = r[0].jid; jids[key] = jid; saveJids()
    }
    if (typing_ms > 0) {
      await s.sock.presenceSubscribe(jid)
      await s.sock.sendPresenceUpdate('composing', jid)
      await sleep(Math.min(Number(typing_ms), 15000))
      await s.sock.sendPresenceUpdate('paused', jid)
    }
    const r = await s.sock.sendMessage(jid, { text })
    res.json({ ok: true, id: r?.key?.id })
  } catch (e) {
    res.status(500).json({ error: String(e?.message || e) })
  }
})

app.post('/send-media', async (req, res) => {
  const s = pick(req, res); if (!s) return
  if (s.state !== 'open') return res.status(503).json({ error: 'WhatsApp não conectado' })
  const { to, kind, mime, filename, caption = '', data } = req.body || {}
  if (!to || !data || !['image', 'video', 'audio', 'document'].includes(kind)) return res.status(400).json({ error: 'to, kind e data são obrigatórios' })
  try {
    const key = jk(s.id, to)
    let jid = jids[key]
    if (!jid) {
      const r = await s.sock.onWhatsApp(to)
      if (!r?.[0]?.exists) return res.status(404).json({ error: 'número sem WhatsApp' })
      jid = r[0].jid; jids[key] = jid; saveJids()
    }
    const buf = Buffer.from(data, 'base64')
    const content = kind === 'image' ? { image: buf, caption }
      : kind === 'video' ? { video: buf, caption, mimetype: mime }
      : kind === 'audio' ? { audio: buf, mimetype: mime, ptt: false }
      : { document: buf, mimetype: mime, fileName: filename || 'arquivo', caption }
    const r = await s.sock.sendMessage(jid, content)
    res.json({ ok: true, id: r?.key?.id })
  } catch (e) {
    res.status(500).json({ error: String(e?.message || e) })
  }
})

// Conexão por código (sem câmera): WhatsApp > Aparelhos conectados > Conectar um aparelho > Conectar com número de telefone
app.post('/pair', async (req, res) => {
  const s = pick(req, res); if (!s) return
  const phone = String(req.body?.phone || '').replace(/\D/g, '')
  if (phone.length < 10) return res.status(400).json({ error: 'Informe o número com DDI e DDD, ex.: 5511999999999' })
  if (!s.sock || !['qr', 'connecting'].includes(s.state)) return res.status(503).json({ error: 'Aguarde o gateway iniciar (o QR precisa aparecer) e tente de novo' })
  if (s.sock.authState?.creds?.registered) return res.status(400).json({ error: 'Já existe uma sessão; desconecte primeiro' })
  try {
    const code = await s.sock.requestPairingCode(phone)
    res.json({ code: (code.match(/.{1,4}/g) || [code]).join('-') })
  } catch (e) {
    res.status(500).json({ error: String(e?.message || e) })
  }
})

app.post('/logout', async (req, res) => {
  const s = pick(req, res); if (!s) return
  try { await s.sock?.logout() } catch {}
  res.json({ ok: true })
})

const HOST = process.env.GATEWAY_HOST || '127.0.0.1'      // no Docker use 0.0.0.0 e NÃO publique a porta para fora (o segredo protege, mas a rede interna basta)
app.listen(PORT, HOST, () => console.log(`Gateway em http://${HOST}:${PORT}`))
sessions.set('main', newSession('main'))
try { for (const id of JSON.parse(fs.readFileSync(LINES_FILE, 'utf8'))) if (validId(id) && id !== 'main' && sessions.size < MAX_LINES) sessions.set(id, newSession(id)) } catch {}
for (const s of sessions.values()) start(s).catch((e) => { console.error(`[${s.id}]`, e); if (s.id === 'main') process.exit(1) })
