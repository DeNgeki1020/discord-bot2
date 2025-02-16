import discord
import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from discord.ext import commands
from discord.utils import get
from discord.ui import View, Button
import os
from dotenv import load_dotenv

# ⬆ .env ファイルを読み込む
load_dotenv()

# ⬆ 環境変数を取得
google_credentials_json = os.getenv("GOOGLE_CREDENTIALS")
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
TOKEN = os.getenv("DISCORD_BOT_TOKEN")  # 環境変数からBOTのトークンを取得
SPREADSHEET_ID = os.getenv("GOOGLE_SHEET_ID")  # .envに追加必須
CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_PATH")

# ⬆ Google Sheets の設定
SHEET_NAME = '参加者一覧'  # シート名
SCOPES = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
# ⬆ Google API 認証
credentials = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=SCOPES)
gc = gspread.authorize(credentials)
worksheet = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)

# ⬆ Discord Bot 設定
intents = discord.Intents.default()
intents.messages = True  
intents.guilds = True    
intents.message_content = True  
intents.members = True   

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user}")

@bot.command()
async def join(ctx, input_value: str):
    """参加者が !join (Discord ID) を入力し、Google Sheets のデータと照合してロールを付与"""
    guild = ctx.guild
    author = ctx.author

    try:
        # ⬆ Google Sheets からデータ取得
        worksheet = gc.open_by_key(SPREADSHEET_ID).worksheet(SHEET_NAME)
        values = worksheet.get_values()

        # ⬆ シートが空でないかチェック
        if not values:
            await ctx.send("⚠ 参加者データが見つかりません。")
            return

        # ⬆ データを DataFrame に変換
        df = pd.DataFrame(values[1:], columns=values[0])
        df["Discord ID"] = df["Discord ID"].astype(str).str.strip()  # IDを文字列として扱う

        # ⬆ Discord ID で検索
        matched_row = df[df["Discord ID"] == input_value]

        if matched_row.empty:
            await ctx.send(f"⚠ 認証失敗: `{input_value}` は登録されていません。", delete_after=10)
            return

        # ⬆ ロール名を取得
        role_name = matched_row.iloc[0]["Role Name"].strip()
        role = get(guild.roles, name=role_name)

        if not role:
            await ctx.send(f"⚠ ロール '{role_name}' がサーバーに存在しません。", delete_after=10)
            return

        # ⬆ ユーザーにロールを付与
        await author.add_roles(role)

        # ⬆ DM で通知
        await author.send(f"✅ あなたの認証が完了しました！ ロール `{role_name}` を付与しました。")

        # ⬆ サーバーで通知（10秒後に削除）
        await ctx.send(f"✅ {author.mention} さんの認証に成功！ ロール `{role_name}` を付与しました。", delete_after=10)

        # ⬆ 参加者の !join メッセージを削除
        await ctx.message.delete()

    except Exception as e:
        print(f"⚠ エラー: {e}")
        await ctx.send(f"⚠ システムエラーが発生しました: {e}")


class TicketButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケット発行", style=discord.ButtonStyle.success)
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        author = interaction.user

        # ✅ 「チケット」カテゴリーを確認、なければ作成
        category = discord.utils.get(guild.categories, name="チケット")
        if category is None:
            category = await guild.create_category("チケット")
        
        # ✅ 既存のチケットがないかチェック
        existing_channel = discord.utils.get(category.text_channels, name=f"ticket-{author.name.lower()}")
        if existing_channel:
            await interaction.response.send_message("⚠ 既にチケットを発行しています！", ephemeral=True)
            return

        # ✅ 新しいチケットチャンネルを作成（「チケット」カテゴリー内）
        ticket_channel = await guild.create_text_channel(
            name=f"ticket-{author.name}",
            category=category,
            overwrites={
                guild.default_role: discord.PermissionOverwrite(view_channel=False),  # 他の人には見えない
                author: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                discord.utils.get(guild.roles, name="運営"): discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }
        )

        # ✅ 運営ログチャンネルに通知
        log_channel = discord.utils.get(guild.text_channels, name="運営ログ")
        if log_channel:
            await log_channel.send(f"📌 {author.mention} さんが {ticket_channel.mention} を作成しました！")

        # ✅ チケット作成メッセージを送信（5秒後に削除）
        await interaction.response.send_message(f"✅ チケットを作成しました！ {ticket_channel.mention}", ephemeral=True, delete_after=5)

        # ✅ チケットチャンネルに「閉じるボタン」付きメッセージを送信
        await ticket_channel.send(f"{author.mention} さんのチケットが作成されました！\n問題が解決したら「チケットを閉じる」ボタンを押してください。", view=CloseTicketButton())

class CloseTicketButton(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="チケットを閉じる", style=discord.ButtonStyle.danger)
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        channel = interaction.channel
        await interaction.response.send_message("🔒 チケットを閉じています...", ephemeral=True, delete_after=3)
        
        # ✅ 5秒後にチケットを削除
        await channel.delete(delay=5)

# ✅ ボタンを表示するコマンド
@bot.command()
async def ticket(ctx):
    """お問い合わせ用のボタンを設置"""
    view = TicketButton()
    await ctx.send("💬 お問い合わせはこちらから！\nボタンを押すと、運営とやり取りできるチケットを発行します。", view=view)



import random

@bot.command()
async def dice(ctx):
    """1～100 の乱数を生成して送信"""
    number = random.randint(1, 100)
    await ctx.send(f"🎲 {ctx.author.mention} の出目は **{number}** です！")


        

bot.run(TOKEN)
