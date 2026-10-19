import os
import json
import asyncio
import re
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import discord
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv


# ==========================================
# CONFIGURAÇÕES
# ==========================================

load_dotenv()

TOKEN = os.getenv("TOKEN")
PREFIX = "A."

# Cargo autorizado a criar eventos
CARGO_AUTORIZADO_ID = 1535058525334540299

# Fuso horário de Brasília
FUSO = ZoneInfo("America/Sao_Paulo")

# Arquivo onde os eventos serão guardados
ARQUIVO_EVENTOS = Path(__file__).with_name("eventos.json")

# Intervalo de verificação dos lembretes
INTERVALO_VERIFICACAO_SEGUNDOS = 20

# Prioridades dos eventos
PRIORIDADES = {
    "Máxima": 1,
    "Alta": 2,
    "Média": 3,
    "Baixa": 4,
}

DIAS_SEMANA = [
    "Segunda",
    "Terça",
    "Quarta",
    "Quinta",
    "Sexta",
    "Sábado",
    "Domingo",
]

ORDEM_PRIORIDADES = ["Máxima", "Alta", "Média", "Baixa"]

EMOJIS_PRIORIDADE = {
    "Máxima": "🔴",
    "Alta": "🟠",
    "Média": "🟡",
    "Baixa": "🟢",
}

calendario_view_registrado = False
# ==========================================
# INTENTS E BOT
# ==========================================

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
# FUNÇÕES
# ==========================================
def obter_prioridade(evento):
    prioridade = evento.get("prioridade", "Média")
    return prioridade if prioridade in ORDEM_PRIORIDADES else "Média"


def obter_data_evento(evento):
    return datetime.fromisoformat(evento["data_hora"])


def evento_ativo(evento):
    """Eventos passados continuam salvos, mas não entram na agenda futura."""
    return (
        evento.get("estado") != "excluido"
        and obter_data_evento(evento) > datetime.now(FUSO)
    )


