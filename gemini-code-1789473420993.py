import json
import random
import os
import discord
from discord import app_commands
from discord.ext import commands

# --- FICHIERS DE DONNÉES (2 gros fichiers de ~25/30 Aniimos chacun) ---
FICHIERS_ANIIMOS = ["aniimos.json", "aniimos_2.json"]
INVENTORY_FILE = "inventaires.json"

# Charger et fusionner automatiquement tous les fichiers de données
ANIIMOS_DATA = {}
for file_path in FICHIERS_ANIIMOS:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            ANIIMOS_DATA.update(data)
    except FileNotFoundError:
        pass

def charger_inventaires():
    try:
        with open(INVENTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def sauvegarder_inventaires(data):
    with open(INVENTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# Dictionnaires pour la gestion en cours
ACTIVES_SPAWNS = {}      # { channel_id: "nom_cle_de_l_aniimo" }
MESSAGE_COUNTERS = {}    # { channel_id: nombre_de_messages }
ACTIVE_BATTLES = set()   # Pour éviter qu'un joueur lance plusieurs combats en même temps

# --- INTERFACE DE CAPTURE (BOUTON) ---
class CaptureView(discord.ui.View):
    def __init__(self, aniimo_key):
        super().__init__(timeout=180)
        self.aniimo_key = aniimo_key

    @discord.ui.button(label="✨ Capturer l'Aniimo !", style=discord.ButtonStyle.green)
    async def capture_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel_id = interaction.channel.id
        
        if channel_id not in ACTIVES_SPAWNS or ACTIVES_SPAWNS[channel_id] != self.aniimo_key:
            await interaction.response.send_message("❌ Cet Aniimo s'est déjà échappé ou a déjà été capturé !", ephemeral=True)
            return

        user_id = str(interaction.user.id)
        aniimo_info = ANIIMOS_DATA[self.aniimo_key]

        inventaires = charger_inventaires()
        if user_id not in inventaires:
            inventaires[user_id] = {"equipe": [], "box": []}

        inventaires[user_id]["box"].append({
            "id": self.aniimo_key,
            "nom": aniimo_info["nom"],
            "element": aniimo_info["element"],
            "role": aniimo_info["role"],
            "niveau": 5
        })
        
        if not inventaires[user_id]["equipe"]:
            inventaires[user_id]["equipe"].append(inventaires[user_id]["box"][-1])

        sauvegarder_inventaires(inventaires)
        del ACTIVES_SPAWNS[channel_id]

        for child in self.children:
            child.disabled = True
        await interaction.message.edit(view=self)

        await interaction.response.send_message(f"🎉 **{interaction.user.name}** a capturé un **{aniimo_info['nom']}** ({aniimo_info['element']}) !")

# --- SYSTÈME DE COMBAT RPG AU TOUR PAR TOUR ---
class CombatView(discord.ui.View):
    def __init__(self, p1, p2, p1_aniimo, p2_aniimo):
        super().__init__(timeout=60)
        self.p1 = p1
        self.p2 = p2
        self.p1_aniimo = p1_aniimo
        self.p2_aniimo = p2_aniimo
        self.p1_hp = 100
        self.p2_hp = 100
        self.turn = p1

    @discord.ui.button(label="⚔️ Attaquer", style=discord.ButtonStyle.danger)
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user not in (self.p1, self.p2):
            await interaction.response.send_message("Ce n'est pas ton combat !", ephemeral=True)
            return
        
        if interaction.user != self.turn:
            await interaction.response.send_message("Ce n'est pas ton tour de jouer !", ephemeral=True)
            return

        degats = random.randint(15, 30)

        if interaction.user == self.p1:
            self.p2_hp -= degats
            self.turn = self.p2
        else:
            self.p1_hp -= degats
            self.turn = self.p1

        if self.p1_hp <= 0 or self.p2_hp <= 0:
            gagnant = self.p1 if self.p1_hp > 0 else self.p2
            for child in self.children:
                child.disabled = True
            ACTIVE_BATTLES.discard(self.p1.id)
            ACTIVE_BATTLES.discard(self.p2.id)
            await interaction.message.edit(view=self)
            await interaction.response.send_message(f"🏆 Fin du combat ! **{gagnant.mention}** remporte la victoire !")
            return

        embed = discord.Embed(title="⚔️ Combat RPG en cours", color=discord.Color.orange)
        embed.add_field(name=f"{self.p1.name} ({self.p1_aniimo['nom']})", value=f"❤️ PV: {max(0, self.p1_hp)}/100", inline=True)
        embed.add_field(name=f"{self.p2.name} ({self.p2_aniimo['nom']})", value=f"❤️ PV: {max(0, self.p2_hp)}/100", inline=True)
        embed.set_footer(text=f"C'est au tour de {self.turn.name} de jouer !")

        await interaction.response.edit_message(embed=embed, view=self)

# --- CONFIGURATION DU BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Bot connecté en tant que {bot.user} ! Commandes synchronisées : {len(synced)}")
        print(f"Nombre total d'Aniimos chargés : {len(ANIIMOS_DATA)}")
    except Exception as e:
        print(e)

@bot.event
async def on_message(message):
    if message.author.bot:
        return

    channel_id = message.channel.id
    MESSAGE_COUNTERS[channel_id] = MESSAGE_COUNTERS.get(channel_id, 0) + 1

    if MESSAGE_COUNTERS[channel_id] >= 10:
        MESSAGE_COUNTERS[channel_id] = 0

        aniimo_key = random.choice(list(ANIIMOS_DATA.keys()))
        aniimo_info = ANIIMOS_DATA[aniimo_key]
        ACTIVES_SPAWNS[channel_id] = aniimo_key

        embed = discord.Embed(
            title="✨ Un Aniimo sauvage apparaît !",
            description=f"Un **{aniimo_info['nom']}** ({aniimo_info['element']} - {aniimo_info['role']}) sauvage pointe le bout de son nez !\n\n*{aniimo_info['description']}*",
            color=discord.Color.blue()
        )
        embed.set_footer(text="Clique sur le bouton ci-dessous pour le capturer !")

        view = CaptureView(aniimo_key)
        await message.channel.send(embed=embed, view=view)

    await bot.process_commands(message)

# --- COMMANDES RPG ---
@bot.tree.command(name="inventaire", description="Affiche tes Aniimos capturés.")
async def inventaire(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    inventaires = charger_inventaires()

    if user_id not in inventaires or not inventaires[user_id]["box"]:
        await interaction.response.send_message("Tu n'as capturé aucun Aniimo pour l'instant ! Parle dans les salons pour en faire spawner.", ephemeral=True)
        return

    box = inventaires[user_id]["box"]
    description = ""
    for idx, a in enumerate(box, 1):
        description += f"**{idx}.** {a['nom']} ({a['element']}) - Rôle: {a['role']} | Niv. {a['niveau']}\n"

    embed = discord.Embed(title=f"🎒 Inventaire de {interaction.user.name}", description=description, color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="combat", description="Affronte un autre joueur en duel RPG avec ton premier Aniimo !")
async def combat(interaction: discord.Interaction, adversaire: discord.Member):
    if adversaire.bot or adversaire == interaction.user:
        await interaction.response.send_message("Tu ne peux pas combattre un bot ou toi-même !", ephemeral=True)
        return

    user_id = str(interaction.user.id)
    adv_id = str(adversaire.id)
    inventaires = charger_inventaires()

    if user_id not in inventaires or not inventaires[user_id]["equipe"]:
        await interaction.response.send_message("Tu n'as pas d'Aniimo dans ton équipe ! Capture-en un d'abord.", ephemeral=True)
        return
    if adv_id not in inventaires or not inventaires[adv_id]["equipe"]:
        await interaction.response.send_message("Ton adversaire n'a pas d'équipe d'Aniimo !", ephemeral=True)
        return

    if interaction.user.id in ACTIVE_BATTLES or adversaire.id in ACTIVE_BATTLES:
        await interaction.response.send_message("L'un des joueurs est déjà en plein combat !", ephemeral=True)
        return

    ACTIVE_BATTLES.add(interaction.user.id)
    ACTIVE_BATTLES.add(adversaire.id)

    p1_aniimo = inventaires[user_id]["equipe"][0]
    p2_aniimo = inventaires[adv_id]["equipe"][0]

    embed = discord.Embed(title="⚔️ Début du combat RPG !", description=f"{interaction.user.mention} ({p1_aniimo['nom']}) affronte {adversaire.mention} ({p2_aniimo['nom']}) !", color=discord.Color.gold())
    embed.add_field(name=f"{interaction.user.name}", value=f"❤️ PV: 100/100", inline=True)
    embed.add_field(name=f"{adversaire.name}", value=f"❤️ PV: 100/100", inline=True)
    embed.set_footer(text=f"C'est au tour de {interaction.user.name} de commencer !")

    view = CombatView(interaction.user, adversaire, p1_aniimo, p2_aniimo)
    await interaction.response.send_message(embed=embed, view=view)

# Lancement sécurisé du bot via Render
bot.run(os.getenv("DISCORD_TOKEN"))
