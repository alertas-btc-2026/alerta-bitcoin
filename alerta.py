"""Alerta de queda do Bitcoin -> notificacao no iPhone via ntfy.

Configuracao (no GitHub: Settings > Secrets and variables > Actions):
  - Secret   NTFY_TOPIC : nome do canal assinado no app ntfy
  - Variable PRECO_ALVO : preco em USD (ex.: 70000). Pode ter varios: 70000,65000,60000

Cada alvo avisa UMA vez quando o preco cai ate ele, e so volta a ficar
"armado" quando o preco sobe 2% acima do alvo (evita avisos repetidos).
"""
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

ESTADO = "estado.json"
REARME = 1.02  # volta a armar quando subir 2% acima do alvo


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "alerta-btc/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def preco_btc_usd():
    fontes = [
        ("Coinbase", "https://api.coinbase.com/v2/prices/BTC-USD/spot",
         lambda d: float(d["data"]["amount"])),
        ("CoinGecko", "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
         lambda d: float(d["bitcoin"]["usd"])),
        ("Kraken", "https://api.kraken.com/0/public/Ticker?pair=XBTUSD",
         lambda d: float(next(iter(d["result"].values()))["c"][0])),
    ]
    for nome, url, extrai in fontes:
        try:
            return extrai(http_json(url)), nome
        except Exception as e:  # tenta a proxima fonte
            print(f"Falha em {nome}: {e}")
    sys.exit("Nao foi possivel obter o preco em nenhuma fonte.")


def notificar(topico, titulo, msg, prioridade="high"):
    req = urllib.request.Request(
        f"https://ntfy.sh/{topico}",
        data=msg.encode("utf-8"),
        headers={
            "Title": titulo.encode("utf-8"),
            "Priority": prioridade,
            "Tags": "chart_with_downwards_trend",
            "Click": "https://www.coinbase.com/price/bitcoin",
        },
    )
    urllib.request.urlopen(req, timeout=20)


def fmt(v):
    return f"US$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def main():
    topico = os.environ.get("NTFY_TOPIC", "").strip()
    alvos_txt = os.environ.get("PRECO_ALVO", "").strip()
    if not topico or not alvos_txt:
        sys.exit("Configure o secret NTFY_TOPIC e a variable PRECO_ALVO.")
    # aceita "70000" ou "70000, 65000" (ou separado por ponto e virgula)
    partes = alvos_txt.replace(";", ",").replace(" ", "").split(",")
    alvos = sorted({float(p) for p in partes if p}, reverse=True)

    estado = {}
    if os.path.exists(ESTADO):
        with open(ESTADO, encoding="utf-8") as f:
            estado = json.load(f)
    disparados = set(estado.get("disparados", []))

    preco, fonte = preco_btc_usd()
    print(f"BTC agora: {fmt(preco)} (fonte: {fonte})")

    if os.environ.get("TESTE") == "1":
        notificar(topico, "Teste do alerta de Bitcoin",
                  f"Funcionando! BTC agora: {fmt(preco)}", "default")
        print("Notificacao de teste enviada.")

    for alvo in alvos:
        chave = str(alvo)
        if chave not in disparados and preco <= alvo:
            notificar(topico, f"Bitcoin caiu para {fmt(preco)}",
                      f"O BTC atingiu seu alvo de {fmt(alvo)}.\nPreco atual: {fmt(preco)}",
                      "urgent")
            disparados.add(chave)
            print(f"ALERTA enviado (alvo {fmt(alvo)}).")
        elif chave in disparados and preco > alvo * REARME:
            disparados.discard(chave)
            print(f"Alvo {fmt(alvo)} rearmado.")

    # descarta alvos que foram removidos da configuracao
    disparados &= {str(a) for a in alvos}

    agora = datetime.now(timezone.utc)
    novo = {"disparados": sorted(disparados)}
    # "batimento" mensal: um commit por mes impede o GitHub de desligar o agendamento
    ult = estado.get("batimento")
    if not ult or (agora - datetime.fromisoformat(ult)).days >= 30:
        novo["batimento"] = agora.isoformat(timespec="seconds")
    else:
        novo["batimento"] = ult

    if novo != estado:
        with open(ESTADO, "w", encoding="utf-8") as f:
            json.dump(novo, f, indent=2)
            f.write("\n")


if __name__ == "__main__":
    main()