def montar_texto_calendario(eventos, guild_id, pagina=0):
    """Monta a tabela e os eventos de um único dia da semana."""

    eventos_dia = [
        evento
        for evento in eventos
        if int(evento.get("guild_id") or 0) == guild_id
        and evento_ativo(evento)
        and obter_data_evento(evento).weekday() == pagina
    ]

    eventos_dia.sort(key=obter_data_evento)

    agrupados = {
        prioridade: []
        for prioridade in ORDEM_PRIORIDADES
    }

    for evento in eventos_dia:
        agrupados[obter_prioridade(evento)].append(evento)

    dia_nome = DIAS_SEMANA[pagina]

    linhas = [
        f"Prioridade | {dia_nome}",
        "----------------------"
    ]

    for prioridade in ORDEM_PRIORIDADES:
        quantidade = len(agrupados[prioridade])

        linhas.append(
            f"{EMOJIS_PRIORIDADE[prioridade]} "
            f"{prioridade} | {quantidade} evento(s)"
        )

    tabela = "```text\n" + "\n".join(linhas) + "\n```"

    detalhes = []

    for prioridade in ORDEM_PRIORIDADES:
        lista = agrupados[prioridade]

        if not lista:
            continue

        detalhes.append(
            f"\n{EMOJIS_PRIORIDADE[prioridade]} **{prioridade}**"
        )

        for evento in lista:
            data = obter_data_evento(evento)

            detalhes.append(
                f"• `{data:%d/%m/%Y %H:%M}` — "
                f"**{evento['nome']}**"
            )

            descricao = evento.get("descricao", "").strip()

            if descricao:
                detalhes.append(f"  └ {descricao[:150]}")

    if not detalhes:
        detalhes.append(
            "\nNenhum evento agendado para este dia."
        )

    texto_detalhes = "\n".join(detalhes)

    if len(texto_detalhes) > 3800:
        texto_detalhes = (
            texto_detalhes[:3750]
            + "\n\n*Lista reduzida devido ao limite de texto.*"
        )

    return tabela, texto_detalhes, len(eventos_dia)
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
        color=(
            discord.Color.orange()
            if lembrete
            else discord.Color.blurple()
        ),
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

    prioridade = obter_prioridade(evento)

    embed.add_field(
        name="🚦 Prioridade",
        value=f"{EMOJIS_PRIORIDADE[prioridade]} {prioridade}",
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

# ==========================================
# BOTÕES
# ==========================================
class BotaoPagina(discord.ui.Button):
    def __init__(self, pagina, direcao):
        self.pagina = pagina
        self.direcao = direcao

        if direcao == -1:
            label = "⬅️ Esquerda"
            disabled = pagina == 0
            custom_id = f"calendario:{pagina}:anterior"

        elif direcao == 1:
            label = "➡️ Direita"
            disabled = pagina == 6
            custom_id = f"calendario:{pagina}:proximo"

        else:
            label = f"Página {pagina + 1}/7"
            disabled = True
            custom_id = f"calendario:{pagina}:atual"

        super().__init__(
            label=label,
            style=discord.ButtonStyle.secondary,
            disabled=disabled,
            custom_id=custom_id
        )

    async def callback(self, interaction: discord.Interaction):
        if self.direcao == 0:
            return

        nova_pagina = self.pagina + self.direcao

        if not 0 <= nova_pagina <= 6:
            return

        async with bloqueio_arquivo:
            eventos = carregar_eventos()

        tabela, detalhes, quantidade = montar_texto_calendario(
            eventos,
            interaction.guild_id,
            nova_pagina
        )

        await interaction.response.edit_message(
            view=CalendarioView(
                interaction.guild_id,
                nova_pagina,
                tabela,
                detalhes,
                quantidade
            )
        )


class BotaoCalendario(discord.ui.Button):
    def __init__(self, pagina=0):
        super().__init__(
            label="Deletar",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            custom_id=f"calendario:{pagina}:deletar"
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Este botão só pode ser usado dentro do servidor.",
                ephemeral=True
            )
            return

        membro = interaction.user

        if not isinstance(membro, discord.Member):
            await interaction.response.send_message(
                "Não foi possível verificar suas permissões.",
                ephemeral=True
            )
            return

        autorizado = any(
            cargo.id == CARGO_AUTORIZADO_ID
            for cargo in membro.roles
        )

        if not autorizado:
            await interaction.response.send_message(
                "❌ Você não tem o cargo necessário para excluir eventos.",
                ephemeral=True
            )
            return

        async with bloqueio_arquivo:
            eventos = carregar_eventos()

        eventos_guild = [
            evento
            for evento in eventos
            if int(evento.get("guild_id") or 0) == interaction.guild_id
            and evento.get("estado") != "excluido"
        ]

        eventos_guild.sort(key=obter_data_evento)

        if not eventos_guild:
            await interaction.response.send_message(
                "Não existem eventos para excluir.",
                ephemeral=True
            )
            return

        if len(eventos_guild) > 25:
            aviso = (
                "\nSó os 25 primeiros eventos são mostrados. "
                "Exclua alguns para acessar os próximos."
            )
        else:
            aviso = ""

        await interaction.response.send_message(
            "🗑️ **Selecione o evento que deseja excluir.**\n"
            "Você precisará confirmar antes da exclusão."
            + aviso,
            view=SeletorEventoView(eventos_guild[:25]),
            ephemeral=True
        )


class CalendarioView(discord.ui.LayoutView):
    def __init__(
        self,
        guild_id,
        pagina=0,
        tabela="",
        detalhes="",
        quantidade=0
    ):
        super().__init__(timeout=None)

        self.guild_id = guild_id
        self.pagina = pagina

        dia_nome = DIAS_SEMANA[pagina]

        container = discord.ui.Container(
            discord.ui.TextDisplay(
                f"# 📅 Calendário — {dia_nome}"
            ),
            discord.ui.Separator(),
            discord.ui.TextDisplay(
                f"**Página:** {pagina + 1}/7\n"
                f"**Eventos neste dia:** {quantidade}"
            ),
            discord.ui.TextDisplay(tabela),
            discord.ui.Separator(),
            discord.ui.TextDisplay("## 📋 Eventos do dia"),
            discord.ui.TextDisplay(detalhes),
            discord.ui.Separator(),
            discord.ui.ActionRow(
                BotaoPagina(pagina, -1),
                BotaoPagina(pagina, 0),
                BotaoPagina(pagina, 1),
                BotaoCalendario(pagina)
            ),
            accent_colour=discord.Colour.blurple()
        )

        self.add_item(container)


class SeletorEvento(discord.ui.Select):
    def __init__(self, eventos):
        opcoes = []

        for evento in eventos:
            data = obter_data_evento(evento)
            prioridade = obter_prioridade(evento)

            nome = evento.get("nome", "Evento sem nome")[:100]
            descricao = (
                f"{data:%d/%m/%Y %H:%M} • {prioridade}"
            )[:100]

            opcoes.append(
                discord.SelectOption(
                    label=nome,
                    description=descricao,
                    value=str(evento["id"]),
                    emoji=EMOJIS_PRIORIDADE[prioridade]
                )
            )

        super().__init__(
            placeholder="Escolha um evento para excluir",
            min_values=1,
            max_values=1,
            options=opcoes
        )

    async def callback(self, interaction: discord.Interaction):
        evento_id = self.values[0]

        await interaction.response.send_message(
            "⚠️ **Tem certeza de que deseja excluir este evento?**\n"
            "Esta ação removerá o evento do arquivo de agendamentos.",
            view=ConfirmarExclusaoView(evento_id),
            ephemeral=True
        )


class SeletorEventoView(discord.ui.View):
    def __init__(self, eventos):
        super().__init__(timeout=180)
        self.add_item(SeletorEvento(eventos))


class ConfirmarExclusaoView(discord.ui.View):
    def __init__(self, evento_id):
        super().__init__(timeout=120)
        self.evento_id = evento_id

    @discord.ui.button(
        label="Confirmar exclusão",
        style=discord.ButtonStyle.danger,
        emoji="🗑️"
    )
    async def confirmar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        if interaction.guild_id is None:
            await interaction.response.send_message(
                "Este botão só pode ser usado no servidor.",
                ephemeral=True
            )
            return

        membro = interaction.user

        autorizado = (
            isinstance(membro, discord.Member)
            and any(
                cargo.id == CARGO_AUTORIZADO_ID
                for cargo in membro.roles
            )
        )

        if not autorizado:
            await interaction.response.send_message(
                "❌ Você não tem permissão para excluir eventos.",
                ephemeral=True
            )
            return

        async with bloqueio_arquivo:
            eventos = carregar_eventos()

            evento = next(
                (
                    item for item in eventos
                    if str(item.get("id")) == self.evento_id
                    and int(item.get("guild_id") or 0)
                    == interaction.guild_id
                    and item.get("estado") != "excluido"
                ),
                None
            )

            if evento is None:
                await interaction.response.send_message(
                    "Esse evento já foi excluído ou não existe.",
                    ephemeral=True
                )
                return

            nome = evento.get("nome", "Evento sem nome")

            # Exclusão definitiva do arquivo de eventos.
            eventos = [
                item for item in eventos
                if not (
                    str(item.get("id")) == self.evento_id
                    and int(item.get("guild_id") or 0)
                    == interaction.guild_id
                )
            ]

            salvar_eventos(eventos)

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"✅ O evento **{nome}** foi excluído.",
            view=self
        )

    @discord.ui.button(
        label="Cancelar",
        style=discord.ButtonStyle.secondary
    )
    async def cancelar(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button
    ):
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content="❎ Exclusão cancelada. O evento foi mantido.",
            view=self
        )
