
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv


# ==============================
# CONFIGURAÇÕES
# ==============================

load_dotenv()

TOKEN = os.getenv("TOKEN")
PREFIX = "A."


# ==============================
# INTENTS E CONFIGURAÇÃO DO BOT
# ==============================
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix=PREFIX,
    intents=intents
)

# Evita sincronizações repetidas durante reconexões
comandos_sincronizados = False

# Evita acessos simultâneos ao arquivo
bloqueio_arquivo = asyncio.Lock()

# ==========================================
# ARMAZENAMENTO DOS EVENTOS
# ==========================================
def carregar_eventos():
    """Carrega os eventos salvos no arquivo JSON."""
    if not ARQUIVO_EVENTOS.exists():
        return []

    try:
        with ARQUIVO_EVENTOS.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)

        return dados if isinstance(dados, list) else []

    except (json.JSONDecodeError, OSError) as erro:
        print(f"Erro ao carregar eventos: {erro}")
        return []


def salvar_eventos(eventos):
    """Salva os eventos de maneira atômica."""
    arquivo_temporario = ARQUIVO_EVENTOS.with_suffix(".tmp")

    with arquivo_temporario.open("w", encoding="utf-8") as arquivo:
        json.dump(
            eventos,
            arquivo,
            ensure_ascii=False,
            indent=4
        )

    os.replace(arquivo_temporario, ARQUIVO_EVENTOS)
# ==========================================
# UTILITÁRIOS
# ==========================================
def criar_embed(evento, lembrete=False):
    """Monta o embed de divulgação ou lembrete."""
    data_evento = datetime.fromisoformat(evento["data_hora"])

    embed = discord.Embed(
        title=(
            f"⏰ Lembrete: {evento['nome']}"
            if lembrete
            else f"📅 {evento['nome']}"
        ),
        description=evento["descricao"],
        color=discord.Color.orange() if lembrete
        else discord.Color.blurple(),
        timestamp=data_evento
    )

    embed.add_field(
        name="📆 Data",
        value=data_evento.strftime("%d/%m/%Y"),
        inline=True
    )

    embed.add_field(
        name="🕒 Horário",
        value=data_evento.strftime("%H:%M"),
        inline=True
    )

    embed.add_field(
        name="👤 Criado por",
        value=f"<@{evento['criador_id']}>",
        inline=True
    )

    if evento.get("imagem"):
        embed.set_image(url=evento["imagem"])

    if lembrete:
        embed.add_field(
            name="🔔 Aviso",
            value="Este evento começará em aproximadamente 1 hora!",
            inline=False
        )

    embed.set_footer(text=f"Evento ID: {evento['id']}")

    return embed
# ==============================
# EVENTOS
# ==============================
@bot.event
async def on_ready():
    global comandos_sincronizados

    print(f"✅ Bot conectado como {bot.user}")
    print(f"🔶 Prefixo: {PREFIX}")

    if not comandos_sincronizados:
        try:
            comandos = await bot.tree.sync()
            comandos_sincronizados = True

            print(f"✅ {len(comandos)} comandos slash sincronizados.")

        except discord.HTTPException as erro:
            print(f"Erro ao sincronizar comandos: {erro}")

    if not verificar_lembretes.is_running():
        verificar_lembretes.start()
# ==============================
# COMANDOS
# ==============================

@bot.command(name="ping")
async def ping(ctx):
    """Verifica a latência básica do bot."""
    await ctx.send("Pong! 🏓")
