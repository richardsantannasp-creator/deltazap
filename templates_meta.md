# Templates sugeridos para aprovar na Meta (idioma pt_BR, 1 variável {{1}} = primeiro nome)

Só dispare para quem deu o número voluntariamente e consentiu em ser contatado (formulário, anúncio, cotação online). Guarde a prova do consentimento. A Meta decide a categoria final (Marketing ou Utility).

1) Lead que pediu cotação (formulário/anúncio)
Olá, {{1}}! Aqui é a Ana, assistente virtual da [CORRETORA]. Você pediu informações sobre plano de saúde. Posso te fazer 3 perguntas rápidas para buscar as melhores opções? Se não quiser receber mensagens, responda SAIR.

2) Reativação de lead que parou de responder
Oi, {{1}}! Passando para saber se você ainda está buscando um plano de saúde. Se sim, retomo de onde paramos. Se não quiser mais mensagens, responda SAIR.

Depois que o lead responde, a conversa fica livre por 24h e o agente conduz normalmente.

## Cadência de retomada (planos de saúde)
Textos prontos para templates de retomada (a conversa livre fecha após 24h sem resposta). O sistema ainda não dispara a cadência sozinho: use hoje manualmente (Disparar) ou peça a automação.
- Dia 1: "Oi, {{1}}! Ontem a gente começou a olhar o seu plano de saúde. Ainda faz sentido pra você? Se sim, me diga as idades e a cidade que eu adianto a comparação. Se não quiser mais mensagens, responda SAIR."
- Dia 3: "{{1}}, uma dica rápida: as carências só começam a contar depois que o plano é contratado, então quanto antes decidir, mais cedo você fica totalmente coberto. Quer que o corretor te envie as opções? Para não receber mais mensagens, responda SAIR."
- Dia 7 (encerramento gentil): "Oi, {{1}}! Não quero ser insistente, então vou deixar o seu atendimento em pausa por aqui. Se voltar a procurar plano de saúde, é só me chamar. Se preferir não receber mais mensagens, responda SAIR."

Regra: no máximo 3 retomadas por lead, e pare imediatamente se ele responder ou pedir para sair.

# Limpa Multas BR (nicho Limpa Multas)

Base de consentimento: quem preencheu o Analisador de Multa no site concordou em ser contatado pelo WhatsApp informado. Guarde esse registro (data, hora e número).

3) Lead do analisador (motorista)
Olá, {{1}}! Aqui é a Ana, assistente virtual da Limpa Multas BR. Você pediu a análise de uma multa pelo nosso site. Pode me enviar uma foto da notificação por aqui? Se não quiser receber mensagens, responda SAIR.

4) Lead do cadastro de parceiros
Olá, {{1}}! Aqui é a Ana, da Limpa Multas BR. Recebemos seu cadastro no programa de parceiros. Posso te fazer 3 perguntas rápidas para o time de parcerias preparar as condições? Se não quiser receber mensagens, responda SAIR.

Depois de aprovar, informe o nome do template no editor do nicho (Agentes > Limpa Multas).


## Retomada automática na API oficial (fora da janela de 24 h)
Cada etapa da cadência precisa de um template aprovado, com 1 variável `{{1}}` = primeiro nome. Informe o nome do template na etapa (aba Retomada). Sugestões (categoria Marketing; revise com o seu jurídico):
- **retomada_1**: "Oi, {{1}}! Passando para saber se você ainda tem interesse. Posso continuar de onde paramos? Para não receber mais mensagens, responda SAIR."
- **retomada_2**: "{{1}}, ficou alguma dúvida que eu possa tirar? Estou por aqui. Para não receber mais mensagens, responda SAIR."
- **retomada_3**: "Oi, {{1}}! Não quero ser insistente, então vou deixar o seu atendimento em pausa. Se precisar, é só me chamar. Para não receber mais mensagens, responda SAIR."
Observação: com template, o texto exato é o do template (o Claude não reescreve); no histórico do painel fica registrado o texto gerado para a etapa.