# ==========================================
# EVENTOS DO BOT
# ==========================================

@bot.event
async def on_ready():
    global comandos_sincronizados, calendario_view_registrado

    print(f"✅ Bot conectado como {bot.user}")
    print(f"🔶 Prefixo: {PREFIX}")

    if not comandos_sincronizados:
        try:
            comandos = await bot.tree.sync()
            comandos_sincronizados = True
            print(f"✅ {len(comandos)} comandos slash sincronizados.")
        except discord.HTTPException as erro:
            print(f"❌ Erro ao sincronizar comandos: {erro}")

    if not calendario_view_registrado:
        for pagina in range(7):
            bot.add_view(
                CalendarioView(
                    guild_id=None,
                    pagina=pagina
                )
            )

        calendario_view_registrado = True
        print("✅ Botões persistentes do calendário registrados.")

    if not verificar_lembretes.is_running():
        verificar_lembretes.start()
# ==========================================
# COMANDO TRADICIONAL
# ==========================================
@bot.command(name="ping")
async def ping(ctx):
    """Verifica se o bot está funcionando."""
    await ctx.send("Pong! 🏓")

@bot.command(name="calendario")
@commands.guild_only()
async def calendario(ctx):
    async with bloqueio_arquivo:
        eventos = carregar_eventos()

    pagina_inicial = 0

    tabela, detalhes, quantidade = montar_texto_calendario(
        eventos,
        ctx.guild.id,
        pagina_inicial
    )

    view = CalendarioView(
        ctx.guild.id,
        pagina_inicial,
        tabela,
        detalhes,
        quantidade
    )

    await ctx.send(view=view)
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
    mencionar="Mencione os usuários que receberão o lembrete (opcional)",
    imagem="Imagem opcional do evento (anexo)"
)
@app_commands.choices(
    prioridade=[
        app_commands.Choice(name="Máxima", value="Máxima"),
        app_commands.Choice(name="Alta", value="Alta"),
        app_commands.Choice(name="Média", value="Média"),
        app_commands.Choice(name="Baixa", value="Baixa"),
    ]
)
async def marcar(
    interaction: discord.Interaction,
    data: str,
    horario: str,
    nome: str,
    descricao: str,
    prioridade: app_commands.Choice[str],
    mencionar: str = None,
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
    # Validação das menções
    # --------------------------------------
if len(set(ids_encontrados)) > 4:
        await interaction.response.send_message(
            "❌ Você pode mencionar no máximo 4 usuários por evento.",
            ephemeral=True
        )
        return

for user_id in set(ids_encontrados):
        membro = interaction.guild.get_member(int(user_id))

    
if membro is not None:
    ids_mencionar.append(membro.id)

    if len(ids_mencionar) != len(set(ids_encontrados)):
        await interaction.response.send_message(
            "❌ Um ou mais usuários mencionados não foram encontrados "
            "neste servidor.",
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
    "criador_id": interaction.user.id,
    "nome": nome,
    "descricao": descricao,
    "imagem": imagem_url,
    "prioridade": prioridade.value,
    "usuarios_mencionar": ids_mencionar,
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

            # Eventos que já passaram não recebem lembrete atrasado.
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
                        
usuarios = evento.get("usuarios_mencionar", [])

mencoes = " ".join(
    f"<@{user_id}>"
    for user_id in usuarios
)

await canal.send(
    content=mencoes if mencoes else None,
    embed=criar_embed(evento, lembrete=True),
    allowed_mentions=discord.AllowedMentions(
        users=True,
        everyone=False,
        roles=False
    )
)
                    evento["lembrete_enviado"] = True
                    evento["estado"] = "lembrete_enviado"
                    alterado = True

                    print(f"🔔 Lembrete enviado: {evento['nome']}")

                except discord.NotFound:
                    evento["lembrete_enviado"] = True
                    evento["estado"] = "canal_indisponivel"
                    alterado = True

                except discord.Forbidden:
                    print(
                        f"Sem permissão para enviar o lembrete: "
                        f"{evento['nome']}"
                    )

                except discord.HTTPException as erro:
                    print(
                        f"Erro ao enviar lembrete de {evento['nome']}: "
                        f"{erro}"
                    )

        if alterado:
            salvar_eventos(eventos)


@verificar_lembretes.before_loop
async def antes_dos_lembretes():
    await bot.wait_until_ready()

# ==========================================
# INICIALIZAÇÃO
# ==========================================

def main():
    if not TOKEN or not TOKEN.strip():
        print("ERRO: TOKEN não encontrado ou vazio!")
        print("Verifique se o arquivo .env contém TOKEN=seu_token")
        return

    print("TOKEN encontrado! Iniciando o bot...")

    try:
        bot.run(TOKEN.strip())

    except discord.LoginFailure:
        print("ERRO: Token inválido. Verifique o arquivo .env.")

    except discord.PrivilegedIntentsRequired:
        print(
            "ERRO: Intents privilegiados necessários. "
            "Verifique o Discord Developer Portal."
        )


if __name__ == "__main__":
    main()
