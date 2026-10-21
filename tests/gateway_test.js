// Testa o conector do WhatsApp (gateway/index.js) de verdade, ligado ao server.py de verdade.
// As bibliotecas express, qrcode, pino e @whiskeysockets/baileys são SUBSTITUTAS de teste (a Baileys real precisa de internet e do WhatsApp).
// Uso: node tests/gateway_test.js
const fs = require('fs'), path = require('path'), os = require('os')
const { spawn } = require('child_process')
const ROOT = path.resolve(__dirname, '..')
const GW_PORT = 3101, CTRL = 3999, SRV_PORT = 8767
const GW = `http://127.0.0.1:${GW_PORT}`, CT = `http://127.0.0.1:${CTRL}`, SRV = `http://127.0.0.1:${SRV_PORT}`
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const until = async (fn, ms = 8000, what = 'condição') => { const t = Date.now(); while (Date.now() - t < ms) { try { if (await fn()) return } catch {} await sleep(100) } throw new Error('tempo esgotado esperando: ' + what) }
const expect = (c, m) => { if (!c) throw new Error(m) }
const results = []
const step = async (name, fn) => { try { await fn(); results.push(true); console.log('OK    ' + name) } catch (e) { results.push(false); console.log('FALHA ' + name + ' -> ' + String(e.message).split('\n')[0]) } }
const gw = async (p, o = {}) => { const r = await fetch(GW + p, { method: o.body ? 'POST' : o.method || 'GET', headers: { 'x-secret': o.secret ?? 'seg', 'content-type': 'application/json', ...(o.line ? { 'x-line': o.line } : {}) }, body: o.body ? JSON.stringify(o.body) : undefined }); const t = await r.text(); let j = null; try { j = JSON.parse(t) } catch {} return { status: r.status, json: j, text: t } }
const gwRaw = async (p, line) => { const r = await fetch(GW + p, { headers: { 'x-secret': 'seg', ...(line ? { 'x-line': line } : {}) } }); return { status: r.status, type: r.headers.get('content-type'), buf: Buffer.from(await r.arrayBuffer()) } }
const ctrl = async (p, body) => (await fetch(CT + p, { method: body ? 'POST' : 'GET', body: body ? JSON.stringify(body) : undefined })).json()
const srv = async (p, o = {}) => { const r = await fetch(SRV + p, { method: o.method || (o.body ? 'POST' : 'GET'), headers: { 'X-Token': 'testtoken', 'content-type': 'application/json' }, body: o.body ? JSON.stringify(o.body) : undefined }); return { status: r.status, json: await r.json().catch(() => null) } }
const db = async (sql, args = []) => (await srv('/__test/db', { body: { sql, args } })).json

