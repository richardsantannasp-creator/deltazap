# Roteiro de piloto (7 dias)

Os testes automáticos do sistema usam WhatsApp, Claude, Whisper e pagamentos **simulados**. Este roteiro é o que falta: provar tudo com contas reais, em pequena escala, antes de vender ou divulgar. Use um número de teste (de preferência um chip novo, não o principal da empresa).

## Dia 0: preparar
1. Siga o `COMECE-AQUI.md` até o painel abrir.
2. Clique em **Verificar instalação** (topo do painel). Resolva todos os ❌ e leia os ⚠️. Ele confere a chave do Claude, o WhatsApp, áudio, vídeo, avisos, orçamento, nichos pendentes, disco e backup.
3. Defina um **orçamento mensal** pequeno na aba Custos (ex.: R$ 50) e configure ao menos um canal de aviso (e-mail ou webhook, para o alerta de queda do WhatsApp).
4. Escolha **um** nicho, preencha os campos `[ENTRE COLCHETES]`, cadastre catálogo e base de conhecimento e rode a **avaliação com clientes simulados** (aba Agentes). Meta: nota estável acima de 80 e nenhuma falha grave.

## Dia 1: conexão e conversa com você mesmo
Conecte o número de teste (QR) e, de **outro celular seu**, mande:

| Teste | O que esperar | ✔ |
|---|---|---|
| Mensagem de texto sobre o assunto do nicho | roteado ao nicho certo, resposta curta e uma pergunta por vez | |
| Áudio de 15 s | aparece "transcrito automaticamente" e a resposta faz sentido | |
| Foto de um documento | leitura automática correta; dados críticos confirmados | |
| PDF e vídeo curto | leitura do PDF; áudio e quadros do vídeo | |
| "Quanto custa?" (item do catálogo) | preço igual ao cadastro, sem inventar | |
| Pedir desconto acima do máximo | recusa e oferece o permitido | |
| "Você é um robô?" | responde que é assistente virtual | |
| "SAIR" | confirma, descarta e nunca mais recebe disparo | |
| "Quero falar com uma pessoa" | transfere (fila ou atendente) e a IA pausa | |
| Compra com link de pagamento (modo teste/sandbox do Asaas ou Stripe) | link correto; pagar no sandbox vira "ganho" | |

Anote o que errou e ajuste o prompt do nicho. Repita até não haver surpresa.

## Dias 2 e 3: disparo pequeno (só com consentimento)
- Importe **10 a 20 contatos que aceitaram** receber mensagem (amigos, clientes que pediram contato).
- Mantenha o ritmo padrão e o aquecimento ligado. Acompanhe a aba **Envio e conexão**: se a pausa automática disparar (muitos descartes), pare e revise o texto.
- Meta: respostas coerentes, nenhuma reclamação, nenhum aviso de bloqueio no celular.

## Dia 4: equipe humana
- Cadastre 1 ou 2 atendentes (aba Avisos > Equipe) e entre em `/atendente` em outro navegador.
- Provoque transferências: com atendente disponível, ausente e sem ninguém. Confira fila, resposta pelo WhatsApp com o nome dele, transferência entre atendentes e "devolver à IA".

## Dias 5 e 6: acompanhar
- Veja Funil, Custos (custo por lead) e a aba Conversas todos os dias. Leia as conversas reais: onde a IA hesitou, repetiu ou errou?
- Derrube o conector de propósito (pare o contêiner) e confirme que o alerta de queda chega por e-mail/webhook em ~5 minutos, e que a reconexão também avisa.
- Faça um **backup** e copie o arquivo para fora do servidor. Teste restaurar em outra pasta (`restore_backup.py`).

## Dia 7: decisão
Siga adiante só se **todos** forem verdadeiros:
- [ ] nota da avaliação estável (≥ 80) e sem falha grave;
- [ ] zero mensagem inventada (preço, prazo, cobertura) nas conversas reais;
- [ ] o SAIR e a transferência funcionaram sempre;
- [ ] custo por lead dentro do esperado;
- [ ] número sem bloqueio ou restrição durante o piloto;
- [ ] alerta de queda e backup testados.

## Se algo der errado
- **Número restrito ou bloqueado:** pare os disparos, não tente "driblar". O modo QR usa uma biblioteca não oficial e o risco é seu (o painel avisa). Para operação séria, migre para a API oficial da Meta.
- **IA falando algo errado:** corrija o prompt/base, rode a avaliação de novo e só então volte a disparar.
- **Cliente reclamou:** use "Apagar dados" ou o SAIR, registre e revise a lista de origem dos contatos.

Quando terminar, guarde as anotações: elas viram a base do seu playbook e das cláusulas do termo de uso para clientes.
