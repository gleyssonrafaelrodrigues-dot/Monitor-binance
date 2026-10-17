# Monitor MACD Binance — versão para celular

## Como usar
Este projeto é um painel web responsivo, ideal para abrir no navegador do Android. Para ficar acessível por um link, ele precisa ser publicado em um serviço de hospedagem (por exemplo, Streamlit Community Cloud) a partir de um repositório GitHub.

## Arquivos
- `app.py`: painel web responsivo.
- `requirements.txt`: dependências.

## Publicar
1. Crie um repositório no GitHub e envie estes arquivos.
2. No Streamlit Community Cloud, crie um app apontando para `app.py`.
3. Abra o link gerado no Android e, no Chrome, use o menu ⋮ → **Adicionar à tela inicial**.

## Regras
- M3: MACD padrão 12,26,9 em candles fechados.
- M15: SMA 9 acima da SMA 12 confirma entrada; SMA 9 abaixo da SMA 12 confirma saída.
- Tolerância configurável.
- Somente alertas; não executa ordens.
- O histórico mostrado é da sessão atual e não é persistente no servidor.
- O painel precisa permanecer aberto para continuar atualizando; não é um serviço de segundo plano.

## Atenção à escala
DIF/DEA dependem da escala de preço do ativo. Confira os valores-alvo para BTC/BRL e SOL/BRL antes de confiar nos sinais.
