# Guia do operador: hospedar o SDR para seus clientes e cobrar mensalidade

Este kit é para **você** (quem vende). Cada cliente recebe uma instância separada do sistema, com banco, arquivos, sessão do WhatsApp, senhas e endereço próprios. Um cliente nunca enxerga os dados de outro. A assinatura é controlada por vencimento: vencendo, o sistema do cliente é pausado e o endereço mostra "acesso suspenso"; pagando, você renova e ele volta.

> **Sobre os testes:** a ferramenta `deploy/sdr-admin.py` foi testada em modo simulado (arquivos gerados, cadastro, vencimento, suspensão, comandos do Docker que seriam executados): 40 verificações. **Não pude executar o Docker nem construir as imagens no ambiente em que preparei isto.** Faça o primeiro cliente de teste (seu) com calma e confira os logs (`docker logs sdr-<cliente>`).

## 1. Preparar o servidor (uma vez)
- VPS Linux com Docker e Docker Compose. Conte ~1 GB de RAM por cliente no modo QR (servidor + conector) e ~0,5 GB no modo API oficial. Comece com 4 GB para ~3 clientes.
- Um domínio seu, por exemplo `sdr.seudominio.com.br`, com um registro DNS **curinga** `*.sdr.seudominio.com.br` apontando para o IP do servidor. Portas 80 e 443 liberadas; **não abra** 8000 nem 3001.
- Copie a pasta `sdr-whatsapp` inteira para o servidor (ex.: `/opt/sdr-whatsapp`).

```
cd /opt/sdr-whatsapp
python3 deploy/sdr-admin.py iniciar --dominio-base sdr.seudominio.com.br --email voce@seudominio.com.br
python3 deploy/sdr-admin.py construir
```
Os dados ficam em `/opt/sdr-clientes` (ou `$SDR_HOME`). Faça backup dessa pasta e dos volumes do Docker.

## 2. Criar um cliente
API oficial da Meta (recomendado para operação comercial estável):
```
python3 deploy/sdr-admin.py novo acme --nome "Acme Ltda" --provider official --dias 30 \
   --anthropic-key sk-ant-... --wa-token EAAG... --wa-phone-id 123456 --meta-secret abc...
```
QR code (exige o aceite registrado do cliente, veja a seção 6):
```
python3 deploy/sdr-admin.py novo beta --nome "Beta ME" --provider qr --aceito-risco-qr --dias 30
```
O comando imprime o endereço (`https://acme.sdr.seudominio.com.br`), a senha do painel (`DASH_TOKEN`) e, na API oficial, o endereço do webhook e o *verify token* para colar no painel da Meta. Entregue a senha por um canal seguro. Se faltar alguma chave, edite `/opt/sdr-clientes/clientes/<cliente>/.env` e rode `reiniciar <cliente>`.

**Quem paga o Claude?** Duas opções: (a) o cliente usa a chave dele (mais simples; o custo não é seu); (b) você usa uma chave sua e embute o custo na mensalidade. Nesse caso, defina o orçamento mensal na aba Custos de cada cliente (a IA para ao estourar) e confirme com a Anthropic as condições comerciais de revenda.

**Seu cliente também pode vender pelo WhatsApp.** Cada instância já traz catálogo, base de conhecimento, link de pagamento (fixo, Asaas ou Stripe) e o simulador de avaliação (README, "Vender pelo WhatsApp"). Os webhooks de pagamento do cliente usam o endereço dele (`https://cliente.../pay/webhook/asaas`), são independentes da **sua** cobrança de mensalidade (seção 3) e o dinheiro cai na conta do provedor **dele**. Peça que ele teste primeiro no sandbox. O avaliador usa o Claude da chave configurada na instância: avise quem paga a chave.

## 3. Cobrança, avisos e suspensão
Cada cliente tem **data de validade**, **período** (dias somados a cada pagamento; padrão 30) e **tolerância** (dias após o vencimento antes de suspender; padrão 3, de 0 a 30). Defina no cadastro (`novo acme ... --tolerancia 5 --periodo-dias 30`) ou mude depois pelo painel.

