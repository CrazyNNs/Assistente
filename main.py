import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

bot = commands.Bot(command_prefix="!", intents=intents)

load_dotenv()

token = os.getenv("TOKEN")

if token is None:
    print("ERRO: A variável TOKEN não foi encontrada!")
elif not token.strip():
    print("ERRO: A variável TOKEN está vazia!")
else:
    print("TOKEN encontrado!")
    bot.run(token)
