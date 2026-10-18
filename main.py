
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv


# ==============================
# CONFIGURAÇÕES
# ==============================

load_dotenv()

TOKEN = os.getenv("TOKEN")
PREFIX = "!"


# ==============================
# INTENTS E CONFIGURAÇÃO DO BOT
# ==============================

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents
)


# ==============================
# EVENTOS
# ==============================

@bot.event
async def on_ready():
    print(f"✅ Bot conectado!")
    print(f"🔶 Prefixo: {PREFIX}")


# ==============================
# COMANDOS
# ==============================

@bot.command(name="ping")
async def ping(ctx):
    """Verifica a latência básica do bot."""
    await ctx.send("Pong! 🏓")


# ==============================
# INICIALIZAÇÃO
# ==============================

def main():
    if not TOKEN or not TOKEN.strip():
        print("ERRO: TOKEN não encontrado ou vazio!")
        print("Verifique se o arquivo .env existe e contém TOKEN=seu_token")
        return

    print("TOKEN encontrado! Iniciando o bot...")

    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("ERRO: Token inválido. Verifique o TOKEN no arquivo .env.")
    except discord.PrivilegedIntentsRequired:
        print(
            "ERRO: Intents privilegiados necessários. "
            "Verifique as configurações no Discord Developer Portal."
        )


if __name__ == "__main__":
    main()