# ==========================================
# COMANDO SLASH /MARCAR
# ==========================================
@bot.tree.command(
    name="marcar",
    description="Cria um evento com lembrete automático."
)
@app_commands.guild_only()
@app_commands.describe(
    data="Data do evento no formato DD/MM/AAAA",
    horario="Horário no formato HH/MM (ex.: 20/30)",
    nome="Nome do evento",
    descricao="Descrição do evento",
    imagem="Imagem opcional do evento (anexo)"
)
async def marcar(
    interaction: discord.Interaction,
    data: str,
    horario: str,
    nome: str,
    descricao: str,
    imagem: discord.Attachment | None = None
):
# --------------------------------------
    # Verificação de permissão
    # --------------------------------------

    membro = interaction.user

    if not isinstance(membro, discord.Member):
        await interaction.response.send_message(
            "❌ Este comando só pode ser utilizado dentro de um servidor.",
            ephemeral=True
        )
        return

    possui_cargo = any(
        cargo.id == CARGO_AUTORIZADO_ID
        for cargo in membro.roles
    )

    if not possui_cargo:
        await interaction.response.send_message(
            "❌ Você não tem o cargo necessário para criar eventos.",
            ephemeral=True
        )
        return

    # --------------------------------------
    # Validação da data e do horário
    # --------------------------------------

    try:
        data_obj = datetime.strptime(data.strip(), "%d/%m/%Y").date()
    except ValueError:
        await interaction.response.send_message(
            "❌ Data inválida. Utilize DD/MM/AAAA, por exemplo: 25/12/2026.",
            ephemeral=True
        )
        return

    try:
        hora, minuto = map(int, horario.strip().split("/"))

        if not (0 <= hora <= 23 and 0 <= minuto <= 59):
            raise ValueError

        horario_obj = datetime.strptime(
            f"{hora:02d}:{minuto:02d}",
            "%H:%M"
        ).time()

    except ValueError:
        await interaction.response.send_message(
            "❌ Horário inválido. Utilize HH/MM, por exemplo: 20/30.",
            ephemeral=True
        )
        return

    data_hora = datetime.combine(
        data_obj,
        horario_obj,
        tzinfo=FUSO
    )

    agora = datetime.now(FUSO)

    # Exige pelo menos uma hora de antecedência
    if data_hora <= agora + timedelta(hours=1):
        await interaction.response.send_message(
            "❌ O evento precisa ser marcado para mais de uma hora no futuro, "
            "para que o lembrete possa ser enviado antes do início.",
            ephemeral=True
        )
        return

    # --------------------------------------
    # Validação dos campos de texto
    # --------------------------------------

    nome = nome.strip()
    descricao = descricao.strip()

    if not nome or len(nome) > 200:
        await interaction.response.send_message(
            "❌ O nome deve conter entre 1 e 200 caracteres.",
            ephemeral=True
        )
        return

    if not descricao or len(descricao) > 4000:
        await interaction.response.send_message(
            "❌ A descrição deve conter entre 1 e 4000 caracteres.",
            ephemeral=True
        )
        return

    # --------------------------------------
    # Validação e obtenção da imagem
    # --------------------------------------

    imagem_url = None

    if imagem is not None:
        if not imagem.content_type or not imagem.content_type.startswith("image/"):
            await interaction.response.send_message(
                "❌ O anexo precisa ser uma imagem.",
                ephemeral=True
            )
            return

        imagem_url = imagem.url

    # --------------------------------------
    # Criação e armazenamento do evento
    # --------------------------------------

    await interaction.response.defer(ephemeral=True)

    evento = {
        "id": str(interaction.id),
        "guild_id": interaction.guild_id,
        "canal_id": interaction.channel_id,
        "criador_id": membro.id,
        "nome": nome,
        "descricao": descricao,
        "imagem": imagem_url,
        "data_hora": data_hora.isoformat(),
        "lembrete_enviado": False
    }

    try:
        async with bloqueio_arquivo:
            eventos = carregar_eventos()
            eventos.append(evento)
            salvar_eventos(eventos)

    except OSError as erro:
        print(f"Erro ao salvar evento: {erro}")

        await interaction.followup.send(
            "❌ Não foi possível salvar o evento. Tente novamente.",
            ephemeral=True
        )
        return

    # --------------------------------------
    # Divulgação do evento no canal
    # --------------------------------------

    canal = interaction.channel

    try:
        if canal is None:
            canal = await bot.fetch_channel(interaction.channel_id)

        await canal.send(
            embed=criar_embed(evento),
            allowed_mentions=discord.AllowedMentions.none()
        )

    except (discord.HTTPException, discord.Forbidden) as erro:
        print(f"Evento salvo, mas não foi possível divulgá-lo: {erro}")

        await interaction.followup.send(
            "⚠️ O evento foi salvo, mas não consegui publicá-lo no canal. "
            "Verifique as permissões do bot.",
            ephemeral=True
        )
        return

    await interaction.followup.send(
        f"✅ Evento **{nome}** criado com sucesso!\n"
        f"📆 Data: {data_hora.strftime('%d/%m/%Y')}\n"
        f"🕒 Horário: {data_hora.strftime('%H:%M')}\n"
        "🔔 O lembrete será enviado uma hora antes.",
        ephemeral=True
    )


# ==========================================
# SISTEMA AUTOMÁTICO DE LEMBRETES
# ==========================================

@tasks.loop(seconds=INTERVALO_VERIFICACAO_SEGUNDOS)
async def verificar_lembretes():
    agora = datetime.now(FUSO)

    async with bloqueio_arquivo:
        eventos = carregar_eventos()
        alterado = False

        for evento in eventos:
            if evento.get("lembrete_enviado", False):
                continue

            data_hora = datetime.fromisoformat(evento["data_hora"])

            # Eventos que já terminaram não precisam de lembrete
            if data_hora <= agora:
                evento["lembrete_enviado"] = True
                evento["estado"] = "expirado"
                alterado = True
                continue

            horario_lembrete = data_hora - timedelta(hours=1)

            if agora >= horario_lembrete:
                try:
                    canal = bot.get_channel(int(evento["canal_id"]))

                    if canal is None:
                        canal = await bot.fetch_channel(
                            int(evento["canal_id"])
                        )

                    await canal.send(
                        content="@everyone",
                        embed=criar_embed(evento, lembrete=True),
                        allowed_mentions=discord.AllowedMentions(
                            everyone=True
                        )
                    )

                    evento["lembrete_enviado"] = True
                    evento["estado"] = "lembrete_enviado"
                    alterado = True

                    print(
                        f"🔔 Lembrete enviado: {evento['nome']}"
                    )

                except discord.NotFound:
                    # O canal foi removido
                    evento["lembrete_enviado"] = True
                    evento["estado"] = "canal_indisponivel"
                    alterado = True

                except discord.Forbidden:
                    # Não há permissão para enviar no canal
                    print(
                        f"Sem permissão para enviar lembrete: "
                        f"{evento['nome']}"
                    )

                except discord.HTTPException as erro:
                    # Mantém pendente para tentar novamente
                    print(
                        f"Falha ao enviar lembrete de {evento['nome']}: "
                        f"{erro}"
                    )

        if alterado:
            salvar_eventos(eventos)


@verificar_lembretes.before_loop
async def antes_dos_lembretes():
    await bot.wait_until_ready()
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