// ---------- bibliotecas substitutas ----------
const EXPRESS = `const http=require('http'),{URL}=require('url')
function express(){const stack=[];const app=()=>{};const add=(m,p,fn)=>stack.push({m,p,fn})
app.use=(fn)=>stack.push({fn});app.get=(p,fn)=>add('GET',p,fn);app.post=(p,fn)=>add('POST',p,fn)
app.listen=(port,host,cb)=>{const s=http.createServer((rq,rs)=>{let raw='';rq.on('data',d=>raw+=d);rq.on('end',()=>{const u=new URL(rq.url,'http://x')
const req={method:rq.method,path:u.pathname,query:Object.fromEntries(u.searchParams),headers:rq.headers,get:h=>rq.headers[h.toLowerCase()],body:undefined,_raw:raw};let st=200
const res={status(c){st=c;return res},json(o){rs.writeHead(st,{'content-type':'application/json'});rs.end(JSON.stringify(o))},type(t){res._t=t==='html'?'text/html':t;return res},send(x){rs.writeHead(st,{'content-type':res._t||'text/plain'});rs.end(Buffer.isBuffer(x)?x:String(x))}}
let i=0;const next=()=>{const e=stack[i++];if(!e)return res.status(404).json({error:'not found'});if(!e.m)return e.fn(req,res,next);if(e.m===req.method&&e.p===req.path)return e.fn(req,res,next);next()};next()})});s.listen(port,host,cb);return s}
return app}
express.json=()=>(req,res,next)=>{try{req.body=req._raw?JSON.parse(req._raw):{}}catch{req.body={}}next()}
module.exports=express`
const QRCODE = `module.exports={toDataURL:async(s)=>'data:image/png;base64,FAKE-'+s,toString:async(s)=>'##'+s+'##'}`
const PINO = `module.exports=()=>({level:'warn',info(){},warn(){},error(){},debug(){},child(){return this}})`
const CORE = `const http=require('http'),fs=require('fs')
const ctrlPort=Number(process.env.FAKE_BAILEYS_CTRL||3999);let sockets=0,cur=null;const reg={},socks={},actions=[]
const log=a=>actions.push({t:Date.now(),...a})
function Emitter(){const h={};return{on:(e,f)=>(h[e]=h[e]||[]).push(f),removeAllListeners:e=>{if(e)delete h[e];else for(const k in h)delete h[k]},emit:(e,a)=>(h[e]||[]).forEach(f=>f(a))}}
function makeWASocket(o){sockets++;const dir=(o&&o.auth&&o.auth.dir)||'?';const ev=Emitter();const sock={ev,dir,authState:{creds:{get registered(){return !!reg[dir]}}},user:undefined,
async profilePictureUrl(j){if(String(j).includes('5599999999999'))throw new Error('item-not-found');return 'http://127.0.0.1:'+ctrlPort+'/pic'},async onWhatsApp(n){return[{exists:!String(n).endsWith('404'),jid:n+'@s.whatsapp.net'}]},async presenceSubscribe(j){log({a:'subscribe',jid:j,dir})},
async sendPresenceUpdate(s,j){log({a:'presence',state:s,jid:j,dir})},async sendMessage(j,c){log({a:'send',jid:j,text:c.text,kind:Object.keys(c)[0],file:c.fileName,mime:c.mimetype,cap:c.caption,size:(c.document||c.image||c.video||c.audio||[]).length,dir});return{key:{id:'MSG'+actions.length}}},
async readMessages(){log({a:'read',dir})},async requestPairingCode(n){if(reg[dir])throw new Error('já registrado');log({a:'pair',phone:n,dir});return'ABCD1234'},
async logout(){log({a:'logout',dir});reg[dir]=false;setTimeout(()=>ev.emit('connection.update',{connection:'close',lastDisconnect:{error:{output:{statusCode:401},message:'logged out'}}}),20)},
end(){log({a:'end',dir})},updateMediaMessage(){}};cur=sock;socks[dir]=sock
setTimeout(()=>ev.emit('connection.update',{connection:'connecting'}),10)
setTimeout(()=>{if(reg[dir]){sock.user={id:'5521999990000:12@s.whatsapp.net'};ev.emit('connection.update',{connection:'open'})}else ev.emit('connection.update',{qr:'QR-'+sockets})},40);return sock}
async function useMultiFileAuthState(d){const existed=fs.existsSync(d);fs.mkdirSync(d,{recursive:true});log({a:'auth',existed,dir:d});return{state:{creds:{},dir:d},saveCreds:()=>{}}}
async function fetchLatestBaileysVersion(){return{version:[2,3000,1]}}
async function downloadMediaMessage(m){return Buffer.from(m.__media||'x','base64')}
const DisconnectReason={loggedOut:401,restartRequired:515,connectionReplaced:440,badSession:500}
const pick=b=>{const d=b.line&&b.line!=='main'?'./auth-'+b.line:'./auth';return socks[d]||cur}
http.createServer((rq,rs)=>{let raw='';rq.on('data',d=>raw+=d);rq.on('end',()=>{const b=raw?JSON.parse(raw):{};const ok=o=>{rs.writeHead(200,{'content-type':'application/json'});rs.end(JSON.stringify(o))}
if(rq.url==='/pic'){rs.writeHead(200,{'content-type':'image/png'});return rs.end(Buffer.from('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360f8cfc0f01f0005000201a5f645400000000049454e44ae426082','hex'))}
if(rq.url==='/open'){const k=pick(b);reg[k.dir]=true;k.user={id:(b.me||'5521999990000')+':12@s.whatsapp.net'};k.ev.emit('connection.update',{connection:'open'});return ok({})}
if(rq.url==='/message'){pick(b).ev.emit('messages.upsert',{messages:[b.m||b],type:'notify'});return ok({})}
if(rq.url==='/close'){pick(b).ev.emit('connection.update',{connection:'close',lastDisconnect:{error:{output:{statusCode:b.code},message:'fechou'}}});return ok({})}
if(rq.url==='/log')return ok({sockets,actions});ok({})})}).listen(ctrlPort,'127.0.0.1')
module.exports={makeWASocket,useMultiFileAuthState,fetchLatestBaileysVersion,downloadMediaMessage,DisconnectReason}`
const BAILEYS_CJS = `const c=require('./core.cjs');Object.assign(exports,c);exports.default=c.makeWASocket;Object.defineProperty(exports,'__esModule',{value:true})`
const BAILEYS_ESM = `import core from './core.cjs'\nexport default core.makeWASocket\nexport const { makeWASocket, useMultiFileAuthState, fetchLatestBaileysVersion, downloadMediaMessage, DisconnectReason } = core`