### Regras de vencimento (já embutidas)
| Situação | O que acontece |
|---|---|
| Faltam 5 a 3 dias | Faixa azul no painel do cliente: "Sua assinatura vence em N dias" + seu contato |
| Faltam 2 a 0 dias | Faixa amarela ("vence hoje" no dia) |
| Venceu, dentro da tolerância | Faixa vermelha: "Assinatura vencida há N dia(s). O acesso será suspenso em X dia(s)..." O sistema **continua respondendo os leads** |
| Passou da tolerância | Suspenso: o sistema do cliente para e o endereço mostra "Acesso suspenso". Dados preservados |
| Pagamento confirmado | Renova (soma ao prazo que sobrou; se já venceu, conta a partir de hoje), reativa e apaga o aviso |

Os avisos são gravados por `suspender-vencidos` (e pelo receptor, a cada 6 h) no contêiner de cada cliente; só chamam o Docker quando o texto muda. Informe seu contato uma vez em `iniciar --contato "WhatsApp 11 99999-0000"`.
**Aviso por contrato:** a faixa no painel só é vista por quem abre o painel. Combine no contrato também um aviso por e-mail ou WhatsApp do seu lado (o Asaas e o Stripe já enviam lembretes de cobrança ao cliente) e a tolerância escolhida (`deploy/termos-modelo.md`, cláusula 2).

### Receptor de pagamentos e painel do operador (`sdr-cobranca.py`)
Um serviço pequeno (sem dependências) que fica ao lado do `sdr-admin.py`:
1. **Variáveis (arquivo `/etc/sdr-cobranca.env`, permissão 600):** `OPERADOR_TOKEN` (senha do painel, 16+ caracteres), e conforme o provedor: `ASAAS_WEBHOOK_TOKEN`, `STRIPE_WEBHOOK_SECRET`, `PAY_HMAC_SECRET`. Provedor sem segredo responde 404.
2. **Serviço (systemd):** crie `/etc/systemd/system/sdr-cobranca.service` com `ExecStart=/usr/bin/python3 /opt/sdr-whatsapp/deploy/sdr-cobranca.py`, `EnvironmentFile=/etc/sdr-cobranca.env`, `Restart=always`; depois `systemctl enable --now sdr-cobranca`. Escuta na porta 8900.
3. **Endereço público só do webhook:** `iniciar ... --dominio-operador cobranca.seudominio.com.br` (DNS apontando para o servidor). O proxy publica **apenas** `/cobranca/*`; o painel não é publicado e, mesmo que alguém chegue à porta, só abre para quem está dentro do próprio servidor.
4. **Cadastre o webhook no provedor:**
   - Asaas: URL `https://cobranca.seudominio.com.br/cobranca/asaas`, token = `ASAAS_WEBHOOK_TOKEN`, eventos de pagamento recebido/confirmado.
   - Stripe: URL `.../cobranca/stripe`, evento `invoice.paid` (ou `invoice.payment_succeeded`); o segredo `whsec_...` vai em `STRIPE_WEBHOOK_SECRET`. Aceita só eventos com menos de 5 min.
   - Outros (Kiwify, Mercado Pago via n8n/Make etc.): `POST .../cobranca/generico` com JSON `{"id":"único","cliente":"acme","dias":30}` e cabeçalho `X-Signature` = HMAC-SHA256 (hex) do corpo com `PAY_HMAC_SECRET`.
5. **Ligar cliente do provedor ao cliente do sistema:** `sdr-admin.py vincular acme --provedor asaas --cliente-id cus_123` (ou pelo painel). Pagamento de quem não tem vínculo fica no histórico como "sem_vinculo" e **não** renova ninguém.
6. **Painel:** do seu computador, `ssh -L 8900:127.0.0.1:8900 usuario@servidor` e abra `http://127.0.0.1:8900/painel`. Lista clientes (estado, vencimento, dias, tolerância, vínculo), renova, suspende, retoma, muda a tolerância, vincula e roda a rotina; mostra os últimos eventos. **Também cria cliente** (API oficial ou QR; o QR só cria com o aceite do risco marcado), **mostra a senha** do painel de cada cliente, **faz backup** (copia para `backups-painel/` no servidor), **reinicia** e **remove** (você digita o nome do cliente para confirmar; sem volta, faça backup antes). Criar, remover, backup, reiniciar e ver senha ficam no histórico (sem guardar chaves ou senhas).

