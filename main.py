import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logado como {bot.user}")

@bot.command()
async def ping(ctx):
    await ctx.send("Pong! 🏓")

token = os.getenv("TOKEN")

if token is None or not token.strip():
    print("ERRO: TOKEN não encontrado ou vazio!")
else:
    print("TOKEN encontrado!")
    bot.run(token)