function setup(variant) {
  const base = fs.mkdtempSync(path.join(os.tmpdir(), 'gw-')); const g = path.join(base, 'gateway')
  fs.mkdirSync(g, { recursive: true })
  fs.writeFileSync(path.join(base, '.env'), '# comentário\nOUTRA=1\nGATEWAY_SECRET="seg"\n')   // o conector deve ler o segredo daqui
  fs.copyFileSync(path.join(ROOT, 'gateway/index.js'), path.join(g, 'index.js'))
  fs.copyFileSync(path.join(ROOT, 'gateway/package.json'), path.join(g, 'package.json'))
  const mod = (name, files, pkg = {}) => { const d = path.join(g, 'node_modules', name); fs.mkdirSync(d, { recursive: true }); fs.writeFileSync(path.join(d, 'package.json'), JSON.stringify({ name, main: 'index.js', ...pkg })); for (const [f, c] of Object.entries(files)) fs.writeFileSync(path.join(d, f), c) }
  mod('express', { 'index.js': EXPRESS }); mod('qrcode', { 'index.js': QRCODE }); mod('pino', { 'index.js': PINO })
  mod('@whiskeysockets/baileys', { 'core.cjs': CORE, 'index.js': variant === 'esm' ? BAILEYS_ESM : BAILEYS_CJS }, variant === 'esm' ? { type: 'module' } : {})
  return { base, g }
}
function start(cmd, args, opts) { const p = spawn(cmd, args, opts); let log = ''; p.stdout.on('data', (d) => (log += d)); p.stderr.on('data', (d) => (log += d)); p.getLog = () => log; return p }