Garantias: cada evento só vale uma vez (reenvio do provedor não renova duas vezes); assinatura inválida é recusada e registrada; erro de um cliente não derruba os outros.
**Limites honestos:** foi testado com eventos simulados no formato documentado do Asaas e do Stripe, não contra contas reais: faça um pagamento de teste (sandbox) antes de confiar. Não emite nota fiscal nem cobra o cliente; o provedor de pagamento faz isso.

### Sem o receptor
Continua valendo o modo manual: `renovar acme` ao receber e, por cron diário, `0 8 * * * python3 /opt/sdr-whatsapp/deploy/sdr-admin.py suspender-vencidos`. O `listar` mostra dias restantes.

## 4. Operação do dia a dia
| Tarefa | Comando |
|---|---|
| Ver clientes | `listar` |
| Senha do painel | `token <cliente>` |
| Reler o .env | `reiniciar <cliente>` |
| Atualizar o sistema para todos | substitua os arquivos e rode `atualizar` (mantém dados e sessões) |
| Backup dos clientes | `backup --todos --destino /caminho/seguro` |
| Suspender / reativar | `suspender <c>` / `retomar <c>` |
| Apagar tudo de um cliente | `remover <c> --confirmo-apagar-dados` (sem volta) |

Cada instância também faz o backup diário dela e mostra na aba Integrações. **Os backups contêm dados pessoais de leads:** guarde com acesso restrito. As sessões de WhatsApp (modo QR) ficam nos volumes `wa-session` e **não** entram nesses backups, de propósito; perdê-las obriga o cliente a escanear o QR de novo.
Monitore `https://<cliente>.../health` num serviço externo (UptimeRobot, Better Stack).

## 5. O que este kit ainda não faz
- Não tem tela de cadastro/pagamento para o cliente final: ele paga no link/boleto do seu provedor. O painel do operador é só seu e só abre por túnel SSH (para acesso de outros aparelhos, use uma VPN como Tailscale em vez de publicar o painel).
- Não emite nota fiscal nem faz cobrança de inadimplente; contratos ficam fora do sistema.
- Cada cliente é uma instância própria. Passando de uns 10 a 20 clientes, vale evoluir para multi-cliente numa só instância.

## 6. Riscos e obrigações (leia antes de vender)
- **Modo QR (regra no sistema):** além do `--aceito-risco-qr` do operador, o painel do cliente **bloqueia o envio** até alguém ler e aceitar o aviso de risco de banimento (fica gravado quem/quando/versão). O risco continua sendo do número do cliente, e ao vender você recebe a reclamação. Usa uma biblioteca não oficial e pode violar os Termos do WhatsApp; o número do cliente pode ser banido, e ao vender você passa a receber essa reclamação. Por isso o comando exige `--aceito-risco-qr`, que grava a data do aceite. Só use com cliente informado, **por escrito**, e ofereça a API oficial como alternativa. Mais números não reduzem o risco.
- **LGPD:** você hospeda dados pessoais de leads do cliente: em geral o cliente é o controlador e você o operador. Precisa de contrato (cláusulas de tratamento de dados), política de privacidade, canal para titulares e plano para incidentes. O sistema já aplica: **origem do consentimento obrigatória** em cada disparo (gravada por lead), **lista de supressão** (quem diz SAIR nunca mais recebe, nem por reimportação; guarda só um hash), **exportar** e **apagar** os dados de um lead pela aba LGPD/Leads, com registro sem telefones. Mesmo assim, o **consentimento dos contatos é responsabilidade do cliente**: deixe isso claro no contrato. **Um advogado precisa revisar** contrato, política de privacidade e papéis de controlador/operador: o sistema ajuda, não substitui.
- **Termos e contrato:** há um esqueleto em `deploy/termos-modelo.md`. É um ponto de partida para um advogado revisar, **não** um documento pronto.
- **Segurança:** acesso ao servidor só por chave SSH, atualizações do sistema em dia, `.env` com permissão 600 (o kit já aplica) e backups protegidos.
- **Suporte:** o agente não faz promessas, mas erra como qualquer IA. Combine o escopo do que você garante.
