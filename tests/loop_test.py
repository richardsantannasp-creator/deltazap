"""Testa o ciclo AUTOMÁTICO da fila (outbox_loop), sem acionar manualmente: um envio por vez e espera real entre eles."""
import asyncio, sys, time, os
sys.path.insert(0, os.path.dirname(__file__))
import harness

async def main():
    S = harness.load_server()
    await S.pacing_put({"min_delay": 20, "max_delay": 20, "batch_size": 50, "warmup": False, "daily_limit": 100, "reply_delay_min": 0, "reply_delay_max": 0})
    await S.dispatch(S.DispatchIn(niche_id=1, lines="5511999990001;Ana\n5511999990002;Beto", consent=True, origem="lista de teste"), None)
    S.NEXT_AT = 0; S.LINE_NEXT.clear(); S.LINE_STATE_TS = 0
    task = asyncio.create_task(S.outbox_loop())          # o ciclo real, que checa a fila a cada 2 s
    await asyncio.sleep(3.5)
    sent1 = len(harness.SENT)
    gap = S.NEXT_AT - time.time()
    await asyncio.sleep(3.5)
    sent2 = len(harness.SENT)
    task.cancel()
    ok = sent1 == 1 and sent2 == 1 and 14 <= gap <= 145
    print(("OK    " if ok else "FALHA ") + f"ciclo automático: 1º envio em <=2 s ({sent1}), espera de {gap:.0f}s respeitada ({sent2} após 7 s)")
    sys.exit(0 if ok else 1)
asyncio.run(main())