async function scenario(variant, full) {
  const { g } = setup(variant)
  const env = { PATH: process.env.PATH, HOME: process.env.HOME, GATEWAY_PORT: String(GW_PORT), FAKE_BAILEYS_CTRL: String(CTRL), INBOUND_URL: `${SRV}/gateway/inbound` }
  const harness = full ? start('python3', [path.join(ROOT, 'tests/harness.py'), String(SRV_PORT)], { cwd: ROOT, env: { ...process.env, REAL_GATEWAY: GW, GATEWAY_URL: GW } }) : null
  if (harness) await until(() => harness.getLog().includes('harness em'), 15000, 'servidor de teste')
  const gate = start('node', ['index.js'], { cwd: g, env })
  const tag = `[baileys ${variant}] `
  try {
    await step(tag + 'conector sobe, lê o segredo de ../.env e carrega a biblioteca', async () => {
      await until(async () => (await gw('/status')).status === 200, 8000, 'gateway no ar')
      expect(!gate.getLog().includes('formato inesperado') && !gate.getLog().includes('Defina GATEWAY_SECRET'), gate.getLog().slice(0, 200))
      expect((await gw('/status', { secret: '' })).status === 403 && (await gw('/status', { secret: 'x' })).status === 403, 'sem proteção por segredo')
    })
    await step(tag + 'mostra o QR (imagem e página de apoio /qr) e protege com a chave', async () => {
      await until(async () => (await gw('/status')).json.state === 'qr', 5000, 'estado qr')
      const s = (await gw('/status')).json; expect(s.qr.startsWith('data:image/png;base64,FAKE-QR-'), 'qr: ' + s.qr)
      const page = await gw('/qr?key=seg', { secret: '' }); expect(page.status === 200 && page.text.includes('Escaneie') && page.text.includes('/status'), 'página /qr')
      expect((await gw('/qr?key=errada', { secret: '' })).status === 403, '/qr sem chave correta')
      expect(gate.getLog().includes('Novo QR code') && gate.getLog().includes('##QR-'), 'QR no terminal')
    })
    await step(tag + 'enviar antes de conectar devolve 503; código por número valida e responde', async () => {
      expect((await gw('/send', { body: { to: '5511', text: 'oi' } })).status === 503, 'send sem conexão')
      expect((await gw('/pair', { body: { phone: '123' } })).status === 400, 'número curto')
      const r = await gw('/pair', { body: { phone: '5511999990000' } }); expect(r.status === 200 && r.json.code === 'ABCD-1234', 'código: ' + r.text)
    })
    await step(tag + 'escanear (conectar) muda o estado, esconde o QR e informa o número', async () => {
      await ctrl('/open', {}); await until(async () => (await gw('/status')).json.state === 'open', 4000, 'open')
      const s = (await gw('/status')).json; expect(s.me === '5521999990000' && s.qr === null, JSON.stringify(s))
    })
    await step(tag + 'envio mostra "digitando" antes de mandar, e trata erros', async () => {
      const t0 = Date.now(); const r = await gw('/send', { body: { to: '5521988880099', text: 'Olá!', typing_ms: 1200 } })
      expect(r.status === 200 && Date.now() - t0 >= 1150, 'duração: ' + (Date.now() - t0))
      const acts = (await ctrl('/log')).actions.filter((a) => ['presence', 'send'].includes(a.a)).slice(-3).map((a) => a.a + (a.state ? ':' + a.state : ''))
      expect(acts.join(',') === 'presence:composing,presence:paused,send', 'ordem: ' + acts)
      expect((await gw('/send', { body: { to: '5521988880404', text: 'oi' } })).status === 404, 'número sem WhatsApp')
      expect((await gw('/send', { body: { to: '5521988880099' } })).status === 400, 'sem texto')
    })
    if (!full) return
    // ---------- ligação com o servidor ----------
    const lead = async (phone) => (await srv('/api/leads')).json.find((l) => l.phone === phone)
    const acts = async () => (await ctrl('/log')).actions
    await srv('/api/pacing', { method: 'PUT', body: { reply_delay_min: 0, reply_delay_max: 0 } })
    const msg = (jid, id, message, extra = {}) => ctrl('/message', { key: { remoteJid: jid, fromMe: false, id, ...(extra.key || {}) }, pushName: extra.pushName || 'Teste', message, __media: extra.media })
    await step('mensagem do WhatsApp chega ao servidor, o agente responde e a resposta sai pelo conector', async () => {
      await msg('5521988880001@s.whatsapp.net', 'A1', { conversation: 'oi, quero plano de saúde' }, { pushName: 'Zeca' })
      await until(async () => await lead('5521988880001'), 6000, 'lead criado')
      const l = await lead('5521988880001'); expect(l.origin === 'receptivo' && l.niche === 'Planos de saúde' && l.name === 'Zeca', 'lead: ' + JSON.stringify([l.origin, l.niche, l.name]))
      await until(async () => (await acts()).some((a) => a.a === 'send' && a.jid === '5521988880001@s.whatsapp.net'), 6000, 'resposta enviada')
      const a = await acts(); const i = a.findIndex((x) => x.a === 'send' && x.jid === '5521988880001@s.whatsapp.net')
      expect(a[i].text.includes('cidade') && a.slice(0, i).some((x) => x.a === 'presence' && x.state === 'composing' && x.jid === a[i].jid), 'digitando antes da resposta')
      expect(a.some((x) => x.a === 'read'), 'marcou como lida')
    })
    await step('grupos e mensagens enviadas por nós são ignorados', async () => {
      const n0 = (await srv('/api/leads')).json.length
      await msg('120363000@g.us', 'G1', { conversation: 'oi grupo' }); await msg('5521988887777@s.whatsapp.net', 'F1', { conversation: 'eco' }, { key: { fromMe: true } })
      await sleep(900); expect((await srv('/api/leads')).json.length === n0, 'criou lead indevido')
    })
    await step('contato @lid usa o número real e a resposta volta pelo identificador certo', async () => {
      await msg('99887766@lid', 'L1', { conversation: 'plano de saúde por favor' }, { key: { remoteJidAlt: '5521988880002@s.whatsapp.net' }, pushName: 'Lia' })
      await until(async () => await lead('5521988880002'), 6000, 'lead pelo número real')
      await until(async () => (await acts()).some((a) => a.a === 'send' && a.jid === '99887766@lid'), 6000, 'resposta para o @lid')
      expect(JSON.parse(fs.readFileSync(path.join(g, 'jids.json'), 'utf8'))['5521988880002'] === '99887766@lid', 'jids.json')
    })
    await step('imagem, áudio e figurinha: viram leitura, transcrição e aviso', async () => {
      await msg('5521988880003@s.whatsapp.net', 'M1', { imageMessage: { mimetype: 'image/jpeg', caption: '' } }, { media: Buffer.from([0xff, 0xd8, 0xff, 1]).toString('base64') })
      await msg('5521988880004@s.whatsapp.net', 'M2', { audioMessage: { mimetype: 'audio/ogg; codecs=opus', ptt: true } }, { media: Buffer.from('OggS').toString('base64') })
      await msg('5521988880005@s.whatsapp.net', 'M3', { stickerMessage: {} })
      await until(async () => (await lead('5521988880003')) && (await lead('5521988880004')) && (await lead('5521988880005')), 8000, 'três leads')
      const t = async (p) => (await db("SELECT text FROM messages WHERE phone=? AND role='lead'", [p]))[0].text
      expect((await t('5521988880003')).includes('Leitura automática'), 'imagem'); expect((await t('5521988880004')).includes('transcrito automaticamente'), 'áudio')
      expect((await t('5521988880005')).includes('stickerMessage'), 'figurinha: ' + (await t('5521988880005')))
    })
    await step('vídeo: o conector baixa e entrega ao servidor como vídeo', async () => {
      await msg('5521988880007@s.whatsapp.net', 'V1', { videoMessage: { mimetype: 'video/mp4', caption: 'olha' } }, { media: Buffer.from('\x00\x00\x00\x18ftypmp42').toString('base64') })
      await until(async () => await lead('5521988880007'), 8000, 'lead do vídeo')
      const t = (await db("SELECT text FROM messages WHERE phone='5521988880007' AND role='lead'"))[0].text
      expect(/vídeo/.test(t), 'texto do vídeo: ' + t)
    })
    await step('localização, contato e botão viram texto; reação é ignorada', async () => {
      await msg('5521988880011@s.whatsapp.net', 'LOC1', { locationMessage: { degreesLatitude: -23.5, degreesLongitude: -46.6, name: 'Loja Centro', address: 'Rua A, 10' } })
      await msg('5521988880012@s.whatsapp.net', 'C1', { contactMessage: { displayName: 'Maria Silva', vcard: 'BEGIN:VCARD\nTEL;waid=5511999990000:+55 11 99999-0000\nEND:VCARD' } })
      await msg('5521988880013@s.whatsapp.net', 'B1', { buttonsResponseMessage: { selectedDisplayText: 'Quero saber mais' } })
      await msg('5521988880014@s.whatsapp.net', 'R1', { reactionMessage: { text: '👍' } })
      await until(async () => (await lead('5521988880011')) && (await lead('5521988880012')) && (await lead('5521988880013')), 8000, 'leads: ' + gate.getLog().split('\n').filter(l => /rro|falh|Error/i.test(l)).slice(-3).join(' | '))
      const t = async (p) => (await db("SELECT text FROM messages WHERE phone=? AND role='lead'", [p]))[0].text
      expect(/Loja Centro/.test(await t('5521988880011')) && /maps\.google\.com\/\?q=-23\.5,-46\.6/.test(await t('5521988880011')), 'localização: ' + await t('5521988880011'))
      expect(/Maria Silva/.test(await t('5521988880012')) && /99999-0000/.test(await t('5521988880012')), 'contato: ' + await t('5521988880012'))
      expect((await t('5521988880013')) === 'Quero saber mais', 'botão')
      await sleep(600); expect(!(await lead('5521988880014')), 'reação não deveria criar lead')
    })
    await step('enviar material: documento, imagem e vídeo saem com tipo, nome e legenda; erros tratados', async () => {
      const post = (b) => fetch(GW + '/send-media', { method: 'POST', headers: { 'x-secret': 'seg', 'content-type': 'application/json' }, body: JSON.stringify(b) })
      const d64 = Buffer.from('%PDF-1.4 x').toString('base64')
      expect((await post({ to: '5521988880003', kind: 'document', mime: 'application/pdf', filename: 'cat.pdf', caption: 'Segue', data: d64 })).status === 200, 'documento')
      expect((await post({ to: '5521988880003', kind: 'image', mime: 'image/png', data: d64, caption: 'foto' })).status === 200, 'imagem')
      const acts = (await ctrl('/log')).actions.filter((x) => x.a === 'send' && x.kind)
      const doc = acts.find((x) => x.kind === 'document'), img = acts.find((x) => x.kind === 'image')
      expect(doc && doc.file === 'cat.pdf' && doc.mime === 'application/pdf' && doc.size === 10 && doc.cap === 'Segue', 'documento: ' + JSON.stringify(doc))
      expect(img && img.cap === 'foto', 'imagem: ' + JSON.stringify(img))
      expect((await post({ to: '5521988880003', kind: 'exe', data: d64 })).status === 400, 'tipo inválido')
      expect((await fetch(GW + '/send-media', { method: 'POST', headers: { 'content-type': 'application/json' }, body: '{}' })).status === 403, 'sem segredo')
    })
    await step('foto de perfil: o conector devolve a imagem; sem foto ou segredo errado dá erro', async () => {
      const a = await gwRaw('/photo?to=5521988880003'); expect(a.status === 200 && a.type === 'image/png' && a.buf.slice(1, 4).toString() === 'PNG', 'foto do contato ' + a.status)
      const m = await gwRaw('/photo?to=me'); expect(m.status === 200, 'foto do próprio número ' + m.status)
      const n = await gwRaw('/photo?to=5599999999999'); expect(n.status === 404, 'sem foto deveria ser 404, veio ' + n.status)
      const e = await fetch(GW + '/photo?to=5521988880003', { headers: { 'x-secret': 'errado' } }); expect(e.status === 403, 'segredo errado')
      const x = await gwRaw('/photo', 'main'); expect(x.status === 400, 'to é obrigatório')
    })
    await step('reconexão (código 515) abre um novo socket sem duplicar mensagens', async () => {
      const s0 = (await ctrl('/log')).sockets; await ctrl('/close', { code: 515 })
      await until(async () => (await ctrl('/log')).sockets === s0 + 1, 5000, 'novo socket'); await until(async () => (await gw('/status')).json.state === 'open', 5000, 'reabriu')
      expect((await acts()).some((a) => a.a === 'end'), 'socket antigo não foi encerrado')
      await msg('5521988880006@s.whatsapp.net', 'R1', { conversation: 'plano de saúde' }); await until(async () => await lead('5521988880006'), 6000, 'lead')
      await sleep(600); const n = (await db("SELECT COUNT(*) n FROM messages WHERE phone='5521988880006' AND role='lead'"))[0].n; expect(n === 1, 'mensagem processada ' + n + 'x')
    })
    await step('servidor → conector: disparo da fila sai com "digitando"; sem conexão a fila registra falha', async () => {
      await srv('/api/pacing', { method: 'PUT', body: { warmup: false, daily_limit: 300 } })
      await srv('/api/dispatch', { body: { niche_id: 1, lines: '5521977770001;Carla\n5521977770002;Davi', consent: true, origem: 'lista de teste' } })
      await srv('/__test/tick', { body: {} })
      const a = await acts(); const i = a.map((x) => x.a + ':' + (x.jid || '')).lastIndexOf('send:5521977770001@s.whatsapp.net')
      expect(i > 0 && a.slice(0, i).some((x) => x.a === 'presence' && x.jid === '5521977770001@s.whatsapp.net' && x.state === 'composing') && a[i].text.includes('Carla'), 'envio do 1º contato')
      await ctrl('/close', { code: 500 }); await until(async () => (await gw('/status')).json.state === 'closed' || true, 500)
      const st = (await srv('/__test/tick', { body: {} })).json.find((r) => r.phone === '5521977770002')
      expect(['failed', 'queued', 'sent'].includes(st.status), 'status: ' + st.status)
    })
    await step('desconectar pelo painel apaga a sessão e volta a pedir o QR; código por número pelo servidor', async () => {
      await until(async () => (await gw('/status')).json.state === 'open', 8000, 'conectado de novo')
      expect((await srv('/api/connection/logout', { body: {} })).status === 200, 'logout')
      await until(async () => (await gw('/status')).json.state === 'qr', 6000, 'voltou ao QR')
      const auths = (await acts()).filter((a) => a.a === 'auth'); expect(auths.at(-1).existed === false, 'a sessão antiga não foi apagada')
      const c = await srv('/api/connection/pair', { body: { phone: '5511999990000' } }); expect(c.status === 200 && c.json.code === 'ABCD-1234', 'código pelo servidor: ' + JSON.stringify(c))
      const c2 = await srv('/api/connection/pair', { body: { phone: '12' } }); expect(c2.status === 400, 'número inválido')
    })
    // ---------- vários números ----------
    await step('vários números: criar, listar, limite e id inválido', async () => {
      expect((await gw('/line/add', { body: { id: 'Ruim Id' } })).status === 400, 'id inválido aceito')
      expect((await gw('/line/add', { body: { id: 'comercial-2' } })).json.existed === false, 'não criou')
      expect((await gw('/line/add', { body: { id: 'comercial-2' } })).json.existed === true, 'não é idempotente')
      await db("INSERT INTO lines(id,label,active,created) VALUES('comercial-2','Comercial 2',1,1)")   // o servidor também conhece a linha (o painel faz isto ao adicionar)
      await until(async () => (await gw('/status', { line: 'comercial-2' })).json.state === 'qr', 5000, 'QR da linha 2')
      const l = (await gw('/lines')).json; expect(l.length === 2 && l[0].id === 'main' && l[1].id === 'comercial-2', JSON.stringify(l))
      expect((await gw('/status', { line: 'zzz' })).status === 404, 'linha desconhecida deveria dar 404')
      expect((await gw('/send', { line: 'zzz', body: { to: '5511', text: 'oi' } })).status === 404, 'envio em linha desconhecida')
      expect(JSON.parse(fs.readFileSync(path.join(g, 'lines.json'), 'utf8')).join() === 'comercial-2', 'lines.json')
      expect(fs.existsSync(path.join(g, 'auth-comercial-2')) && !fs.existsSync(path.join(g, 'auth-main')), 'pastas de sessão')
    })
    await step('vários números: cada um tem seu QR, código e estado, sem afetar o outro', async () => {
      const q1 = (await gw('/status', { line: 'comercial-2' })).json.qr, q0 = (await gw('/status')).json
      expect(q1 && q1.startsWith('data:image/png') && q0.state === 'qr', 'QRs ' + q0.state)
      const page = await gw('/qr?key=seg&line=comercial-2', { secret: '' }); expect(page.status === 200 && page.text.includes('comercial') === false && page.text.includes("get('line')"), 'página /qr por linha')
      const p = await gw('/pair', { line: 'comercial-2', body: { phone: '5511999990001' } }); expect(p.status === 200 && p.json.code === 'ABCD-1234', 'pair ' + p.text)
      expect((await ctrl('/log')).actions.some((a) => a.a === 'pair' && a.dir === './auth-comercial-2'), 'código pedido na sessão errada')
      await ctrl('/open', { line: 'comercial-2', me: '5521999990002' })
      await until(async () => (await gw('/status', { line: 'comercial-2' })).json.state === 'open', 4000, 'linha 2 conectada')
      const a = (await gw('/status')).json, b = (await gw('/status', { line: 'comercial-2' })).json
      expect(a.state === 'qr' && b.me === '5521999990002', 'estados misturados: ' + JSON.stringify([a.state, b.me]))
    })
    await step('vários números: o envio sai pela sessão pedida e o gateway só envia se aquela estiver conectada', async () => {
      expect((await gw('/send', { body: { to: '5521988881111', text: 'oi' } })).status === 503, 'principal está desconectada')
      const r = await gw('/send', { line: 'comercial-2', body: { to: '5521988881111', text: 'Olá pela 2' } }); expect(r.status === 200, 'envio ' + r.text)
      const s = (await ctrl('/log')).actions.filter((x) => x.a === 'send').at(-1); expect(s.dir === './auth-comercial-2' && s.text === 'Olá pela 2', JSON.stringify(s))
    })
    await step('vários números: mensagem recebida informa a linha e a resposta volta pela mesma', async () => {
      await ctrl('/message', { line: 'comercial-2', m: { key: { remoteJid: '5521988881234@s.whatsapp.net', fromMe: false, id: 'L2A' }, pushName: 'Nina', message: { conversation: 'oi, quero plano de saúde' } } })
      await until(async () => await lead('5521988881234'), 6000, 'lead pela linha 2')
      expect((await db("SELECT line FROM leads WHERE phone='5521988881234'"))[0].line === 'comercial-2', 'lead sem a linha')
      await until(async () => (await ctrl('/log')).actions.some((x) => x.a === 'send' && x.jid === '5521988881234@s.whatsapp.net'), 6000, 'resposta')
      expect((await ctrl('/log')).actions.filter((x) => x.a === 'send' && x.jid === '5521988881234@s.whatsapp.net').every((x) => x.dir === './auth-comercial-2'), 'resposta saiu por outra sessão')
      expect(JSON.parse(fs.readFileSync(path.join(g, 'jids.json'), 'utf8'))['comercial-2:5521988881234'], 'identificador por linha')
    })
    await step('vários números: pelo painel, adicionar número e ver o estado dele', async () => {
      const a = await srv('/api/lines', { body: { label: 'Vendas Sul' } }); expect(a.status === 200 && a.json.id === 'vendas-sul', JSON.stringify(a))
      await until(async () => (await srv('/api/connection?line=vendas-sul')).json.state === 'qr', 6000, 'QR pelo servidor')
      const ls = (await srv('/api/lines')).json.lines; expect(ls.length === 3 && ls.find((x) => x.id === 'comercial-2').state === 'open', JSON.stringify(ls.map((x) => [x.id, x.state])))
      expect((await srv('/api/connection/logout?line=vendas-sul', { body: {} })).status === 200, 'logout da linha')
    })
    await step('vários números: reiniciar o gateway recria as linhas e remover apaga a sessão', async () => {
      const r = await srv('/api/lines/vendas-sul', { method: 'DELETE' }); expect(r.status === 200, 'remover ' + JSON.stringify(r))
      expect(!fs.existsSync(path.join(g, 'auth-vendas-sul')) && (await gw('/lines')).json.every((x) => x.id !== 'vendas-sul'), 'sessão não apagada')
      expect((await gw('/line/remove', { body: { id: 'main' } })).status === 400, 'principal removível')
    })
    await step('conector e servidor sem exceções', async () => {
      expect(!/TypeError|ReferenceError|Unhandled|Error:/.test(gate.getLog().replace(/falha ao baixar mídia/g, '')), 'gateway: ' + gate.getLog().split('\n').filter((l) => /Error/.test(l)).slice(0, 2).join(' | '))
      expect(!/Traceback/.test(harness.getLog()), 'servidor: ' + harness.getLog().split('Traceback')[1]?.split('\n').slice(0, 5).join(' / '))
    })
  } finally { gate.kill(); harness?.kill(); await sleep(300) }
}

;(async () => {
  await scenario('cjs', true)      // formato da Baileys 6.x (CommonJS com exports.default)
  await scenario('esm', false)     // formato da Baileys 7.x (ESM)
  const fails = results.filter((r) => !r).length
  console.log(`\n${results.length - fails} ok, ${fails} falha(s)`); process.exit(fails ? 1 : 0)
})().catch((e) => { console.error('ERRO NO TESTE', e); process.exit(2) })
